import pandas as pd
import streamlit as st


@st.cache_data
def load_data():
    # I read the local CSV once and cache the result because Streamlit
    # reruns the page whenever the user interacts with the application.
    reservoirs = pd.read_csv("data/reservoirs.csv")

    # Rename the Norwegian headers so the tables and plots are understandable.
    english_names = {
    "dato_Id": "observation_date",
    "omrType": "area_type",
    "omrnr": "area_number",
    "iso_aar": "iso_year",
    "iso_uke": "iso_week",
    "fyllingsgrad": "filling_fraction",
    "kapasitet_TWh": "capacity_twh",
    "fylling_TWh": "stored_energy_twh",
    "neste_Publiseringsdato": "next_publication_date",
    "fyllingsgrad_forrige_uke": "previous_week_filling_fraction",
    "endring_fyllingsgrad": "weekly_filling_change"     
    }

    return reservoirs.rename(columns=english_names)