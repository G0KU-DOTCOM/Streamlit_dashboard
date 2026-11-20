import streamlit as st
import plotly.graph_objects as go

from dashboard.reservoir_views import MEASUREMENTS, area_lines, area_summary, reservoir_controls, source_details
from dashboard.theme import style_figure

st.set_page_config(page_title="Reservoirs", layout="wide")
st.title("Reservoir overview")
st.write("Explore filling trends, compare areas and inspect the underlying observations.")
selection = reservoir_controls("table")

if selection.data.empty:
    st.info("There are no observations for this period and area type.")
else:
    trend, overview, observations = st.tabs(["Trend", "Area overview", "Observations"])
    with trend:
        measurement = st.selectbox("Measurement", list(MEASUREMENTS),
                                   format_func=MEASUREMENTS.get, key="overview_measurement")
        values = area_lines(selection, measurement)
        units = {"filling_fraction": "Filling (%)", "capacity_twh": "Capacity (TWh)",
                 "stored_energy_twh": "Stored energy (TWh)",
                 "previous_week_filling_fraction": "Previous filling (%)",
                 "weekly_filling_change": "Weekly filling change (pp)"}
        if measurement in ("filling_fraction", "previous_week_filling_fraction", "weekly_filling_change"):
            values = values * 100
        figure = go.Figure()
        for name in values:
            figure.add_trace(go.Scatter(x=values.index, y=values[name], name=name,
                                       mode="lines", connectgaps=False))
        st.plotly_chart(style_figure(figure, y_title=units[measurement]))
        st.caption("Weekly observations. Missing weeks stay visible as gaps.")
    # Each area has its own row and five independent measurement sparklines.
    # Identifiers and dates remain ordinary columns rather than mini-plots.
    overview.dataframe(
        area_summary(selection),
        column_config={
            "area": "Area", "area_number": "Area number", "observations": "Observations",
            "first_observation": st.column_config.DateColumn("First observation"),
            "last_observation": st.column_config.DateColumn("Last observation"),
            **{
                column: st.column_config.LineChartColumn(
                    label, width="medium",
                    help="Weekly values from the area's first to last available observation. An internal missing week leaves the chart empty; missing values are never replaced with zero.",
                )
                for column, label in MEASUREMENTS.items()
            },
        },
        hide_index=True,
    )
    overview.caption(
        "Each trend uses its own vertical scale. Filling fraction 1.0 means 100%; "
        "weekly change 0.01 means one percentage point. Trends omit empty weeks before "
        "and after available values; an internal missing week leaves the trend empty. "
        "Open Trend for dated axes and gaps."
    )
    with observations:
        # Preserve the Part 1 ability to inspect all eleven imported fields.
        st.dataframe(selection.data, hide_index=True)
        st.dataframe(
            [{"column": column, "data_type": str(dtype)} for column, dtype in selection.history.dtypes.items()],
            hide_index=True,
        )
        if selection.data["next_publication_date"].isna().any():
            st.caption("Missing publication dates are shown as empty values; NVE's year-1 marker is treated as missing.")

source_details(selection.history)
