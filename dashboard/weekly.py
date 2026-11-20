"""Oslo calendar-week alignment and the approved historical weather scenario."""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]


def weekly_weather(data):
    hourly = data.copy().set_index("time")
    hourly.index = pd.to_datetime(hourly.index, utc=True)
    hourly = hourly.sort_index()
    if not hourly.index.is_unique or not np.isfinite(
        hourly[["temperature_2m", "precipitation"]].to_numpy()
    ).all():
        raise ValueError("Weather needs unique hourly timestamps and finite values.")
    # Temperature is instantaneous; precipitation is the preceding hour's total.
    starts = hourly.index - pd.Timedelta(hours=1)
    first = starts.min().tz_convert("Europe/Oslo").normalize()
    first -= pd.DateOffset(days=first.weekday())
    last = hourly.index.max().tz_convert("Europe/Oslo").normalize()
    last += pd.DateOffset(days=7 - last.weekday())
    grid = pd.date_range(first.tz_convert("UTC"), last.tz_convert("UTC"),
                         freq="h", inclusive="left")
    aligned = pd.DataFrame({
        "temperature_c": hourly.temperature_2m,
        "precipitation_mm": hourly.precipitation.set_axis(starts),
    }, index=grid)
    calendar = grid.tz_convert("Europe/Oslo").isocalendar()
    grouped = aligned.groupby([calendar.year.to_numpy(), calendar.week.to_numpy()])
    complete = grouped.count().eq(grouped.size(), axis=0)
    result = grouped.temperature_c.mean().to_frame().join(
        grouped.precipitation_mm.sum(min_count=1)
    ).where(complete)
    result.index = pd.DatetimeIndex(
        [date.fromisocalendar(int(year), int(week), 7) for year, week in result.index],
        name="observation_date",
    )
    return result.sort_index()


@st.cache_data(ttl=600, max_entries=12, show_spinner=False)
def load_weekly_weather(region):
    extended = ROOT / "data/weather" / f"{region}_era5_2023-2025_hourly_sample100.csv.gz"
    paths = [extended] if extended.exists() else sorted(
        (ROOT / "data/weather").glob(f"{region}_era5_*_hourly.csv.gz")
    )
    if not paths:
        raise ValueError("No saved weather exists for this area. Prepare a weather year under Weather anomalies first.")
    frame = pd.concat([pd.read_csv(path, parse_dates=["time"]) for path in paths])
    frame = frame.drop_duplicates(subset="time", keep="last")
    count = int(frame.point_count.min())
    return weekly_weather(frame), count


def prepare_weather_scenario(weather, training_dates, forecast_dates):
    """Use previous-week weather and means learned strictly before the cutoff."""
    known = weather.reindex(training_dates - pd.Timedelta(weeks=1))
    if known.isna().any().any():
        raise ValueError("The saved weather does not cover every previous training week. Choose a covered period or filling history alone.")
    exogenous = known.set_axis(training_dates)
    weeks = known.index.isocalendar().week.to_numpy()
    historical_means = known.groupby(weeks).mean()
    future_weeks = (forecast_dates - pd.Timedelta(weeks=1)).isocalendar().week.to_numpy()
    scenario = historical_means.reindex(future_weeks).set_axis(forecast_dates)
    counts = known.groupby(weeks).size().reindex(future_weeks).set_axis(forecast_dates)
    if scenario.isna().any().any():
        raise ValueError("No historical weather scenario is available for one of the forecast weeks.")
    return exogenous, scenario, counts


def sliding_correlation(weather, reservoir, weather_property, reservoir_property, lag, window):
    aligned = reservoir[[reservoir_property]].join(weather, how="outer").sort_index().asfreq("W-SUN")
    return aligned[weather_property].shift(lag).rolling(window).corr(aligned[reservoir_property])
