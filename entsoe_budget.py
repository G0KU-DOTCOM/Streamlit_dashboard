"""Persistent download limits for the project's sequential ENTSO-E requests.

The ledger counts attempts and decoded bytes across reruns. It contains no
credentials or URLs. A process lock prevents competing runs from spending the
same allowance. Interrupted requests retain their full byte reservation.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import time
import tomllib
import xml.etree.ElementTree as ET

import requests

from entsoe_data import EntsoeDataError, flow_intervals

CHUNK_BYTES = 8192
ENDPOINT = 'https://web-api.tp.entsoe.eu/api'


class DownloadStopped(EntsoeDataError):
    def __init__(self, message, code='budget_stop'):
        super().__init__(message)
        self.code = code


def _save_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


class DownloadBudget:
    def __init__(self, project_root):
        self.root = Path(project_root)
        self.plan = json.loads((self.root / 'entsoe_plan.json').read_text())
        self.limits = self.plan['planned_limits']
        self.cache = self.root / 'no_sync' / 'entsoe_cache'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'no_sync' / 'entsoe_download_ledger.json'
        self.lock_path = self.path.with_suffix('.lock')

    def _read(self):
        if self.path.exists():
            try:
                ledger = json.loads(self.path.read_text())
                valid = (
                    ledger['version'] == 1
                    and isinstance(ledger['attempts'], int) and ledger['attempts'] >= 0
                    and isinstance(ledger['charged_bytes'], int) and ledger['charged_bytes'] >= 0
                    and isinstance(ledger['last_request_at'], (int, float))
                    and isinstance(ledger['requests'], dict)
                    and ledger['attempts'] == len(ledger['requests'])
                    and all(r['status'] in ('ok', 'failed', 'in_progress')
                            and isinstance(r['charged_bytes'], int) and r['charged_bytes'] >= 0
                            for r in ledger['requests'].values())
                    and ledger['charged_bytes'] == sum(r['charged_bytes'] for r in ledger['requests'].values())
                )
                if not valid:
                    raise ValueError
                return ledger
            except (ValueError, KeyError, TypeError, AttributeError):
                raise DownloadStopped('Download ledger is invalid; review it rather than reset the budget.') from None
        return {'version': 1, 'attempts': 0, 'charged_bytes': 0,
                'last_request_at': 0, 'requests': {}}

    def snapshot(self):
        return self._read()

    def load(self, origin, destination, start, end, cache_name, max_response_bytes=None):
        # Keep cache paths local and date intervals explicit.
        if Path(cache_name).name != cache_name or not cache_name.endswith('.xml'):
            raise DownloadStopped('Use a plain XML filename inside the cache.')
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise DownloadStopped('Use a positive interval with timezone-aware dates.')
        cap = min(self.limits['max_response_bytes'] if max_response_bytes is None else max_response_bytes, self.limits['max_response_bytes'])
        if cap <= 0:
            raise DownloadStopped('Response limit must be positive.')
        # Each process holds this lock for the whole cache/read/request operation.
        with self.lock_path.open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DownloadStopped('Another ENTSO-E download is running; no request started.') from None
            return self._load_locked(origin, destination, start, end, cache_name, cap)

    def _load_locked(self, origin, destination, start, end, cache_name, cap):
        from datetime import timezone
        parameters = {'documentType': 'A11', 'out_Domain': origin, 'in_Domain': destination,
                      'periodStart': start.astimezone(timezone.utc).strftime('%Y%m%d%H%M'),
                      'periodEnd': end.astimezone(timezone.utc).strftime('%Y%m%d%H%M')}
        key = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
        ledger = self._read()
        cache_path = self.cache / cache_name
        cache_bytes = sum(p.stat().st_size for p in self.cache.rglob('*') if p.is_file())
        if cache_bytes > self.limits['max_entsoe_cache_bytes']:
            raise DownloadStopped('Total ENTSO-E cache exceeds its limit.')
        if cache_path.exists():
            if cache_path.stat().st_size > cap:
                raise DownloadStopped('Cached response exceeds the per-response limit.')
            body = cache_path.read_bytes()
            flow_intervals(body, origin, destination, start, end)
            record = ledger['requests'].get(key)
            if record and record['status'] == 'ok' and record['sha256'] != hashlib.sha256(body).hexdigest():
                raise DownloadStopped('Cached XML changed since validation; review before reuse.')
            return body, 0
        if any(r['status'] == 'in_progress' for r in ledger['requests'].values()):
            raise DownloadStopped('An interrupted request retains a byte reservation; review before continuing.')
        if key in ledger['requests']:
            raise DownloadStopped('This request was already attempted; no automatic retry.', 'already_attempted')
        if ledger['attempts'] >= self.limits['max_total_request_attempts']:
            raise DownloadStopped('The total request-attempt limit is reached.')
        # Account even for the one decoded chunk that detects an oversized body.
        reservation = cap + CHUNK_BYTES
        if ledger['charged_bytes'] + reservation > self.limits['max_new_decoded_download_bytes']:
            raise DownloadStopped('Insufficient remaining cumulative download allowance.')
        if cache_bytes + cap > self.limits['max_entsoe_cache_bytes']:
            raise DownloadStopped('Insufficient remaining cache allowance.')
        if shutil.disk_usage(self.root).free < self.limits['min_host_free_bytes'] + cap:
            raise DownloadStopped('Insufficient free host disk space.')
        try:
            with (self.root / '.streamlit' / 'secrets.toml').open('rb') as handle:
                token = tomllib.load(handle)['entsoe']['token']
            if not isinstance(token, str) or not token.strip():
                raise ValueError
        except (OSError, KeyError, ValueError):
            raise DownloadStopped('Configure [entsoe] token in local Streamlit secrets.', 'credentials') from None
        remaining_wait = self.limits['min_seconds_between_requests'] - (time.time() - ledger['last_request_at'])
        if remaining_wait > 0:
            time.sleep(remaining_wait)
        record = {'cache_name': cache_name, 'status': 'in_progress', 'charged_bytes': reservation}
        ledger['requests'][key] = record
        ledger['attempts'] += 1
        ledger['charged_bytes'] += reservation
        ledger['last_request_at'] = time.time()
        _save_json(self.path, ledger)  # Reserve before any network action.
        received = 0
        body = bytearray()
        began = time.monotonic()
        try:
            try:
                with requests.get(ENDPOINT, params={**parameters, 'securityToken': token},
                                  stream=True, timeout=(10, 45), allow_redirects=False) as response:
                    # Error response bodies are small and counted too, but never printed.
                    for chunk in response.iter_content(chunk_size=CHUNK_BYTES):
                        received += len(chunk)
                        if received > cap:
                            raise DownloadStopped('Response exceeded its size limit.', 'response_limit')
                        if time.monotonic() - began > 120:
                            raise DownloadStopped('Request exceeded its time limit.', 'timeout')
                        body.extend(chunk)
                    if response.status_code != 200:
                        raise DownloadStopped(f'ENTSO-E returned HTTP {response.status_code}; details hidden.', f'http_{response.status_code}')
            except requests.RequestException:
                raise DownloadStopped('ENTSO-E network request failed; details hidden.', 'network') from None
            if token.encode() in body:
                raise DownloadStopped('Unexpected sensitive response; not saved.', 'sensitive_response')
            try:
                root = ET.fromstring(body)
                if root.tag.rsplit('}', 1)[-1] == 'Acknowledgement_MarketDocument':
                    code = root.findtext('{*}Reason/{*}code')
                    raise DownloadStopped('API acknowledgement returned, not a flow series.', 'no_data' if code == '999' else 'acknowledgement')
            except ET.ParseError:
                raise DownloadStopped('Response is not valid XML.', 'invalid_xml') from None
            flow_intervals(body, origin, destination, start, end)
            if sum(p.stat().st_size for p in self.cache.rglob('*') if p.is_file()) + len(body) > self.limits['max_entsoe_cache_bytes']:
                raise DownloadStopped('Cache allowance was consumed during this request.')
            temporary = cache_path.with_suffix('.tmp')
            temporary.write_bytes(body)
            temporary.replace(cache_path)
            record.update(status='ok', sha256=hashlib.sha256(body).hexdigest())
        except Exception as exc:
            record.update(status='failed', error_code=getattr(exc, 'code', 'validation_or_io'))
            if isinstance(exc, EntsoeDataError):
                raise
            raise DownloadStopped('Response processing failed; details hidden.', 'validation_or_io') from None
        finally:
            # A KeyboardInterrupt/crash keeps the full reservation and in-progress
            # state; ordinary completion charges all bytes actually received.
            if record['status'] != 'in_progress':
                ledger['charged_bytes'] += received - reservation
                record['charged_bytes'] = received
                _save_json(self.path, ledger)
        return bytes(body), received
