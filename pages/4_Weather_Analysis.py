import matplotlib

# Streamlit renders figures without opening a desktop plot window.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

from dashboard.reservoir_analysis import plot_temperature_spc, plot_temperature_lof
from dashboard.weather_views import weather_controls

st.set_page_config(page_title="Weather Analysis", layout="wide")
st.title("Weather Analysis")
st.write("Hourly ERA5 temperature analyses for the selected reservoir area.")
selection = weather_controls()
if selection is None:
    st.stop()

region, year, weather = selection
st.subheader(f"{region} · {year}")
st.caption("Hourly averages across the region's 1000 sampled locations. Times are UTC.")
hourly = weather.set_index("time")
spc_tab, lof_tab = st.tabs(["Outlier / SPC", "Anomaly / LOF"])

with spc_tab:
    # The teacher clarified that the DCT/SPC analysis should use temperature.
    st.write("Find unusual temperature hours using DCT filtering and robust SPC limits.")
    columns = st.columns(2)
    cutoff = columns[0].number_input(
        "DCT cutoff (cycles/day)", min_value=0.0001, max_value=11.99,
        value=1 / 30, step=0.005, format="%.5f", key="spc_cutoff",
        help="The default removes variations with periods longer than approximately 30 days.",
    )
    deviations = columns[1].number_input(
        "Number of standard deviations", min_value=0.1, value=3.0, step=0.5,
        key="spc_deviations", help="Larger values give wider limits and flag fewer hours.",
    )
    try:
        figure, summary, outliers = plot_temperature_spc(
            hourly["temperature_2m"], cutoff_frequency=cutoff, n_std=deviations,
        )
    except ValueError as exc:
        st.info(str(exc))
    else:
        columns = st.columns(4)
        columns[0].metric("Hours analysed", f"{summary['number_of_hours']:,}")
        columns[1].metric("Outlier hours", f"{summary['number_of_outliers']:,}")
        columns[2].metric("Outlier share", f"{summary['percentage']:.2f}%")
        columns[3].metric("Robust standard deviation", f"{summary['robust_standard_deviation_c']:.3f} °C")
        st.pyplot(figure)
        plt.close(figure)
        st.caption(
            "Limits use the median and scaled MAD of the seasonally adjusted temperature variations "
            "(SATV) over the whole year. The plot shows original temperature, limits and flagged hours."
        )
        st.subheader("Temperature outlier hours")
        st.dataframe(
            outliers.rename_axis("time").reset_index(),
            hide_index=True, column_config={
                "time": st.column_config.DatetimeColumn("Time (UTC)"),
                "temperature_c": st.column_config.NumberColumn("Temperature (°C)", format="%.2f"),
                "lower_limit_c": st.column_config.NumberColumn("Lower limit (°C)", format="%.2f"),
                "upper_limit_c": st.column_config.NumberColumn("Upper limit (°C)", format="%.2f"),
            },
        )
        st.caption("Sorted by time. Both warm and cold outliers may be flagged; they do not necessarily indicate data errors.")

with lof_tab:
    st.write("Find unusual temperature hours using Local Outlier Factor.")
    percentage = st.number_input(
        "Anomaly proportion (%)", min_value=0.01, max_value=50.0, value=1.0,
        step=0.5, format="%.2f", key="lof_percentage",
        help="The default is 1%. This sets the threshold; the actual share can differ slightly because of ties or rounding.",
    )
    try:
        figure, summary, anomalies = plot_temperature_lof(
            hourly["temperature_2m"], outlier_fraction=percentage / 100,
        )
    except ValueError as exc:
        st.info(str(exc))
    else:
        columns = st.columns(3)
        columns[0].metric("Hours analysed", f"{summary['number_of_hours']:,}")
        columns[1].metric("Anomaly hours", f"{summary['number_of_anomalies']:,}")
        columns[2].metric("Anomaly share", f"{summary['percentage']:.2f}%")
        st.pyplot(figure)
        plt.close(figure)
        st.caption(
            "LOF uses standardised time and temperature with 20 neighbours. "
            "Flagged hours are statistically unusual and do not necessarily contain data errors."
        )
        st.subheader("Temperature anomaly hours")
        st.dataframe(
            anomalies.rename_axis("time").reset_index(), hide_index=True,
            column_config={
                "time": st.column_config.DatetimeColumn("Time (UTC)"),
                "temperature_c": st.column_config.NumberColumn("Temperature (°C)", format="%.2f"),
                "lof_score": st.column_config.NumberColumn("LOF score", format="%.3f"),
            },
        )
        st.caption("Sorted by LOF score: higher scores indicate more unusual observations.")
