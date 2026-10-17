import streamlit as st

from dashboard.reservoir_views import MEASUREMENTS, area_summary, reservoir_controls, source_details

st.set_page_config(page_title="Reservoir Data Table", layout="wide")
st.title("Reservoir Data Table")
st.write("Compare each area's weekly measurements over the selected period.")
selection = reservoir_controls("table")

if selection.data.empty:
    st.info("There are no observations for this period and area type.")
else:
    # Each area has its own row and five independent measurement sparklines.
    # Identifiers and dates remain ordinary columns rather than mini-plots.
    st.dataframe(
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
    st.caption(
        "Each trend uses its own vertical scale. Filling fraction 1.0 means 100%; "
        "weekly change 0.01 means one percentage point. Trends omit empty weeks before "
        "and after available values; an internal missing week leaves the trend empty. "
        "Open Data Plot for dated axes and gaps."
    )
    with st.expander("Selected observations and column types"):
        # Preserve the Part 1 ability to inspect all eleven imported fields.
        st.dataframe(selection.data, hide_index=True)
        st.dataframe(
            [{"column": column, "data_type": str(dtype)} for column, dtype in selection.history.dtypes.items()],
            hide_index=True,
        )
        if selection.data["next_publication_date"].isna().any():
            st.caption("Missing publication dates are shown as empty values; NVE's year-1 marker is treated as missing.")

source_details(selection.history)
