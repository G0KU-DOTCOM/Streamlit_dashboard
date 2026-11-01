"""Shared weather selection and explicit download controls for Streamlit."""

from datetime import date, timedelta

import requests
import streamlit as st

from dashboard.load_data import load_data_or_stop
from dashboard.reservoir_views import area_controls, remember_selection
from dashboard.weather_data import prepare_weather_summary, read_weather_summary, weather_region


@st.cache_data(ttl=24 * 60 * 60, max_entries=16, show_spinner=False)
def load_weather_summary(region, start_date, end_date):
    return read_weather_summary(region, start_date, end_date)


def weather_controls():
    """Return (region, year, hourly means), or None until matching data are ready."""
    history = load_data_or_stop()
    area_type, area_number, _ = area_controls("weather", history)

    # Weather uses a complete calendar year; reservoir analyses use their own period.
    latest_year = (date.today() - timedelta(days=5)).year - 1
    years = list(range(1940, latest_year + 1))
    saved = st.session_state.get("weather_year", min(2024, latest_year))
    if saved not in years:
        saved = min(2024, latest_year)
    st.session_state["weather_year"] = saved
    year = st.selectbox(
        "Weather year", years, index=years.index(saved), key="_weather_year",
        on_change=remember_selection, args=("weather_year", "_weather_year"),
    )
    st.caption("The weather year is separate from the reservoir plot period.")
    if area_number is None:
        st.info("Choose a single area to load its weather data.")
        return None
    region = weather_region(area_type, area_number)
    if region is None:
        st.info("No weather sample is available for this area. Choose NO1–NO5 or VASS1–VASS3.")
        return None
    if area_type == "VASS":
        st.caption(
            "Weather uses the assignment's groups: East (RS + RØ), West (RV), "
            "and North (RM + RN)."
        )
    start_date, end_date = f"{year}-01-01", f"{year}-12-31"
    try:
        data = load_weather_summary(region, start_date, end_date)
    except (ValueError, OSError) as exc:
        st.error(f"Saved weather data could not be loaded: {exc}")
        return None

    with st.expander("Weather data and download", expanded=data is None):
        st.write(f"ERA5 · {region} · {year} · 1000 sampled locations")
        st.caption(
            "Saved data are reused. A new download may take several minutes and "
            "starts only when you press the button."
        )
        download = st.button("Download weather data", disabled=data is not None, key="download_weather")
        if download:
            try:
                with st.status("Preparing weather data…", expanded=True) as status:
                    progress_bar = st.progress(0.0)

                    def report(message, completed, total):
                        progress_bar.progress(completed / total, text=message)

                    data = prepare_weather_summary(region, start_date, end_date, progress=report)
                    load_weather_summary.clear()
                    progress_bar.progress(1.0, text="All locations and hours are ready.")
                    status.update(label="Weather data ready", state="complete", expanded=False)
            except (requests.RequestException, ValueError, OSError, AssertionError, KeyError) as exc:
                st.error(f"Weather data could not be prepared: {exc}")
                return None
        if data is not None:
            st.success(f"Ready: {len(data):,} hours, with 1000 locations per hour.")
    st.caption(
        "Source: [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), "
        "ERA5. Region samples: [NVE Atlas](https://atlas.nve.no). Times are UTC."
    )
    if data is None:
        st.info("Weather data have not been downloaded for this area and year.")
        return None
    return region, year, data
