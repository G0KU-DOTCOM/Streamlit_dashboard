import streamlit as st

st.set_page_config(
    page_title="Reservoir Dashboard",
    page_icon="💧",
    layout="wide"
)

st.title("Norwegian Reservoir Dashboard")
st.write(
    "This app presents historical data about Norwegian reservoir "
    "levels, capacity and stored energy."
)