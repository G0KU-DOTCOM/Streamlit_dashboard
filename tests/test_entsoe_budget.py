"""Check persisted safety limits with synthetic XML and no network or database."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from pipeline.entsoe_budget import DownloadBudget, DownloadStopped, CHUNK_BYTES
from pipeline.entsoe_data import EntsoeDataError
from test_entsoe_data import xml, START, END


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = json.loads(Path('entsoe_plan.json').read_text())
        self.plan['planned_limits'].update(min_host_free_bytes=0, min_seconds_between_requests=0)
        self.save_plan()
        (self.root / '.streamlit').mkdir()
        (self.root / '.streamlit/secrets.toml').write_text('[entsoe]\ntoken = "dummy-test-secret"\n')
        self.body = xml([(1, 100)])
        self.get = self.enterContext(patch('pipeline.entsoe_budget.requests.get'))
        self.response(self.body)

    def save_plan(self):
        (self.root / 'entsoe_plan.json').write_text(json.dumps(self.plan))

    def response(self, body, status=200):
        response = MagicMock(status_code=status)
        response.iter_content.side_effect = lambda chunk_size: (
            body[i:i + chunk_size] for i in range(0, len(body), chunk_size)
        )
        self.get.return_value.__enter__.return_value = response

    def load(self, name='probe.xml', cap=4096):
        return DownloadBudget(self.root).load('origin', 'destination', START, END, name, cap)

    def test_persisted_bytes_and_cache_reuse(self):
        self.assertEqual(self.load(), (self.body, len(self.body)))
        ledger = DownloadBudget(self.root).snapshot()
        self.assertEqual((ledger['attempts'], ledger['charged_bytes']), (1, len(self.body)))
        self.assertEqual(self.load(), (self.body, 0))
        self.get.assert_called_once()
        self.assertNotIn('dummy-test-secret', json.dumps(ledger))
        self.assertEqual(DownloadBudget(self.root).snapshot(), ledger)

    def test_limits_stop_before_network(self):
        for limit, value in [('max_total_request_attempts', 0),
                             ('max_new_decoded_download_bytes', 4096 + CHUNK_BYTES - 1),
                             ('max_entsoe_cache_bytes', 4095),
                             ('min_host_free_bytes', 10**20)]:
            with self.subTest(limit=limit):
                original = self.plan['planned_limits'][limit]
                self.plan['planned_limits'][limit] = value
                self.save_plan()
                with self.assertRaises(DownloadStopped):
                    self.load()
                self.get.assert_not_called()
                self.plan['planned_limits'][limit] = original
        self.save_plan()

    def test_existing_cache_counts_toward_cache_limit(self):
        budget = DownloadBudget(self.root)
        (budget.cache / 'another.xml').write_bytes(b'x' * 100)
        self.plan['planned_limits']['max_entsoe_cache_bytes'] = 4195
        self.save_plan()
        with self.assertRaises(DownloadStopped):
            self.load()
        self.get.assert_not_called()

    def test_cumulative_limit_applies_across_instances(self):
        self.load()
        self.plan['planned_limits']['max_new_decoded_download_bytes'] = len(self.body) + 4096 + CHUNK_BYTES - 1
        self.save_plan()
        with self.assertRaisesRegex(DownloadStopped, 'cumulative'):
            DownloadBudget(self.root).load('other', 'destination', START, END, 'second.xml', 4096)
        self.get.assert_called_once()
        self.plan['planned_limits']['max_new_decoded_download_bytes'] = 1000000
        self.plan['planned_limits']['max_total_request_attempts'] = 1
        self.save_plan()
        with self.assertRaisesRegex(DownloadStopped, 'attempt-limit|attempt limit'):
            DownloadBudget(self.root).load('other', 'destination', START, END, 'second.xml', 4096)
        self.get.assert_called_once()

    def test_failed_attempt_counted_and_not_retried(self):
        self.response(b'dummy-test-secret should never be printed', 429)
        with self.assertRaises(DownloadStopped) as ctx:
            self.load()
        self.assertEqual(ctx.exception.code, 'http_429')
        self.assertNotIn('dummy-test-secret', str(ctx.exception))
        ledger = DownloadBudget(self.root).snapshot()
        self.assertEqual(ledger['charged_bytes'], len(b'dummy-test-secret should never be printed'))
        with self.assertRaises(DownloadStopped) as ctx:
            self.load()
        self.assertEqual(ctx.exception.code, 'already_attempted')
        self.get.assert_called_once()

    def test_oversize_counts_detection_chunk_but_saves_no_xml(self):
        self.response(b'x' * 20000)
        with self.assertRaises(DownloadStopped) as ctx:
            self.load(cap=10000)
        self.assertEqual(ctx.exception.code, 'response_limit')
        ledger = DownloadBudget(self.root).snapshot()
        self.assertEqual(ledger['charged_bytes'], 16384)
        self.assertFalse((DownloadBudget(self.root).cache / 'probe.xml').exists())

    def test_interrupted_request_retains_reservation_and_stops_other_requests(self):
        self.get.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.load()
        ledger = DownloadBudget(self.root).snapshot()
        self.assertEqual(ledger['charged_bytes'], 4096 + CHUNK_BYTES)
        with self.assertRaisesRegex(DownloadStopped, 'interrupted'):
            DownloadBudget(self.root).load('other', 'destination', START, END, 'other.xml', 4096)
        self.get.assert_called_once()

    def test_wrong_window_or_changed_cache_rejected(self):
        self.load()
        cache = DownloadBudget(self.root).cache / 'probe.xml'
        cache.write_bytes(xml([(1, 200)]))
        with self.assertRaisesRegex(DownloadStopped, 'changed'):
            self.load()
        cache.write_bytes(xml([(1, 100)], period_start='2024-01-01T00:00Z', period_end='2024-01-01T01:00Z'))
        with self.assertRaises(EntsoeDataError):
            self.load()
        self.get.assert_called_once()

    def test_corrupt_ledger_fails_closed(self):
        budget = DownloadBudget(self.root)
        budget.path.write_text('{"version":1}')
        with self.assertRaises(DownloadStopped):
            self.load()
        self.get.assert_not_called()

    def test_concurrent_process_cannot_spend_budget(self):
        import fcntl
        budget = DownloadBudget(self.root)
        with budget.lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(DownloadStopped, 'Another'):
                self.load()
        self.get.assert_not_called()

    def test_missing_credentials_and_zero_limit_make_no_attempt(self):
        with self.assertRaises(DownloadStopped):
            self.load(cap=0)
        (self.root / '.streamlit/secrets.toml').unlink()
        with self.assertRaises(DownloadStopped):
            self.load()
        self.assertEqual(DownloadBudget(self.root).snapshot()['attempts'], 0)
        self.get.assert_not_called()

    def test_no_data_is_not_a_zero_flow(self):
        self.response(b'<Acknowledgement_MarketDocument><Reason><code>999</code></Reason></Acknowledgement_MarketDocument>')
        with self.assertRaises(DownloadStopped) as ctx:
            self.load()
        self.assertEqual(ctx.exception.code, 'no_data')
        self.assertFalse((DownloadBudget(self.root).cache / 'probe.xml').exists())


if __name__ == '__main__':
    unittest.main()
