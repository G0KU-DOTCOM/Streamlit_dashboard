"""Offline checks for data correctness and bounded API traffic."""
import json
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import requests

import load_data as nve


def observation(**changes):
    row = dict(zip(nve.ENGLISH_NAMES, [
        "2026-01-04T00:00:00", "NO", 0, 2026, 1, 1.02, 87.4, 89.148,
        "0001-01-01T00:00:00", 0.99, 0.03,
    ]))
    return row | changes


class NVEDataTests(unittest.TestCase):
    def tearDown(self):
        nve.load_data.clear()
        nve.load_areas.clear()

    def response(self, chunks):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = iter(chunks)
        return response

    def test_size_boundary_and_connection_closed(self):
        response = self.response([b'[', b'{}', b']'])
        with patch.object(nve.requests, 'get', return_value=response):
            self.assertEqual(nve.fetch_json('test', 4), ([{}], 4))
        response.__exit__.assert_called_once()

        response = self.response([b'[', b'{}', b']', b'never read'])
        with patch.object(nve.requests, 'get', return_value=response):
            with self.assertRaisesRegex(nve.NVEDataError, 'size limit'):
                nve.fetch_json('test', 3)
        response.__exit__.assert_called_once()
        self.assertEqual(next(response.iter_content.return_value), b'never read')

    def test_network_and_invalid_json_errors(self):
        with patch.object(nve.requests, 'get', side_effect=requests.Timeout):
            with self.assertRaises(nve.NVEDataError):
                nve.fetch_json('test', 100)
        with patch.object(nve.requests, 'get', return_value=self.response([b'<html>'])):
            with self.assertRaises(nve.NVEDataError):
                nve.fetch_json('test', 100)

    def test_dates_and_above_capacity_values(self):
        frame = nve.prepare_history([observation()])
        self.assertTrue(pd.isna(frame.loc[0, 'next_publication_date']))
        self.assertEqual(frame.loc[0, 'filling_fraction'], 1.02)
        self.assertEqual(frame.loc[0, 'observation_date'], pd.Timestamp('2026-01-04'))

    def test_missing_schema_and_duplicate_rows_are_rejected(self):
        for records in ([], [{}], [observation(), observation()], [observation(dato_Id=None)]):
            with self.subTest(records=records):
                with self.assertRaises(nve.NVEDataError):
                    nve.prepare_history(records)

    def test_cache_avoids_repeated_downloads_and_returns_independent_data(self):
        nve.load_data.clear()
        raw = [observation()]
        with patch.object(nve, 'fetch_json', return_value=(raw, len(json.dumps(raw)))) as fetch:
            first = nve.load_data()
            first.loc[0, 'filling_fraction'] = 0
            second = nve.load_data()
            self.assertEqual(second.loc[0, 'filling_fraction'], 1.02)
            fetch.assert_called_once_with('HentOffentligData', nve.MAX_HISTORY_BYTES)


if __name__ == '__main__':
    unittest.main()
