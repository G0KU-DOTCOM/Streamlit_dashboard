"""Offline checks of VASS selection, map values and complete weekly weather."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import folium
import pandas as pd
from shapely.geometry import shape
from streamlit.testing.v1 import AppTest

from dashboard import load_data as nve
from dashboard import map_weather
from dashboard import weather_data
from dashboard.geography import area_from_map_click, area_map, feature_number, load_geometry
from test_nve_data import observation
from test_reservoir_views import fixtures

ROOT = Path(__file__).resolve().parents[1]


class MapTests(unittest.TestCase):
    def test_vass_polygons_have_distinct_clickable_interiors(self):
        features = load_geometry("VASS")["features"]
        self.assertEqual([feature_number(f) for f in features], [1, 2, 3])
        polygons = [shape(f["geometry"]) for f in features]
        for number, polygon in enumerate(polygons, 1):
            self.assertTrue(polygon.is_valid and not polygon.is_empty)
            point = polygon.representative_point()
            self.assertEqual(area_from_map_click({"last_clicked": {"lat": point.y, "lng": point.x}}, "VASS"), number)
        for i, polygon in enumerate(polygons):
            for other in polygons[i + 1:]:
                self.assertLess(polygon.intersection(other).area, 1e-10)
        self.assertIsNone(area_from_map_click({"last_clicked": {"lat": 0, "lng": 0}}, "VASS"))

    def test_vass_values_and_highlight_use_vass_numbers_not_price_areas(self):
        history = pd.DataFrame({
            "area_type": ["VASS"] * 3 + ["EL"], "area_number": [1, 2, 3, 2],
            "observation_date": pd.to_datetime(["2024-10-27"] * 4),
            "filling_fraction": [.4, .7, .9, .1],
        })
        result = area_map(history, "VASS", 2, "2024-10-27", "Filling (%)")
        layer = next(child for child in result._children.values() if isinstance(child, folium.GeoJson))
        features = layer.data["features"]
        self.assertEqual([f["properties"]["map_value"] for f in features], ["40.00 %", "70.00 %", "90.00 %"])
        self.assertEqual([layer.style_function(f)["weight"] for f in features], [1, 3, 1])
        weather = {1: {"temperature_c": -5}, 2: {"temperature_c": 0}}
        result = area_map(history, "VASS", 2, "2024-10-27", "Temperature (°C)", weather)
        layer = next(child for child in result._children.values() if isinstance(child, folium.GeoJson))
        self.assertEqual(layer.data["features"][0]["properties"]["map_value"], "-5.00 °C")
        self.assertEqual(layer.style_function(layer.data["features"][2])["fillColor"], "#d8dee7")
        self.assertTrue(any(getattr(child, "caption", None) == "Temperature (°C)"
                            for child in result._children.values()))
        missing = area_map(history, "VASS", 2, "2024-10-27", "Temperature (°C)", {})
        self.assertFalse(any(getattr(child, "caption", None) == "Temperature (°C)"
                             for child in missing._children.values()))


class MapWeatherTests(unittest.TestCase):
    def setUp(self):
        map_weather.map_weather_values.clear()
        self.addCleanup(map_weather.map_weather_values.clear)
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        (self.root / "data/weather").mkdir(parents=True)
        self.enterContext(patch.object(map_weather, "ROOT", self.root))

    def save(self, name, count, temperature, *, partial=False):
        # Includes both UTC edges of Oslo's 169-hour autumn transition week.
        stamps = pd.date_range("2024-10-20 00:00Z", "2024-10-28 00:00Z", freq="h")
        frame = pd.DataFrame({"time": stamps, "temperature_2m": temperature,
                              "precipitation": 1., "point_count": count})
        if partial:
            frame = frame.loc[frame.time.ne(pd.Timestamp("2024-10-24 10:00Z"))]
        frame.to_csv(self.root / "data/weather" / name, index=False, compression="gzip")

    def test_largest_complete_sample_wins_and_incomplete_week_is_not_blended(self):
        self.save("Øst_era5_sample_hourly_sample100.csv.gz", 100, 5.)
        self.save("Øst_era5_full_hourly.csv.gz", 1000, 10., partial=True)
        values = map_weather.map_weather_values("VASS", "2024-10-27")
        self.assertEqual(values, {1: {"temperature_c": 5., "precipitation_mm": 169., "point_count": 100}})
        self.save("Øst_era5_full_hourly.csv.gz", 1000, 10.)
        map_weather.map_weather_values.clear()
        values = map_weather.map_weather_values("VASS", "2024-10-27")
        self.assertEqual(values[1]["temperature_c"], 10.)
        self.assertEqual(values[1]["point_count"], 1000)

    def test_missing_weather_does_not_download_or_invent_values(self):
        with patch.object(weather_data.requests, "post", side_effect=AssertionError("Unexpected download")):
            self.assertEqual(map_weather.map_weather_values("VASS", "2024-10-27"), {})
            self.assertEqual(map_weather.map_weather_values("NO", "2024-10-27"), {})

    def test_request_dates_cover_oslo_week_and_precipitation_end_timestamp(self):
        for week in ["2024-03-31", "2024-10-27", "2024-12-29"]:
            start, end = map_weather.weather_request_dates(week)
            requested = pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(days=1), freq="h", inclusive="left", tz="UTC")
            sunday = pd.Timestamp(week)
            local_start = (sunday - pd.Timedelta(days=6)).tz_localize("Europe/Oslo").tz_convert("UTC")
            local_end = (sunday + pd.Timedelta(days=1)).tz_localize("Europe/Oslo").tz_convert("UTC")
            self.assertIn(local_start, requested)
            self.assertIn(local_end, requested)


class HomeMapTests(unittest.TestCase):
    def setUp(self):
        nve.load_data.clear()
        nve.load_areas.clear()
        self.addCleanup(nve.load_data.clear)
        self.addCleanup(nve.load_areas.clear)
        rows, areas = fixtures()
        rows += [observation(dato_Id="2026-03-01T00:00:00", omrType="VASS", omrnr=i, fyllingsgrad=.7)
                 for i in [2, 3]]
        areas[0]["vassdrag"] += [dict(omrType="VASS", omrnr=i, navn=f"VASS{i}", beskrivelse="Fixture") for i in [2, 3, 4]]
        self.enterContext(patch.object(nve, "fetch_json", side_effect=lambda endpoint, _: (
            rows if endpoint == "HentOffentligData" else areas, 2048)))
        self.enterContext(patch.object(nve.requests, "get", side_effect=AssertionError("Unexpected GET")))
        self.enterContext(patch.object(weather_data.requests, "post", side_effect=AssertionError("Unexpected POST")))
        self.map_event = self.enterContext(patch("streamlit_folium.st_folium", return_value={}))
        self.prepare = self.enterContext(patch.object(weather_data, "prepare_weather_summary"))
        self.values = self.enterContext(patch.object(map_weather, "map_weather_values", return_value={}))

    def app(self):
        app = AppTest.from_file(str(ROOT / "main.py"), default_timeout=15).run()
        app.radio(key="_nve_area_type_home").set_value("VASS").run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_vass_default_and_map_click_are_shared_with_other_pages(self):
        app = self.app()
        self.assertEqual(app.selectbox(key="_nve_area_number_VASS_home").value, 1)
        point = shape(load_geometry("VASS")["features"][1]["geometry"]).representative_point()
        self.map_event.return_value = {"last_clicked": {"lat": point.y, "lng": point.x}}
        app.run()
        self.assertEqual(app.selectbox(key="_nve_area_number_VASS_home").value, 2)
        app.switch_page("pages/1_Data_Table.py").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="_nve_area_number_VASS_table").value, 2)
        self.prepare.assert_not_called()

    def test_weather_download_is_explicit_and_vass4_has_useful_feedback(self):
        app = self.app()
        app.selectbox(key="map_measure").set_value("Temperature (°C)").run()
        self.assertFalse(app.exception)
        self.prepare.assert_not_called()
        app.button(key="map_weather_download").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(self.prepare.call_args.args, ("Øst", "2026-02-22", "2026-03-01"))
        self.prepare.assert_called_once()
        app.selectbox(key="_nve_area_number_VASS_home").set_value(4).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("No filling observation" in item.value for item in app.info))
        self.assertTrue(any("VASS4" in item.value for item in app.info))
        self.assertFalse(any(button.key == "map_weather_download" for button in app.button))


if __name__ == "__main__":
    unittest.main()
