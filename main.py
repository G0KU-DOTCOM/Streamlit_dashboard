import streamlit as st

st.set_page_config(
    page_title="Reservoir Dashboard",
    layout="wide"
)

st.title("Norwegian Reservoir Dashboard")
st.write(
    "This app presents historical data about Norwegian reservoir "
    "levels, capacity and stored energy, downloaded directly from NVE's API. "
    "Open Reservoir API in the sidebar to choose a period and area type."
)
