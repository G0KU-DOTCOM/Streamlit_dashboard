"""The notebook's lagged correlation, with local interactive controls."""

import plotly.graph_objects as go
import streamlit as st

from dashboard.load_data import load_data_or_stop
from dashboard.reservoir_views import area_controls
from dashboard.theme import style_figure
from dashboard.weather_data import weather_region
from dashboard.weekly import load_weekly_weather, sliding_correlation


def render_correlation():
    st.subheader("Weather & reservoir filling")
    st.write("Inspect how the relationship changes across trailing weekly windows.")
    history = load_data_or_stop()
    kind, number, labels = area_controls("correlation", history)
    region = weather_region(kind, number)
    if number is None or region is None:
        st.info("Choose one area with saved weather data.")
        return
    left, right = st.columns(2)
    weather_property = left.selectbox("Weather property", ["temperature_c", "precipitation_mm"],
        format_func=lambda key: {"temperature_c": "Temperature (°C)", "precipitation_mm": "Precipitation (mm)"}[key])
    reservoir_property = right.selectbox("Reservoir variable", ["weekly_filling_change", "filling_fraction", "stored_energy_twh"],
        format_func=lambda key: {"weekly_filling_change": "Weekly filling change", "filling_fraction": "Filling fraction", "stored_energy_twh": "Stored energy (TWh)"}[key])
    lag = left.number_input("Weather lead (weeks)", 0, 26, 1, key="correlation_lag")
    window = right.number_input("Window length (weeks)", 4, 104, 13, key="correlation_window")
    try:
        weather, points = load_weekly_weather(region)
        reservoir = history.loc[history.area_type.eq(kind) & history.area_number.eq(number)].set_index("observation_date")
        result = sliding_correlation(weather, reservoir, weather_property, reservoir_property, lag, window)
        # Limit the display to weather coverage rather than drawing decades of empty axes.
        result = result.loc[weather.index.min():weather.index.max()]
        if not result.notna().any():
            st.info("No complete correlation windows for these settings and available data.")
            return
        figure = go.Figure(go.Scatter(x=result.index, y=result, mode="lines", name="Pearson r", connectgaps=False))
        figure.add_hline(y=0, line_width=1, line_color="#8799ac")
        style_figure(figure, y_title="Pearson correlation r")
        figure.update_yaxes(range=[-1, 1])
        st.plotly_chart(figure)
        st.caption(f"{labels[number]} · {points} weather locations · full {window}-week windows. A lead of {lag} pairs weather with filling {lag} weeks later. Correlation does not establish causation.")
        with st.expander("Weekly correlation values"):
            st.dataframe(result.rename("Pearson r").dropna().reset_index(), hide_index=True)
    except (ValueError, OSError, KeyError) as exc:
        st.info(str(exc))
