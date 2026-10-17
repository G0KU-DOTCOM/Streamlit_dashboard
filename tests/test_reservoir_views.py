"""Offline checks of area isolation, missing weeks and multipage selections."""
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import load_data as nve
from dashboard.reservoir_views import ReservoirSelection, area_lines, area_summary
from test_nve_data import observation

ROOT = Path(__file__).resolve().parents[1]


def fixtures():
    rows = []
    for date in ('2026-01-04T00:00:00', '2026-03-01T00:00:00'):
        for kind, number, value in [('NO', 0, .5), ('EL', 1, .2), ('EL', 2, .8), ('VASS', 1, .6)]:
            rows.append(observation(dato_Id=date, omrType=kind, omrnr=number, fyllingsgrad=value))
    areas = [{key: [dict(omrType=kind, omrnr=number, navn=f'{kind}{number}', beskrivelse='Fixture')
                    for number in numbers]
              for key, kind, numbers in [('land', 'NO', [0]), ('elspot', 'EL', [1, 2, 3]), ('vassdrag', 'VASS', [1])]}]
    return rows, areas


class ReservoirViewsTests(unittest.TestCase):
    def setUp(self):
        nve.load_data.clear()
        nve.load_areas.clear()
        rows, areas = fixtures()
        def fetch(endpoint, max_bytes):
            if endpoint == 'HentOffentligData': return rows, 2048
            if endpoint == 'HentOmråder': return areas, 512
            raise AssertionError(f'Unexpected API request: {endpoint}')
        self.fetch = self.enterContext(patch.object(nve, 'fetch_json', side_effect=fetch))
        # A missed mock must never make a live API call from a test.
        self.enterContext(patch.object(nve.requests, 'get', side_effect=AssertionError('Live request forbidden')))
        self.addCleanup(nve.load_data.clear)
        self.addCleanup(nve.load_areas.clear)

    def assert_ok(self, app):
        self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_area_values_missing_weeks_and_missing_area(self):
        history = nve.prepare_history(fixtures()[0])
        data = history.loc[history.area_type.eq('EL') & history.observation_date.dt.month.eq(1)]
        selection = ReservoirSelection(history, data, 'EL', '2026-01', '2026-01', {1: 'EL1', 2: 'EL2', 3: 'EL3'})
        lines = area_lines(selection, 'filling_fraction')
        self.assertEqual(lines.loc['2026-01-04', 'EL1'], .2)
        self.assertEqual(lines.loc['2026-01-04', 'EL2'], .8)
        self.assertTrue(lines.loc['2026-01-11'].isna().all())
        self.assertTrue(lines['EL3'].isna().all())
        summary = area_summary(selection).set_index('area_number')
        self.assertEqual(summary.loc[3, 'observations'], 0)
        self.assertEqual(summary.loc[1, 'filling_fraction'], [.2])
        self.assertIsNone(summary.loc[3, 'filling_fraction'])
        # The two real observations have missing weeks between them: keep the
        # dated plot's gaps and suppress its sparkline instead of joining them.
        selection.data = history.loc[history.area_type.eq('EL')]
        selection.end = '2026-03'
        gapped = area_summary(selection).set_index('area_number')
        self.assertIsNone(gapped.loc[1, 'filling_fraction'])

    def test_navigation_preserves_selection_and_reuses_downloads(self):
        app = AppTest.from_file(str(ROOT/'main.py')).run()
        app.switch_page('pages/1_Data_Table.py').run()
        self.assert_ok(app)
        self.assertEqual(app.dataframe[0].value['area_number'].tolist(), [1, 2, 3])
        app.select_slider[0].set_value(('2026-01', '2026-01')).run()
        app.radio[0].set_value('VASS').run()
        self.assertEqual(app.dataframe[0].value['area_number'].tolist(), [1])
        self.assertEqual(app.dataframe[0].value['observations'].tolist(), [1])
        app.switch_page('pages/2_Data_Plot.py').run()
        self.assert_ok(app)
        self.assertEqual(app.radio[0].value, 'VASS')
        self.assertEqual(tuple(app.select_slider[0].value), ('2026-01', '2026-01'))
        for column in app.selectbox[0].options:
            app.selectbox[0].set_value(column).run()
            self.assert_ok(app)
        app.radio[0].set_value('NO').run()
        # Visit pages without widgets: their cleanup must not discard selection.
        app.switch_page('pages/3_Reservoir_API.py').run()
        self.assert_ok(app)
        app.switch_page('pages/5_About.py').run()
        self.assert_ok(app)
        app.switch_page('pages/1_Data_Table.py').run()
        self.assert_ok(app)
        self.assertEqual(app.radio[0].value, 'NO')
        self.assertEqual(tuple(app.select_slider[0].value), ('2026-01', '2026-01'))
        self.assertEqual(app.dataframe[0].value['area_number'].tolist(), [0])
        self.assertEqual(self.fetch.call_count, 2)
        # February is a real empty interval, not an automatic fallback to January.
        app.select_slider[0].set_value(('2026-02', '2026-02')).run()
        self.assert_ok(app)
        self.assertTrue(any('There are no observations' in x.value for x in app.info))

    def test_metadata_failure_keeps_numeric_area_labels(self):
        rows, _ = fixtures()
        def fetch(endpoint, max_bytes):
            if endpoint == 'HentOffentligData': return rows, 2048
            raise nve.NVEDataError('Area metadata unavailable')
        self.fetch.side_effect = fetch
        app = AppTest.from_file(str(ROOT/'main.py')).run()
        app.switch_page('pages/1_Data_Table.py').run()
        self.assert_ok(app)
        self.assertEqual(app.dataframe[0].value['area'].tolist(), ['EL1', 'EL2'])
        self.assertTrue(app.warning)

    def test_single_month_history(self):
        rows, areas = fixtures()
        self.fetch.side_effect = lambda endpoint, max_bytes: (
            [r for r in rows if r['dato_Id'].startswith('2026-01')] if endpoint == 'HentOffentligData' else areas, 1024)
        app = AppTest.from_file(str(ROOT/'main.py')).run()
        app.switch_page('pages/1_Data_Table.py').run()
        self.assert_ok(app)
        self.assertEqual(tuple(app.select_slider[0].value), ('2026-01', '2026-01'))


if __name__ == '__main__':
    unittest.main()
