import streamlit as st

from load_data import load_data_or_stop


st.title("Reservoir Data Plot")
st.write(
    "Choose a column and a range of months to display."
)

# I share the cached API download across pages and widget selections.
reservoirs = load_data_or_stop()
data_columns = reservoirs.columns.tolist()

# These columns contain the measurements that can be compared as lines.
measurement_columns = [
    "filling_fraction",
    "capacity_twh",
    "stored_energy_twh",
    "previous_week_filling_fraction",
    "weekly_filling_change",
]

selected_column = st.selectbox(
    "Choose a column",
    options=["All columns"] + data_columns,
)

# I add a temporary month label without changing the cached API data.
all_data = reservoirs.copy()
all_data["month"] = all_data["observation_date"].dt.strftime("%Y-%m")

# The national observations give me one continuous series per measurement.
national_data = (
    all_data[all_data["area_type"] == "NO"]
    .sort_values("observation_date")
    .copy()
)

month_options = national_data["month"].drop_duplicates().tolist()

selected_months = st.select_slider(
    "Choose a range of months",
    options=month_options,
    value=(month_options[0], month_options[0]),
)

start_month, end_month = selected_months

filtered_national_data = national_data[
    national_data["month"].between(start_month, end_month)
]
filtered_all_data = all_data[
    all_data["month"].between(start_month, end_month)
]

st.subheader(f"Data from {start_month} to {end_month}")

if selected_column == "All columns":
    # Dates, categories and identifiers cannot share a meaningful y-axis,
    # so the combined view contains the five actual measurements.
    st.line_chart(
        filtered_national_data,
        x="observation_date",
        y=measurement_columns,
        x_label="Observation date",
        y_label="Value on original scale",
    )
    st.caption(
        "The combined view contains the measurement columns. Descriptive "
        "columns can be selected individually from the menu."
    )

elif selected_column == "area_type":
    area_counts = (
        filtered_all_data["area_type"]
        .value_counts()
        .rename_axis("area_type")
        .reset_index(name="number_of_rows")
    )
    st.bar_chart(
        area_counts,
        x="area_type",
        y="number_of_rows",
        x_label="Area type",
        y_label="Number of rows",
    )

elif selected_column == "observation_date":
    observation_counts = (
        filtered_all_data.groupby("observation_date")
        .size()
        .reset_index(name="number_of_rows")
    )
    st.line_chart(
        observation_counts,
        x="observation_date",
        y="number_of_rows",
        x_label="Observation date",
        y_label="Number of rows",
    )

elif selected_column == "next_publication_date":
    publication_data = filtered_national_data.dropna(
        subset=["next_publication_date"]
    ).copy()

    if publication_data.empty:
        st.info("No publication dates were recorded during this period.")
    else:
        publication_data["days_until_publication"] = (
            publication_data["next_publication_date"]
            - publication_data["observation_date"]
        ).dt.total_seconds() / (24 * 60 * 60)

        st.line_chart(
            publication_data,
            x="observation_date",
            y="days_until_publication",
            x_label="Observation date",
            y_label="Days until publication",
        )

else:
    st.line_chart(
        filtered_national_data,
        x="observation_date",
        y=selected_column,
        x_label="Observation date",
        y_label=selected_column.replace("_", " ").title(),
    )
