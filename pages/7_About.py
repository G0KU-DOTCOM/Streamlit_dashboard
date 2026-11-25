import streamlit as st

st.set_page_config(page_title="Sources & about", layout="wide")
st.title("Sources & about")
st.write(
    "This IND320 project combines reservoir history, weather, cross-border energy "
    "transfers and exchange rates. Part 4 adds weekly forecasting with River SNARIMAX "
    "and a shared map-based area selection."
)
st.subheader("Where the data come from")
st.markdown(
    "- **Reservoirs:** [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/). "
    "The app downloads API history and shares the selected area across views. "
    "Home and Forecast also share the observation cutoff and forecast horizon.\n"
    "- **Electricity transfers:** [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/). "
    "Spark stores validated intervals in Cassandra and prepares hourly energy for MongoDB. "
    "The transfer page reads those curated MongoDB records directly.\n"
    "- **Weather:** [Open-Meteo ERA5](https://open-meteo.com/en/docs/historical-weather-api). "
    "SPC and LOF offer temperature or precipitation, with temperature as the default. "
    "The weather analyses use 1000 sampled locations per region. For NO3, correlation "
    "and forecast weather scenarios use a separate saved 100-location sample from 2023–2025. "
    "Open-Meteo data are attributed under CC BY 4.0.\n"
    "- **Exchange rates:** [Norges Bank](https://www.norges-bank.no/en/topics/Statistics/open-data/guide-data-warehouse/). "
    "EUR/NOK and USD/NOK daily spot quotes; see the downloader below.\n"
    "- **Map boundaries:** [NVE Atlas](https://atlas.nve.no). "
    "Price-area and national GeoJSON were simplified from the saved project shapefiles."
)
st.subheader("Interface and navigation")
st.write(
    "The blue layout groups pages into Explore, Analyse, Predict and Project. "
    "Reservoirs combines interactive measurement curves, area sparklines and detailed observations. "
    "Charts use Plotly, including the forecast animation; the clickable map uses Folium. "
    "The reservoir display period, weather year and local analysis settings have separate meanings."
)
st.subheader("How to read the results")
st.write(
    "Filling curves use percentages; raw NVE tables retain fractions, where 1.0 means 100%. "
    "Percentage-based filling changes and forecast errors use percentage points (pp). "
    "Weather anomaly flags identify statistically unusual observations; "
    "they do not prove a data error. Sliding-window correlations can vary over time and do not "
    "establish causation. Forecast scores are shown only for available observations after the "
    "training cutoff, with a last-value reference for comparison."
)
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
st.write(
    "The VASS map uses Part 3's grouped NVE administrative regions as overview outlines, "
    "rather than detailed hydrological catchments. Only VASS1–VASS3 have published observations; "
    "VASS4 has no values or separate outline. Weather colours require a complete saved week; "
    "grey means missing data, and an explicit button prepares weather for the selected area and week. "
    "The evaluated forecast settings are based on NO3 and should not be "
    "assumed to work equally well in every area or season. Weather scenarios require saved data "
    "covering the selected training weeks; missing coverage produces a message."
)
st.markdown(
    "[Project repository](https://github.com/G0KU-DOTCOM/Streamlit_dashboard) · "
    "[Part 4 notebook](https://github.com/G0KU-DOTCOM/Streamlit_dashboard/blob/main/notebooks/prosjekt_part4.ipynb). "
    "The notebooks document methods, checks, AI assistance and work logs. "
    "[Watch the Part 4 screencast](https://nmbu.cloud.panopto.eu/Panopto/Pages/Viewer.aspx?id=0d78306a-ab11-4531-969d-b50d00ccca8b)."
)

with st.expander("Data reuse and waiting time"):
    st.write(
        "NVE history is cached for 24 hours and area descriptions for 7 days. "
        "Transfer reads are cached for 24 hours, using one indexed connection/year query; "
        "month changes reuse the same data. Saved weather summaries avoid repeating downloads. "
        "A new weather download starts only after a button press and shows progress. "
        "Forecast results are cached by their inputs, and exchange-rate reads for 24 hours. "
        "Spinners or status messages indicate work in progress."
    )

with st.expander("Model evaluation and time alignment"):
    st.write(
        "Forecasting uses weekly filling observations. Starting settings are p=1, d=1, q=1, "
        "m=52, sp=1, sd=0, sq=0, 104 training weeks and a 12-week horizon. "
        "These orders were selected on four 2025 cutoffs; 2026 checks showed substantial seasonal variation. "
        "The NO3 weather option uses a saved 100-point sample from 2023–2025. "
        "Historical ISO-week means are explicit future-weather scenarios, not known future observations."
    )
    st.write(
        "Temperature is instantaneous, precipitation describes the preceding hour, and ENTSO-E "
        "energy uses the interval start. Weekly weather uses Europe/Oslo calendar weeks, "
        "including 167- and 169-hour daylight-saving weeks. Exchange rates retain calendar quote dates. "
        "NVE observation dates and later publication dates differ. Historical evaluations use "
        "observation-based cutoffs; exact first-availability and revision histories are not retained."
    )
    st.write(
        "The map week and last forecast training week share session state. "
        "The reservoir overview period, weather year and analysis parameters have their own meanings. "
        "The VASS map uses the grouped overview regions from Part 3."
    )

with st.expander("EUR/NOK and USD/NOK exchange rates"):
    from datetime import date
    import streamlit as st
    import plotly.graph_objects as go
    from dashboard.exchange_rates import download_exchange_rates, ExchangeRateError
    from dashboard.theme import style_figure

    @st.cache_data(ttl=86400, max_entries=12, show_spinner=False)
    def rates_for_period(start, end):
        return download_exchange_rates(start, end)

    with st.form("exchange_rate_dates"):
        columns = st.columns(2)
        start = columns[0].date_input("From", date(2025, 1, 1))
        end = columns[1].date_input("Through", date(2025, 12, 31))
        fetch = st.form_submit_button("Load exchange rates")
    if fetch:
        try:
            with st.spinner("Reading Norges Bank quotes…"):
                rates = rates_for_period(start, end)
            figure = go.Figure()
            for column, label in [("eur_nok", "NOK per EUR"), ("usd_nok", "NOK per USD")]:
                figure.add_trace(go.Scatter(x=rates.index, y=rates[column], name=label, connectgaps=False))
            st.plotly_chart(style_figure(figure, y_title="NOK per currency unit"))
            st.dataframe(rates, column_config={"date": st.column_config.DateColumn("Quote date")})
            st.caption("Published quote dates only. Weekends and holidays are not filled with invented quotes. Reads are cached for 24 hours.")
        except (ExchangeRateError, ValueError) as exc:
            st.error(str(exc))
