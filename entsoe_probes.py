"""One-day, sequential border checks. No database reads or writes."""
import json
from pathlib import Path

import pandas as pd

from entsoe_budget import DownloadBudget, DownloadStopped, _save_json
from entsoe_data import EntsoeDataError, flow_intervals, coverage_summary

PROBE_DAY = '2026-01-01'
PROBE_RESPONSE_CAP = 128 * 1024


def run_probes(project_root, *, allow_download=False, progress=None):
    """Check the fixed plan's borders, with cache-only behavior by default.

    Failed requests are never retried automatically. Results contain safe status
    codes, never exception details, request URLs, tokens, or raw response text.
    """
    root = Path(project_root)
    budget = DownloadBudget(root)
    start = pd.Timestamp(PROBE_DAY, tz='Europe/Oslo')
    end = start + pd.Timedelta(days=1)
    report_path = root / 'no_sync/entsoe_probe_results.json'
    before = budget.snapshot()
    report = {'day': PROBE_DAY, 'timezone': 'Europe/Oslo', 'rows': [],
              'new_requests_this_run': 0, 'new_bytes_this_run': 0}
    stopped = False
    for connection in budget.plan['connections']:
        for direction in ('import', 'export'):
            name = connection['connection']
            origin, destination = connection['norwegian_eic'], connection['foreign_eic']
            if direction == 'import':
                origin, destination = destination, origin
            cache_name = f"{name.replace('-', '_')}_{PROBE_DAY}_{direction}.xml"
            row = {'connection': name, 'direction': direction, 'status': 'not_checked',
                   'covered_hours': None, 'energy_mwh': None, 'intervals': None,
                   'xml_bytes': None, 'downloaded_bytes': 0}
            try:
                if stopped:
                    row['status'] = 'stopped'
                elif not allow_download and not (budget.cache / cache_name).exists():
                    row['status'] = 'not_cached'
                else:
                    body, downloaded = budget.load(origin, destination, start, end, cache_name, PROBE_RESPONSE_CAP)
                    intervals = flow_intervals(body, origin, destination, start, end)
                    coverage = coverage_summary(intervals, start, end)
                    row.update(status='complete' if coverage['complete'] else 'partial',
                               covered_hours=coverage['covered_hours'],
                               energy_mwh=float(intervals['energy_mwh'].sum()),
                               intervals=len(intervals), xml_bytes=len(body), downloaded_bytes=downloaded)
            except DownloadStopped as exc:
                row['status'] = exc.code
                # Unsupported/no-data pairs can be reported independently; account,
                # throttling, network and budget failures stop the whole run.
                if exc.code not in ('no_data', 'http_400', 'http_404', 'acknowledgement', 'already_attempted'):
                    stopped = True
            except EntsoeDataError:
                row['status'] = 'invalid_flow_data'
                stopped = True
            report['rows'].append(row)
            current = budget.snapshot()
            report['new_requests_this_run'] = current['attempts'] - before['attempts']
            report['new_bytes_this_run'] = current['charged_bytes'] - before['charged_bytes']
            report['ledger_total_attempts'] = current['attempts']
            report['ledger_total_charged_bytes'] = current['charged_bytes']
            # Cache-only notebook display does not overwrite the original run audit.
            if allow_download:
                _save_json(report_path, report)
            if progress:
                progress(f"{name} {direction}: {row['status']} ({row['covered_hours']} h)")
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Permit bounded one-day API requests for missing cache entries.')
    args = parser.parse_args()
    result = run_probes(Path(__file__).resolve().parent, allow_download=args.download,
                        progress=lambda text: print(text, flush=True))
    print(f"New requests: {result['new_requests_this_run']}; new decoded bytes: {result['new_bytes_this_run']}")
