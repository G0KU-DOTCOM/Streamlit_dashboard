"""Read complete weekly weather for map colouring without implicit downloads."""

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.geography import feature_number, load_geometry
from dashboard.weather_data import weather_region
from dashboard.weekly import weekly_weather

ROOT = Path(__file__).resolve().parents[1]
WEATHER_MEASURES = {"Temperature (°C)": "temperature_c", "Precipitation (mm)": "precipitation_mm"}


@st.cache_data(ttl=600, max_entries=32, show_spinner=False)
def map_weather_values(kind, week):
    """Prefer the largest complete saved sample; never mix samples within a week."""
    result = {}
    for feature in load_geometry(kind)["features"]:
        number = feature_number(feature)
        region = weather_region(kind, number)
        if region is None:
            continue
        best = None
        for path in sorted((ROOT / "data/weather").glob(f"{region}_era5_*_hourly*.csv.gz")):
            frame = pd.read_csv(path, parse_dates=["time"])
            weekly = weekly_weather(frame)
            date = pd.Timestamp(week)
            if date not in weekly.index or weekly.loc[date].isna().any():
                continue
            count = int(frame.point_count.min())
            if best is None or count > best["point_count"]:
                best = {**weekly.loc[date].to_dict(), "point_count": count}
        if best is not None:
            result[number] = best
    return result


def weather_request_dates(week):
    """UTC calendar-date bounds include the rain interval ending at next Monday."""
    sunday = pd.Timestamp(week)
    start = (sunday - pd.Timedelta(days=6)).tz_localize("Europe/Oslo").tz_convert("UTC")
    end = (sunday + pd.Timedelta(days=1)).tz_localize("Europe/Oslo").tz_convert("UTC")
    return start.date().isoformat(), end.date().isoformat()
