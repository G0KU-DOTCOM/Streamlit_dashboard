import streamlit as st

from dashboard.reservoir_views import MEASUREMENTS, plot_measurement, reservoir_controls, source_details

st.set_page_config(page_title="Reservoir Data Plot", layout="wide")
st.title("Reservoir Data Plot")
st.write("Compare areas using the same selection as the data table.")
selection = reservoir_controls("plot")
selected_column = st.selectbox(
    "Choose a column", options=["All measurements"] + selection.history.columns.tolist(),
    index=selection.history.columns.tolist().index("filling_fraction") + 1,
)

if selection.data.empty:
    st.info("There are no observations for this period and area type.")
elif selected_column == "All measurements":
    # Different units get separate plots rather than a shared, misleading scale.
    for column, label in MEASUREMENTS.items():
        st.subheader(label)
        plot_measurement(selection, column)
elif selected_column in MEASUREMENTS:
    plot_measurement(selection, selected_column)
elif selected_column == "next_publication_date":
    if selection.data[selected_column].isna().all():
        st.info("No publication dates were recorded during this period.")
    else:
        # Keep a line per area and preserve missing publication dates as gaps.
        selection.data["days_until_publication"] = (
            selection.data["next_publication_date"] - selection.data["observation_date"]
        ).dt.total_seconds() / (24 * 60 * 60)
        plot_measurement(selection, "days_until_publication", "Days until publication")
elif selected_column in ("area_type", "area_number"):
    counts = selection.data.groupby("area_number").size().rename("Observations")
    counts.index = counts.index.map(selection.labels)
    st.bar_chart(counts, x_label="Area", y_label="Observations")
    st.caption(f"Observation counts within the selected {selection.area_type} areas.")
else:
    # Dates and ISO year/week are calendar descriptors, not reservoir measures.
    st.info("Calendar fields are shown as a table. Choose a measurement for area curves.")
    st.dataframe(
        selection.data[["observation_date", "area_number", "iso_year", "iso_week"]],
        hide_index=True,
    )

source_details(selection.history)
