"""Check the new state bridge and the time rules used by the live interface."""

from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard import load_data as nve
from dashboard.geography import area_from_map_click, load_geometry
from dashboard.weekly import weekly_weather, prepare_weather_scenario
from test_nve_data import observation

ROOT = Path(__file__).resolve().parents[1]


class WeeklyAppTests(unittest.TestCase):
    def test_autumn_week_counts_169_hours_and_uses_previous_precipitation_hour(self):
        stamps = pd.date_range("2024-10-20 21:00Z", "2024-10-28 01:00Z", freq="h")
        data = pd.DataFrame({"time": stamps, "temperature_2m": 10., "precipitation": 1.})
        weekly = weekly_weather(data)
        self.assertEqual(weekly.loc["2024-10-27", "temperature_c"], 10.)
        self.assertEqual(weekly.loc["2024-10-27", "precipitation_mm"], 169.)
        # Rain stamped Monday 00:00 local belongs to the preceding Sunday.
        data.loc[data.time.eq(pd.Timestamp("2024-10-27 23:00Z")), "precipitation"] = 7.
        self.assertEqual(weekly_weather(data).loc["2024-10-27", "precipitation_mm"], 175.)

    def test_scenario_is_unchanged_by_weather_after_its_cutoff(self):
        dates = pd.date_range("2022-12-25", periods=170, freq="W-SUN", name="observation_date")
        weather = pd.DataFrame({"temperature_c": np.arange(170.), "precipitation_mm": 3.}, index=dates)
        training = dates[1:105]
        future = dates[105:117]
        expected = prepare_weather_scenario(weather, training, future)
        weather.loc[weather.index >= training[-1]] = 9999
        actual = prepare_weather_scenario(weather, training, future)
        for left, right in zip(expected, actual):
            if isinstance(left, pd.DataFrame):
                pd.testing.assert_frame_equal(left, right)
            else:
                pd.testing.assert_series_equal(left, right)

    def test_map_clicks_choose_the_covering_region_and_ignore_ocean(self):
        from shapely.geometry import shape
        feature = next(item for item in load_geometry("EL")["features"] if item["properties"]["region"] == "NO4")
        point = shape(feature["geometry"]).representative_point()
        self.assertEqual(area_from_map_click({"last_clicked": {"lat": point.y, "lng": point.x}}, "EL"), 4)
        self.assertIsNone(area_from_map_click({"last_clicked": {"lat": 0, "lng": 0}}, "EL"))
        self.assertIsNone(area_from_map_click({}, "EL"))


class ForecastPageTests(unittest.TestCase):
    def test_home_cutoff_and_horizon_are_used_by_the_real_forecast(self):
        dates = pd.date_range("2021-01-03", "2024-12-29", freq="W-SUN")
        rows = [observation(dato_Id=day.isoformat(), omrType=kind, omrnr=number,
                            fyllingsgrad=.6 + .15 * np.sin(i * 2 * np.pi / 52))
                for i, day in enumerate(dates) for kind, number in [("NO", 0), ("EL", 1), ("EL", 3)]]
        metadata = [{"land": [dict(omrType="NO", omrnr=0, navn="Norway", beskrivelse="")],
                     "elspot": [dict(omrType="EL", omrnr=i, navn=f"NO{i}", beskrivelse="") for i in [1, 3]], "vassdrag": []}]
        nve.load_data.clear()
        nve.load_areas.clear()
        self.addCleanup(nve.load_data.clear)
        self.addCleanup(nve.load_areas.clear)
        with patch.object(nve, "fetch_json", side_effect=lambda endpoint, _: (
            rows if endpoint == "HentOffentligData" else metadata, 2048,
        )), patch.object(nve.requests, "get", side_effect=AssertionError("Live request forbidden")):
            app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=15).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["nve_area_number_EL"], 3)
            app.date_input(key="_forecast_end_home").set_value(pd.Timestamp("2024-10-06").date()).run()
            app.number_input(key="_forecast_horizon_home").set_value(4).run()
            app.switch_page("pages/8_Forecast.py").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.date_input(key="_forecast_end_forecast").value, pd.Timestamp("2024-10-06").date())
            self.assertEqual(app.number_input(key="_forecast_horizon_forecast").value, 4)
            next(button for button in app.button if button.label == "Run forecast").click().run()
            self.assertFalse(app.exception, [item.message for item in app.exception])
            _, (training, prediction, observed, _) = app.session_state["forecast_result"]
            self.assertEqual(training.index[-1], pd.Timestamp("2024-10-06"))
            self.assertEqual(prediction.index[-1], pd.Timestamp("2024-11-03"))
            self.assertEqual(len(training), 104)
            self.assertTrue(observed.notna().all())
            self.assertEqual(len(app.metric), 3)
            app.number_input(key="_forecast_order_p").set_value(3).run()
            app.switch_page("pages/7_About.py").run()
            app.switch_page("pages/8_Forecast.py").run()
            self.assertEqual(app.number_input(key="_forecast_order_p").value, 3)
            app.switch_page("pages/0_Home.py").run()
            app.session_state["nve_area_number_EL"] = 1  # external map selection
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key="_nve_area_number_EL_home").value, 1)
