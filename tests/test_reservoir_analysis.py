"""Offline integration checks for shared areas and the two analysis tabs."""
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import load_data as nve
from dashboard import reservoir_analysis as analysis
from test_nve_data import observation

ROOT = Path(__file__).resolve().parents[1]


class ReservoirAnalysisTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range('2018-01-07', '2023-12-31', freq='W-SUN')
        rows = []
        for index, date in enumerate(dates):
            for kind, number, baseline in [('NO', 0, .5), ('EL', 1, .4), ('EL', 3, .6)]:
                rows.append(observation(
                    dato_Id=date.isoformat(), omrType=kind, omrnr=number,
                    fyllingsgrad=baseline + .1 * np.sin(2 * np.pi * index / 52),
                ))
        self.rows = rows
        self.history = nve.prepare_history(rows)
        nve.load_data.clear()
        nve.load_areas.clear()
        self.addCleanup(nve.load_data.clear)
        self.addCleanup(nve.load_areas.clear)
        metadata = [{
            key: [dict(omrType=kind, omrnr=number, navn=name, beskrivelse='Fixture')
                  for number, name in entries]
            for key, kind, entries in [
                ('land', 'NO', [(0, 'Norway')]),
                ('elspot', 'EL', [(1, 'NO1'), (3, 'NO3')]),
                ('vassdrag', 'VASS', [(4, 'Missing region')]),
            ]
        }]
        self.enterContext(patch.object(nve, 'fetch_json', side_effect=lambda endpoint, _: (
            self.rows if endpoint == 'HentOffentligData' else metadata, 2048,
        )))
        self.enterContext(patch.object(nve.requests, 'get', side_effect=AssertionError('Live GET forbidden')))
        self.enterContext(patch.object(nve.requests, 'post', side_effect=AssertionError('Live POST forbidden')))
        self.stl = self.enterContext(patch.object(analysis, 'plot_reservoir_stl', wraps=analysis.plot_reservoir_stl))
        self.spectrum = self.enterContext(patch.object(
            analysis, 'plot_reservoir_spectrogram', wraps=analysis.plot_reservoir_spectrogram,
        ))
        self.addCleanup(plt.close, 'all')

    def assert_ok(self, app):
        self.assertFalse(app.exception, [item.message for item in app.exception])

    def test_shared_area_defaults_and_both_tabs_use_the_same_weekly_series(self):
        app = AppTest.from_file(str(ROOT / 'main.py')).run()
        app.switch_page('pages/1_Data_Table.py').run()
        app.selectbox(key='_nve_area_number_EL_table').set_value(3).run()
        app.switch_page('pages/7_Reservoir_Analysis.py').run()
        self.assert_ok(app)
        self.assertEqual(app.selectbox(key='_nve_area_number_EL_analysis').value, 3)
        self.assertEqual([tab.label for tab in app.tabs], ['STL', 'Spectrogram'])
        self.assertEqual(tuple(app.select_slider[0].value), (2018, 2023))
        self.assertEqual(self.stl.call_args.kwargs, dict(seasonal=13, trend=89, robust=True))
        self.assertEqual(self.spectrum.call_args.kwargs, dict(window_length=156, window_overlap=78))
        series = self.stl.call_args.args[0]
        pd.testing.assert_series_equal(series, self.spectrum.call_args.args[0])
        self.assertAlmostEqual(series.iloc[0], .6)
        self.assertFalse(plt.get_fignums(), 'Reruns must not leave figures open')

        for label, value in [('Seasonal smoother', 7), ('Trend smoother (weeks)', 121)]:
            next(item for item in app.number_input if item.label == label).set_value(value).run()
        app.checkbox[0].uncheck().run()
        self.assert_ok(app)
        self.assertEqual(self.stl.call_args.kwargs, dict(seasonal=7, trend=121, robust=False))
        app.number_input(key='spectrum_window').set_value(104).run()
        app.number_input(key='spectrum_overlap').set_value(52).run()
        self.assertEqual(self.spectrum.call_args.kwargs, dict(window_length=104, window_overlap=52))
        app.select_slider[0].set_value((2020, 2022)).run()
        self.assert_ok(app)
        self.assertEqual(set(self.stl.call_args.args[0].index.year), {2020, 2021, 2022})
        app.selectbox(key='_nve_area_number_EL_analysis').set_value(1).run()
        self.assertAlmostEqual(self.stl.call_args.args[0].iloc[0], .4)
        app.switch_page('pages/2_Data_Plot.py').run()
        self.assert_ok(app)
        self.assertEqual(app.selectbox(key='_nve_area_number_EL_plot').value, 1)

    def test_short_period_missing_weeks_and_window_changes_are_safe(self):
        app = AppTest.from_file(str(ROOT / 'main.py')).run()
        app.session_state['nve_area_number_EL'] = 3
        app.switch_page('pages/7_Reservoir_Analysis.py').run()
        app.number_input(key='spectrum_window').set_value(20).run()
        self.assert_ok(app)
        self.assertEqual(app.number_input(key='spectrum_overlap').value, 19)
        app.select_slider[0].set_value((2023, 2023)).run()
        self.assert_ok(app)
        self.assertTrue(any('at least two' in item.value for item in app.info))
        app.select_slider[0].set_value((2018, 2023)).run()
        # Both methods must reject a missing week instead of silently filling it.
        self.rows = [row for row in self.rows if row['dato_Id'] != '2020-06-07T00:00:00']
        nve.load_data.clear()
        app.run()
        self.assert_ok(app)
        self.assertEqual(sum('consecutive, unique weekly' in item.value for item in app.info), 2)

    def test_all_areas_and_area_without_data_do_not_produce_combined_analyses(self):
        app = AppTest.from_file(str(ROOT / 'main.py')).run()
        app.switch_page('pages/7_Reservoir_Analysis.py').run()
        self.assert_ok(app)
        self.assertTrue(any('Choose one area' in item.value for item in app.info))
        self.stl.assert_not_called()
        self.spectrum.assert_not_called()
        app.radio[0].set_value('VASS').run()
        self.assert_ok(app)
        self.assertTrue(any('no filling observations' in item.value for item in app.info))
        self.stl.assert_not_called()

    def test_single_spectrum_window_has_visible_time_width(self):
        series = self.history.loc[self.history.area_type.eq('NO')].set_index('observation_date').filling_fraction.iloc[:52]
        figure = analysis.plot_reservoir_spectrogram(series, window_length=52, window_overlap=26)
        mesh = figure.axes[0].collections[0]
        self.assertEqual(mesh.get_array().shape[1], 1)
        self.assertGreater(np.ptp(mesh.get_coordinates()[0, :, 0]), 0)
        plt.close(figure)


if __name__ == '__main__':
    unittest.main()
