"""Offline checks of weather-area matching, batching and explicit app downloads."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import matplotlib.pyplot as plt
from streamlit.testing.v1 import AppTest

from dashboard import load_data as nve
from dashboard import weather_data as weather
from dashboard import weather_views
from dashboard import reservoir_analysis as analysis
from test_nve_data import observation
from test_reservoir_views import fixtures

ROOT = Path(__file__).resolve().parents[1]


def hourly_frame():
    return pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=24, freq='h', tz='UTC'),
        'temperature_2m': [10.] * 24, 'precipitation': [1.] * 24,
        'point_count': [1000] * 24,
    })


class WeatherDataTests(unittest.TestCase):
    def test_area_mapping_does_not_treat_national_or_all_as_a_sample(self):
        self.assertEqual(weather.weather_region('EL', 3), 'NO3')
        self.assertEqual(weather.weather_region('VASS', 1), 'Øst')
        self.assertEqual(weather.weather_region('VASS', 2), 'Vest')
        self.assertEqual(weather.weather_region('VASS', 3), 'Nord')
        for kind, number in [('NO', 0), ('EL', None), ('VASS', 4)]:
            self.assertIsNone(weather.weather_region(kind, number))

    def test_unequal_batches_have_weighted_means_and_can_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'data/geography'
            folder.mkdir(parents=True)
            pd.DataFrame({
                'region': ['NO3'] * 3, 'point_id': [1, 2, 3],
                'latitude': [63., 64., 65.], 'longitude': [10., 11., 12.],
            }).to_csv(folder / 'weather_locations.csv', index=False)
            timestamps = pd.date_range('2024-01-01', periods=24, freq='h').astype(str).tolist()

            def result(value):
                return {
                    'hourly_units': {'temperature_2m': '°C', 'precipitation': 'mm'},
                    'hourly': {'time': timestamps, 'temperature_2m': [value] * 24,
                               'precipitation': [value / 10] * 24},
                }

            responses = [Mock(ok=True, status_code=200), Mock(ok=True, status_code=200)]
            responses[0].json.return_value = [result(10), result(20)]
            responses[1].json.return_value = [result(30)]
            with patch.object(weather, 'ROOT', root), patch.object(weather.time, 'sleep'), \
                    patch.object(weather.requests, 'post', side_effect=responses) as post:
                means = weather.download_weather('NO3', '2024-01-01', '2024-01-01', batch_size=2, hourly=True)
                self.assertEqual(post.call_count, 2)
                self.assertTrue(means.temperature_2m.eq(20).all())
                self.assertTrue(means.precipitation.eq(2).all())
                self.assertTrue(means.point_count.eq(3).all())
                post.side_effect = AssertionError('Unexpected repeated download')
                raw = weather.download_weather('NO3', '2024-01-01', '2024-01-01', batch_size=2)
                self.assertEqual(len(raw), 72)
                cached = weather.download_weather('NO3', '2024-01-01', '2024-01-01', hourly=True)
                pd.testing.assert_frame_equal(means, cached)

    def test_summary_rejects_incomplete_coverage(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(weather, 'ROOT', Path(directory)):
            path = weather.summary_path('NO3', '2024-01-01', '2024-01-01')
            path.parent.mkdir(parents=True)
            data = hourly_frame()
            data.loc[0, 'point_count'] = 999
            data.to_csv(path, index=False, compression='gzip')
            with self.assertRaisesRegex(ValueError, '1000 locations'):
                weather.read_weather_summary('NO3', '2024-01-01', '2024-01-01')
            data.iloc[:-1].to_csv(path, index=False, compression='gzip')
            with self.assertRaisesRegex(ValueError, 'timestamps'):
                weather.read_weather_summary('NO3', '2024-01-01', '2024-01-01')


class WeatherPageTests(unittest.TestCase):
    def setUp(self):
        nve.load_data.clear()
        nve.load_areas.clear()
        weather_views.load_weather_summary.clear()
        self.addCleanup(nve.load_data.clear)
        self.addCleanup(nve.load_areas.clear)
        self.addCleanup(weather_views.load_weather_summary.clear)
        rows, areas = fixtures()
        rows += [observation(dato_Id=date, omrType='EL', omrnr=3, fyllingsgrad=.4)
                 for date in ('2026-01-04T00:00:00', '2026-03-01T00:00:00')]
        self.enterContext(patch.object(nve, 'fetch_json', side_effect=lambda endpoint, _: (
            rows if endpoint == 'HentOffentligData' else areas, 2048)))
        self.enterContext(patch.object(nve.requests, 'get', side_effect=AssertionError('Live GET forbidden')))
        self.enterContext(patch.object(weather.requests, 'post', side_effect=AssertionError('Live POST forbidden')))
        self.read = self.enterContext(patch.object(weather_views, 'read_weather_summary',
            side_effect=lambda region, start, end: hourly_frame()
            if region == 'NO3' and start == '2024-01-01' else None))
        self.prepare = self.enterContext(patch.object(weather_views, 'prepare_weather_summary', return_value=hourly_frame()))

    def assert_ok(self, app):
        self.assertFalse(app.exception, [item.message for item in app.exception])

    def test_region_is_shared_and_changes_never_trigger_a_download(self):
        app = AppTest.from_file(str(ROOT / 'main.py')).run()
        app.switch_page('pages/1_Data_Table.py').run()
        app.selectbox(key='_nve_area_number_EL_table').set_value(3).run()
        self.assertEqual(app.dataframe[0].value['area_number'].tolist(), [3])
        app.switch_page('pages/4_Weather_Analysis.py').run()
        self.assert_ok(app)
        self.assertEqual(app.selectbox(key='_nve_area_number_EL_weather').value, 3)
        self.assertEqual(app.selectbox(key='_weather_year').value, 2024)
        self.assertTrue(app.button(key='download_weather').disabled)
        self.assertEqual(len(app.dataframe), 2)
        app.selectbox(key='_nve_area_number_EL_weather').set_value(2).run()
        self.assert_ok(app)
        self.assertFalse(app.dataframe)
        self.prepare.assert_not_called()
        app.selectbox(key='_weather_year').set_value(2023).run()
        self.prepare.assert_not_called()
        app.switch_page('pages/2_Data_Plot.py').run()
        self.assert_ok(app)
        self.assertEqual(app.selectbox(key='_nve_area_number_EL_plot').value, 2)
        app.switch_page('pages/4_Weather_Analysis.py').run()
        self.assertEqual(app.selectbox(key='_weather_year').value, 2023)
        app.button(key='download_weather').click().run()
        self.assert_ok(app)
        self.prepare.assert_called_once()
        self.assertEqual(self.prepare.call_args.args, ('NO2', '2023-01-01', '2023-12-31'))

    def test_all_and_national_selections_show_no_stale_weather(self):
        app = AppTest.from_file(str(ROOT / 'main.py')).run()
        app.switch_page('pages/4_Weather_Analysis.py').run()
        self.assert_ok(app)
        self.assertTrue(any('Choose a single area' in item.value for item in app.info))
        self.read.assert_not_called()
        app.radio[0].set_value('NO').run()
        self.assert_ok(app)
        self.assertFalse(app.dataframe)
        self.assertTrue(any('No weather sample' in item.value for item in app.info))
        self.prepare.assert_not_called()

    def test_analysis_tabs_match_notebook_results_and_controls_reuse_saved_data(self):
        # Use the small saved NO3 summary, with no API requests or raw point-data reads.
        self.read.side_effect = weather.read_weather_summary
        with patch.object(analysis, 'plot_temperature_spc', wraps=analysis.plot_temperature_spc) as spc, \
                patch.object(analysis, 'plot_temperature_lof', wraps=analysis.plot_temperature_lof) as lof:
            app = AppTest.from_file(str(ROOT / 'main.py')).run()
            app.session_state['nve_area_number_EL'] = 3
            app.switch_page('pages/4_Weather_Analysis.py').run()
            self.assert_ok(app)
            self.assertEqual([tab.label for tab in app.tabs], ['Outlier / SPC', 'Anomaly / LOF'])
            self.assertEqual(spc.call_args.kwargs, dict(cutoff_frequency=1/30, n_std=3.0))
            self.assertEqual(lof.call_args.kwargs, dict(outlier_fraction=.01))
            self.assertEqual(len(spc.call_args.args[0]), 8784)
            pd.testing.assert_series_equal(spc.call_args.args[0], lof.call_args.args[0])
            metrics = {item.label: item.value for item in app.metric}
            self.assertEqual(metrics['Outlier hours'], '15')
            self.assertEqual(metrics['Anomaly hours'], '88')
            self.assertEqual(len(app.dataframe[0].value), 15)
            self.assertEqual(app.dataframe[0].value.columns.tolist(),
                             ['time', 'temperature_c', 'lower_limit_c', 'upper_limit_c'])
            self.assertTrue(metrics['Robust standard deviation'].endswith('°C'))
            self.assertEqual(len(app.dataframe[1].value), 88)
            self.assertEqual(str(app.dataframe[0].value.time.dt.tz), 'UTC')
            self.assertTrue(app.dataframe[0].value.time.isin(spc.call_args.args[0].index).all())
            self.assertFalse(plt.get_fignums())

            app.number_input(key='spc_deviations').set_value(4.).run()
            self.assert_ok(app)
            self.assertLess(len(app.dataframe[0].value), 15)
            app.number_input(key='spc_cutoff').set_value(.1).run()
            self.assertEqual(spc.call_args.kwargs, dict(cutoff_frequency=.1, n_std=4.0))
            app.number_input(key='lof_percentage').set_value(2.).run()
            self.assert_ok(app)
            self.assertEqual(lof.call_args.kwargs, dict(outlier_fraction=.02))
            self.assertEqual(len(app.dataframe[1].value), 176)
            self.prepare.assert_not_called()
            self.assertEqual(self.read.call_count, 1, 'Analysis changes must reuse the weather cache')

            app.selectbox(key='_nve_area_number_EL_weather').set_value(2).run()
            self.assert_ok(app)
            self.assertFalse(app.tabs)
            self.assertFalse(app.dataframe)
            self.prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
