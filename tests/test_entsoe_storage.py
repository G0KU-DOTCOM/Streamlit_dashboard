import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from entsoe_storage import check_capacity, measure_storage, storage_lock, StorageStopped, WORKING_RESERVE, BYTES_PER_NEW_ROW


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.limits = json.loads(Path('entsoe_plan.json').read_text())['planned_limits']
        self.snapshot = {'volume_allocated_bytes': 3 * 1024**2,
                         'host_free_bytes': 20 * 1024**3, 'docker_free_bytes': 20 * 1024**3}

    def check(self, current=29020, new=100, batch=100):
        return check_capacity(self.snapshot, current_rows=current, new_rows=new,
                              batch_rows=batch, limits=self.limits)

    def test_headroom_accounts_for_existing_data_and_working_files(self):
        result = self.check()
        self.assertEqual(result['projected_rows'], 29120)
        self.assertEqual(result['reserved_bytes'], WORKING_RESERVE + 100 * BYTES_PER_NEW_ROW + 3 * 1024**2)

    def test_unchanged_snapshot_does_not_count_as_new_rows(self):
        result = self.check(current=1300000, new=0, batch=29020)
        self.assertEqual(result['projected_rows'], 1300000)
        self.assertEqual(result['reserved_bytes'], 0)

    def test_cumulative_rows_stop_at_actual_total(self):
        with self.assertRaisesRegex(StorageStopped, 'raw-row'):
            self.check(current=1299950)

    def test_batch_limit(self):
        with self.assertRaisesRegex(StorageStopped, 'batch'):
            self.check(new=100001, batch=100001)

    def test_volume_headroom_rejects_before_volume_is_full(self):
        self.snapshot['volume_allocated_bytes'] = 600 * 1024**2
        with self.assertRaisesRegex(StorageStopped, 'headroom'):
            self.check()

    def test_full_volume_rejects_even_no_new_rows(self):
        self.snapshot['volume_allocated_bytes'] = self.limits['max_cassandra_volume_bytes']
        with self.assertRaises(StorageStopped):
            self.check(new=0)

    def test_both_host_and_docker_free_space_checked(self):
        for key in ['host_free_bytes', 'docker_free_bytes']:
            with self.subTest(key=key):
                old = self.snapshot[key]
                self.snapshot[key] = self.limits['min_host_free_bytes']
                with self.assertRaises(StorageStopped):
                    self.check()
                self.snapshot[key] = old

    def test_invalid_counts(self):
        for current,new,batch in [(-1,0,1),(0,2,1),(0,1.5,2)]:
            with self.assertRaises(StorageStopped):
                self.check(current,new,batch)

    def test_stopped_container_fails_closed(self):
        with patch('entsoe_storage._docker', return_value='[{"State":{"Running":false}}]') as docker:
            with self.assertRaises(StorageStopped):
                measure_storage(Path.cwd())
            docker.assert_called_once()

    def test_running_container_with_stopped_transport_is_rejected(self):
        details = [{'State': {'Running': True}, 'Mounts': [
            {'Destination': '/var/lib/cassandra', 'RW': True}]}]
        with patch('entsoe_storage._docker', side_effect=[json.dumps(details), 'not running']):
            with self.assertRaisesRegex(StorageStopped, 'transport'):
                measure_storage(Path.cwd())

    def test_competing_writers_block(self):
        with tempfile.TemporaryDirectory() as directory:
            with storage_lock(directory):
                with self.assertRaises(StorageStopped):
                    with storage_lock(directory):
                        pass


if __name__ == '__main__':
    unittest.main()
