import streamlit as st

st.set_page_config(
    page_title="Reservoir Dashboard",
    layout="wide"
)

st.title("Norwegian Reservoir Dashboard")
st.write(
    "This app presents historical data about Norwegian reservoir "
    "levels, capacity and stored energy, downloaded directly from NVE's API. "
    "Open Data Table or Data Plot to choose a period and area. "
    "Area choices are shared with Weather Analysis, where ERA5 weather data "
    "can be loaded for the selected region. Reservoir Analysis shows STL and a "
    "spectrogram of weekly filling for the same area. Reservoir API explains "
    "the source and geographical areas. Cross Border Transfers shows curated "
    "ENTSO-E import/export data read from MongoDB."
)
