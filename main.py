import streamlit as st

from dashboard.theme import apply_theme

st.set_page_config(page_title="Reservoir Dashboard", page_icon="💧", layout="wide")
apply_theme()
st.logo("data/geography/dashboard-wordmark.svg", size="large")

# Hidden routes preserve existing bookmarked URLs while the visible menu follows
# the approved task-based sketch. All routes still use the real shared readers.
page = st.navigation({
    "": [st.Page("pages/0_Home.py", title="Home", icon=":material/home:", default=True)],
    "Explore": [
        st.Page("pages/1_Data_Table.py", title="Reservoirs", icon=":material/show_chart:"),
        st.Page("pages/5_Cross_Border_Transfers.py", title="Transfers", icon=":material/swap_horiz:"),
    ],
    "Analyse": [st.Page("pages/3_Reservoir_Analysis.py", title="Analyses", icon=":material/analytics:")],
    "Predict": [st.Page("pages/8_Forecast.py", title="Forecast", icon=":material/trending_up:")],
    "Project": [
        st.Page("pages/7_About.py", title="Sources & about", icon=":material/info:"),
        st.Page("pages/2_Data_Plot.py", title="Data Plot", visibility="hidden"),
        st.Page("pages/4_Weather_Analysis.py", title="Weather Analysis", visibility="hidden"),
        st.Page("pages/6_Reservoir_API.py", title="Reservoir API", visibility="hidden"),
    ],
}, expanded=True)
page.run()
