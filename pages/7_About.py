import streamlit as st

st.set_page_config(page_title="About the Project", layout="wide")
st.title("Sources & about")
st.write(
    "This IND320 project combines reservoir history, weather, cross-border energy "
    "transfers and exchange rates. Part 4 adds weekly forecasting with River SNARIMAX "
    "and a shared map-based area selection."
)
st.subheader("Where the data come from")
st.markdown(
    "- **Reservoirs:** [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/). "
    "The app downloads API history and shares period and area selections between tables and plots.\n"
    "- **Electricity transfers:** [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/). "
    "Spark stores validated intervals in Cassandra and prepares hourly energy for MongoDB. "
    "The transfer page reads those curated MongoDB records directly.\n"
    "- **Weather:** [Open-Meteo ERA5](https://open-meteo.com/en/docs/historical-weather-api). "
    "Saved regional hourly means support the weather analyses and weekly scenarios. "
    "Open-Meteo data are attributed under CC BY 4.0.\n"
    "- **Exchange rates:** [Norges Bank](https://www.norges-bank.no/en/topics/Statistics/open-data/guide-data-warehouse/). "
    "EUR/NOK and USD/NOK daily spot quotes; see the downloader below.\n"
    "- **Map boundaries:** [NVE Atlas](https://atlas.nve.no). "
    "Price-area and national GeoJSON were simplified from the saved project shapefiles."
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
        "Water-area boundaries are not drawn until the match with NVE's reservoir areas is verified."
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
