import streamlit as st

st.set_page_config(page_title="About the Project", layout="wide")
st.title("About the Project")
st.write(
    "This IND320 Part 2 project explores Norwegian reservoir levels and "
    "cross-border electricity imports and exports. It builds on Part 1 using "
    "API data, Spark, Cassandra and MongoDB."
)
st.subheader("Where the data come from")
st.markdown(
    "- **Reservoirs:** [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/). "
    "The app downloads API history and shares period and area selections between tables and plots.\n"
    "- **Electricity transfers:** [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/). "
    "Spark stores validated intervals in Cassandra and prepares hourly energy for MongoDB. "
    "The transfer page reads those curated MongoDB records directly."
)
st.subheader("How to read the results")
st.write(
    "Transfer data cover nine international bidding-zone borders from 11 October 2024 "
    "through 10 October 2026. Only 2025 is a complete calendar year. MW measures power; "
    "MWh measures energy over time. Missing measurements are not treated as zero."
)
st.subheader("Limitations")
st.write(
    "The reservoir period slider filters cached history after download; it does not "
    "restrict the dates returned by NVE. Historical Russia-border coverage is not "
    "established. Hourly transfer averages smooth short peaks. Source details and "
    "coverage are explained on the relevant pages."
)
st.markdown(
    "[Project repository and notebook](https://github.com/G0KU-DOTCOM/Streamlit_dashboard). "
    "The notebook documents methods, checks, the personal work log and AI assistance."
)
