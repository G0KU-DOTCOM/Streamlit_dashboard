"""Regression checks for weekly date alignment and forecast data leakage."""

import unittest

import numpy as np
import pandas as pd
from river import time_series

from dashboard.forecasting import forecast_reservoir_snarimax


class ReservoirForecastTests(unittest.TestCase):
    def setUp(self):
        dates = pd.date_range("2023-01-08", periods=156, freq="W-SUN")
        self.history = pd.DataFrame({
            "observation_date": dates,
            "area_type": "EL",
            "area_number": 3,
            "filling_fraction": 0.6 + 0.2 * np.sin(np.arange(len(dates)) * 2 * np.pi / 52),
        })
        self.kwargs = dict(
            area_type="EL", area_number=3, train_start="2023-01-08", train_end="2025-10-05",
            horizon=12, p=3, d=1, q=3,
        )

    def test_matches_the_course_loop_and_ignores_other_areas_and_future_values(self):
        training, forecast = forecast_reservoir_snarimax(self.history, **self.kwargs)
        self.assertEqual(len(training), 144)
        self.assertEqual(forecast.index[0], pd.Timestamp("2025-10-12"))
        self.assertEqual(forecast.index[-1], pd.Timestamp("2025-12-28"))
        self.assertTrue(np.isfinite(forecast).all())

        model = time_series.SNARIMAX(p=3, d=1, q=3)
        for value in training:
            model.learn_one(float(value))
        np.testing.assert_allclose(forecast, model.forecast(horizon=12))

        changed = self.history.copy()
        changed.loc[changed["observation_date"] > self.kwargs["train_end"], "filling_fraction"] = 999
        other_area = self.history.assign(area_number=2, filling_fraction=-999)
        changed = pd.concat([changed, other_area]).sample(frac=1, random_state=320)
        _, second = forecast_reservoir_snarimax(changed, **self.kwargs)
        pd.testing.assert_series_equal(forecast, second)

    def test_rejects_missing_weeks_duplicate_dates_and_missing_values(self):
        missing = self.history.drop(index=40)
        duplicate = pd.concat([self.history, self.history.iloc[[40]]])
        invalid = self.history.copy()
        invalid.loc[40, "filling_fraction"] = np.nan
        for history, message in (
            (missing, "consecutive, unique"), (duplicate, "consecutive, unique"),
            (invalid, "missing or invalid"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    forecast_reservoir_snarimax(history, **self.kwargs)

    def test_seasonal_orders_and_training_length_are_respected(self):
        _, forecast = forecast_reservoir_snarimax(
            self.history, **{**self.kwargs, "m": 52, "sd": 1, "sp": 1},
        )
        self.assertEqual(len(forecast), 12)
        self.assertTrue(np.isfinite(forecast).all())
        with self.assertRaisesRegex(ValueError, "require more training observations"):
            forecast_reservoir_snarimax(
                self.history, **{**self.kwargs, "train_end": "2023-12-31", "m": 52, "sd": 1},
            )

    def test_rejects_invalid_periods_and_orders(self):
        for overrides, message in (
            ({"horizon": 0}, "horizon"), ({"p": 1.5}, "p must be an integer"),
            ({"m": 0}, "m must be an integer"), ({"d": True}, "d must be an integer"),
            ({"train_start": "2026-01-01"}, "start must be on or before"),
            ({"area_number": 99}, "No reservoir observations"),
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, message):
                    forecast_reservoir_snarimax(self.history, **{**self.kwargs, **overrides})
