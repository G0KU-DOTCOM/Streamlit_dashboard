import streamlit as st

from dashboard.load_data import NVEDataError, load_areas, load_data_or_stop
from dashboard.reservoir_views import source_details

st.title("Reservoir API — Sources and Areas")
st.write(
    "Use Data Table and Data Plot to explore the same period and area selection. "
    "This page explains the source and the geographical groups."
)
history = load_data_or_stop()
st.write(
    f"Available history: {history['observation_date'].min():%d %B %Y} to "
    f"{history['observation_date'].max():%d %B %Y} · {len(history):,} observations."
)
st.write(
    "EL denotes electricity price areas, NO denotes Norway as a whole, and "
    "VASS denotes watercourse regions. These are overlapping geographical "
    "groupings and should not be added together."
)
try:
    st.dataframe(load_areas(), hide_index=True)
except NVEDataError as exc:
    st.warning(str(exc))
source_details(history)
