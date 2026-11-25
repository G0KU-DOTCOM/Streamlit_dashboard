from datetime import timedelta

import pandas as pd
import streamlit as st

from dashboard.app_state import horizon_control, selected_area, week_control
from dashboard.geography import area_from_map_click, area_map
from dashboard.load_data import load_data_or_stop
from dashboard.map_weather import WEATHER_MEASURES, map_weather_values, weather_request_dates
from dashboard.reservoir_views import area_controls

st.title("Norwegian reservoirs")
st.html('<p class="home-intro">Explore reservoir filling, weather and energy transfers. Choose an area to start.</p>')
history = load_data_or_stop()
# NO3 is the evaluated example. Retain any deliberate area choice thereafter.
if "nve_area_number_EL" not in st.session_state and (
    history.area_type.eq("EL") & history.area_number.eq(3)
).any():
    st.session_state["nve_area_number_EL"] = 3
if st.session_state.get("nve_area_type") == "VASS" and "nve_area_number_VASS" not in st.session_state:
    st.session_state["nve_area_number_VASS"] = 1

controls, map_column = st.columns([.9, 1.15], gap="large", vertical_alignment="center")
with controls, st.container(key="home_controls"):
    st.subheader("Choose your area")
    kind, number, labels = area_controls("home", history, compact=True)
    week = week_control(history, "home")
    with st.expander("Forecast horizon"):
        horizon = horizon_control("home")
    horizon = st.session_state.get("forecast_horizon", 12)
    area = selected_area(history)
    observation = area.loc[area.observation_date.eq(pd.Timestamp(week))]
    if not observation.empty:
        row = observation.iloc[0]
        st.metric("Reservoir filling", f"{row.filling_fraction * 100:.1f}%",
                  f"{row.weekly_filling_change * 100:+.2f} pp this week")
    elif number is not None:
        st.info("No filling observation is published for this area and week.")
    st.caption(f"Forecast dates: {week + timedelta(weeks=1):%d %b %Y}–{week + timedelta(weeks=horizon):%d %b %Y}")

with map_column:
    measure = st.selectbox("Map colour", ["Selected area", "Filling (%)", *WEATHER_MEASURES], key="map_measure")
    weather_values = None
    if measure in WEATHER_MEASURES:
        try:
            weather_values = map_weather_values(kind, week)
        except (ValueError, OSError, KeyError) as exc:
            st.error(f"Saved map weather could not be read: {exc}")
            weather_values = {}
        st.caption("Weekly mean temperature or total precipitation (Europe/Oslo). Grey means no saved data for this week.")
        with st.expander("Weather data", expanded=not weather_values):
            from dashboard.weather_data import prepare_weather_summary, weather_region
            region = weather_region(kind, number)
            if weather_values:
                st.caption("Saved weather locations per available area: " + ", ".join(
                    f"{'NO' if kind == 'EL' else 'VASS'}{area}: {int(values['point_count'])}"
                    for area, values in weather_values.items()))
            st.write("Saved observations are reused. Choose an area to load missing weather for this week; a new download uses its 1000 saved sample locations.")
            if region is None:
                st.info("Choose one price area or VASS1–VASS3 for a weather sample. No national or VASS4 sample is defined.")
            elif number not in weather_values and st.button("Load selected week's weather", key="map_weather_download"):
                try:
                    import requests
                    with st.status("Preparing weather for the selected area and week…", expanded=True) as status:
                        progress = st.progress(0.0)
                        def report(message, completed, total):
                            progress.progress(completed / total, text=message)
                        start, end = weather_request_dates(week)
                        prepare_weather_summary(region, start, end, progress=report)
                        map_weather_values.clear()
                        status.update(label="Weekly weather ready", state="complete", expanded=False)
                    st.rerun()
                except (requests.RequestException, ValueError, OSError, AssertionError, KeyError) as exc:
                    st.error(f"Weather could not be prepared: {exc}. Try an earlier week if the archive is not yet complete.")
    figure = area_map(history, kind, number, week, measure, weather_values=weather_values)
    if figure is None:
        st.info("No map layer is available for this area type.")
    else:
        # A fresh widget when its controls change prevents an old click overriding a
        # later selector choice. The persisted selected number stays independent.
        from streamlit_folium import st_folium
        event = st_folium(figure, key=f"region_map_{kind}_{number}_{week}_{measure}",
                          height=350, use_container_width=True,
                          returned_objects=["last_clicked", "last_object_clicked"])
        clicked = area_from_map_click(event, kind)
        if clicked is not None and clicked != number:
            st.session_state[f"nve_area_number_{kind}"] = clicked
            st.rerun()
    if kind == "VASS":
        st.caption("VASS1 East · VASS2 West · VASS3 Mid/North. Outlines use the grouped NVE regions from Part 3. VASS4 has no published observations.")

st.subheader("Where would you like to go?")
for column, page, title, description, icon in zip(
    st.columns(3, gap="medium"),
    ["pages/1_Data_Table.py", "pages/3_Reservoir_Analysis.py", "pages/8_Forecast.py"],
    ["Explore data", "Analyse patterns", "Forecast filling"],
    ["Filling trends and area overview", "Seasonality, weather and correlation", "Weekly SNARIMAX forecasts"],
    [":material/show_chart:", ":material/analytics:", ":material/trending_up:"],
):
    with column.container(border=True):
        st.page_link(page, label=title, icon=icon)
        st.caption(description)
