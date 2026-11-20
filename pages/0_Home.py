from datetime import timedelta

import pandas as pd
import streamlit as st

from dashboard.app_state import horizon_control, selected_area, week_control
from dashboard.geography import area_from_map_click, area_map
from dashboard.load_data import load_data_or_stop
from dashboard.reservoir_views import area_controls

st.title("Norwegian reservoirs")
st.html('<p class="home-intro">Explore reservoir filling, weather and energy transfers. Choose an area to start.</p>')
history = load_data_or_stop()
# NO3 is the evaluated example. Retain any deliberate area choice thereafter.
if "nve_area_number_EL" not in st.session_state and (
    history.area_type.eq("EL") & history.area_number.eq(3)
).any():
    st.session_state["nve_area_number_EL"] = 3

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
    st.caption(f"Forecast dates: {week + timedelta(weeks=1):%d %b %Y}–{week + timedelta(weeks=horizon):%d %b %Y}")

with map_column:
    measure = st.selectbox("Map colour", ["Selected area", "Filling (%)"], key="map_measure")
    figure = area_map(history, kind, number, week, measure)
    if figure is None:
        st.info("Water-area boundaries are being verified. Choose the area using the selector; the price-area map is available under EL.")
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
