"""Calendar and region state shared by the map and forecasting page."""

from html import escape

import pandas as pd
import streamlit as st

from dashboard.reservoir_views import remember_selection


def selected_area(history):
    kind = st.session_state.get("nve_area_type", "EL")
    number = st.session_state.get(f"nve_area_number_{kind}")
    return history.loc[history.area_type.eq(kind) & history.area_number.eq(number)].copy()


def region_label():
    kind = st.session_state.get("nve_area_type", "EL")
    number = st.session_state.get(f"nve_area_number_{kind}")
    if number is None:
        return f"{kind} · All areas"
    return "Norway" if kind == "NO" else f"{'NO' if kind == 'EL' else 'VASS'}{number}"


def area_badge():
    st.html(f'<div class="area-label">{escape(region_label())}</div>')


def week_control(history, view):
    """A selected map week is also the last training observation, not a release time."""
    dates = sorted(history.observation_date.unique())
    dates = [pd.Timestamp(value).date() for value in dates]
    saved = st.session_state.get("forecast_end", dates[-1])
    saved = pd.Timestamp(saved).date()
    if saved not in dates:
        saved = min(dates, key=lambda value: abs(value - saved))
    st.session_state["forecast_end"] = saved
    widget = f"_forecast_end_{view}"
    requested = st.date_input(
        "Observation week / forecast cutoff", value=saved,
        min_value=dates[0], max_value=dates[-1], format="DD/MM/YYYY", key=widget,
        on_change=remember_selection, args=("forecast_end", widget),
        help="Week-ending observation date. Also sets the end of training on Forecast; publication follows later.",
    )
    actual = max(value for value in dates if value <= requested)
    st.session_state["forecast_end"] = actual
    if actual != requested:
        st.caption(f"Using the latest available observation on or before this date: {actual:%d %b %Y}.")
    return actual


def horizon_control(view):
    st.session_state.setdefault("forecast_horizon", 12)
    widget = f"_forecast_horizon_{view}"
    return st.number_input(
        "Forecast horizon (weeks)", min_value=1, max_value=52,
        value=int(st.session_state["forecast_horizon"]), step=1, key=widget,
        on_change=remember_selection, args=("forecast_horizon", widget),
    )
