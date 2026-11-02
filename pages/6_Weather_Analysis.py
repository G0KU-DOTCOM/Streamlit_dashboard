import streamlit as st

from dashboard.weather_views import weather_controls

st.set_page_config(page_title="Weather Analysis", layout="wide")
st.title("Weather Analysis")
st.write("Hourly ERA5 temperature and precipitation for the selected reservoir area.")
selection = weather_controls()
if selection is not None:
    region, year, weather = selection
    st.subheader(f"Weather data — {region}, {year}")
    st.caption("Hourly averages across the region's 1000 sampled locations.")
    st.dataframe(
        weather.head(10), hide_index=True,
        column_config={
            "time": st.column_config.DatetimeColumn("Time (UTC)"),
            "temperature_2m": st.column_config.NumberColumn("Temperature (°C)", format="%.2f"),
            "precipitation": st.column_config.NumberColumn("Precipitation (mm)", format="%.3f"),
            "point_count": "Locations",
        },
    )
