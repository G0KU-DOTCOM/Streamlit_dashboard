"""Bounded ENTSO-E downloads and interval conversion for notebook figures."""
import math
import re
import xml.etree.ElementTree as ET

import pandas as pd

ENDPOINT = 'https://web-api.tp.entsoe.eu/api'
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class EntsoeDataError(Exception):
    """A safe diagnostic that never includes the token or request URL."""


def load_flow_xml(project_root, origin, destination, start, end, cache_name, *, max_response_bytes=None):
    """Use the persistent project budget for every cache read or GET request."""
    # Import here to avoid a cycle: the budget reuses this module's XML checks.
    from entsoe_budget import DownloadBudget
    return DownloadBudget(project_root).load(
        origin, destination, start, end, cache_name, max_response_bytes
    )


def validate_document(body, origin, destination):
    """Reject API error documents, other data items, and incorrect directions."""
    if len(body) > MAX_RESPONSE_BYTES:
        raise EntsoeDataError('XML exceeds the response size limit.')
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise EntsoeDataError('Invalid XML response.') from None
    series = root.findall('{*}TimeSeries')
    if root.findtext('{*}type') != 'A11' or not series:
        raise EntsoeDataError('No physical-flow data returned; response may be an API acknowledgement.')
    for item in series:
        if (item.findtext('{*}out_Domain.mRID') != origin
                or item.findtext('{*}in_Domain.mRID') != destination):
            raise EntsoeDataError('The XML direction differs from the requested direction.')
    return root


def flow_intervals(body, origin, destination, start, end):
    """Decode A01/A03 MW blocks, clip to a UTC window, and calculate MWh.

    A03 values extend to the next position or their own period end. A01
    values cover exactly one resolution step. Gaps stay gaps; nothing is
    filled across XML periods. Overlapping series require review, not summing.
    """
    root = validate_document(body, origin, destination)
    window_start, window_end = pd.Timestamp(start).tz_convert('UTC'), pd.Timestamp(end).tz_convert('UTC')
    if window_start >= window_end:
        raise EntsoeDataError('The requested interval must have positive duration.')
    rows = []
    try:
        for series in root.findall('{*}TimeSeries'):
            curve = series.findtext('{*}curveType', default='A01')
            if curve not in ('A01', 'A03') or series.findtext('{*}quantity_Measure_Unit.name') != 'MAW':
                raise EntsoeDataError('Unsupported curve type or power unit.')
            for period in series.findall('{*}Period'):
                period_start = pd.Timestamp(period.findtext('{*}timeInterval/{*}start')).tz_convert('UTC')
                period_end = pd.Timestamp(period.findtext('{*}timeInterval/{*}end')).tz_convert('UTC')
                resolution_text = period.findtext('{*}resolution', default='')
                if not re.fullmatch(r'PT(?:\d+H)?(?:\d+M)?(?:\d+S)?', resolution_text):
                    raise EntsoeDataError('Unsupported resolution.')
                resolution = pd.Timedelta(resolution_text)
                if resolution <= pd.Timedelta(0) or period_end <= period_start:
                    raise EntsoeDataError('Invalid period length or resolution.')
                if (period_end - period_start) % resolution != pd.Timedelta(0):
                    raise EntsoeDataError('Period length is not a whole number of resolution steps.')
                points = sorted((int(p.findtext('{*}position')), float(p.findtext('{*}quantity')))
                                for p in period.findall('{*}Point'))
                positions = [position for position, _ in points]
                if len(set(positions)) != len(positions):
                    raise EntsoeDataError('Duplicate point positions.')
                for i, (position, power) in enumerate(points):
                    begin = period_start + (position - 1) * resolution
                    if position < 1 or begin >= period_end or not math.isfinite(power) or power < 0:
                        raise EntsoeDataError('Invalid position or power value.')
                    finish = (period_start + (points[i + 1][0] - 1) * resolution
                              if curve == 'A03' and i + 1 < len(points)
                              else period_end if curve == 'A03' else begin + resolution)
                    if finish > period_end or finish <= begin:
                        raise EntsoeDataError('Invalid interval boundary.')
                    begin, finish = max(begin, window_start), min(finish, window_end)
                    if finish <= begin:
                        continue
                    hours = (finish - begin).total_seconds() / 3600
                    rows.append((begin, finish, power, hours, power * hours))
    except (TypeError, ValueError, OverflowError):
        raise EntsoeDataError('Invalid field in XML flow data.') from None
    if not rows:
        raise EntsoeDataError('No flow intervals in the requested window.')
    frame = pd.DataFrame(rows, columns=['start_utc', 'end_utc', 'power_mw', 'hours', 'energy_mwh'])
    frame = frame.sort_values('start_utc').reset_index(drop=True)
    if (frame['start_utc'].iloc[1:].reset_index(drop=True)
            < frame['end_utc'].iloc[:-1].reset_index(drop=True)).any():
        raise EntsoeDataError('Overlapping flow intervals; totals would double count data.')
    return frame


def coverage_summary(frame, start, end):
    """Count covered hours and require full coverage before annual figures."""
    expected = (pd.Timestamp(end).tz_convert('UTC') - pd.Timestamp(start).tz_convert('UTC')).total_seconds() / 3600
    covered = float(frame['hours'].sum())
    return {'expected_hours': expected, 'covered_hours': covered,
            'coverage_percent': 100 * covered / expected,
            'complete': math.isclose(covered, expected, rel_tol=0, abs_tol=1e-7)}
