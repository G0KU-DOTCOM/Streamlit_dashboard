import streamlit as st
from load_data import load_data

# This page will later display the reservoir data as a table.
st.title("Reservoir Data Table")

# I load the cached dataset here to confirm that the table page can access it.
reservoirs = load_data()

st.write(f"The dataset contains {len(reservoirs):,} rows.")
#st.dataframe(reservoirs.head())
# The dataset contains several geographical rows for each week.
# I use the national row so the first month becomes one continuous series.
national_data = (
    reservoirs[reservoirs["area_type"] == "NO"]
    .sort_values("observation_date")
)

first_date = national_data["observation_date"].min()

first_month = national_data[
    national_data["observation_date"].dt.to_period("M")
    == first_date.to_period("M")
]

st.write(
    f"The first month contains {len(first_month)} national observations."
)

# Only the actual measurements are meaningful as line charts.
# Dates, categories and identifiers are instead shown as text.
measurement_columns = [
    "filling_fraction",
    "capacity_twh",
    "stored_energy_twh",
    "previous_week_filling_fraction",
    "weekly_filling_change",
]

table_rows = []

for column in reservoirs.columns:
    first_month_values = first_month[column]

    # I format the two date columns separately so they are understandable
    # instead of displaying Python's internal datetime representation.
    if column == "observation_date":
        displayed_values = ", ".join(
            first_month_values.dt.strftime("%d.%m.%Y")
        )
    elif column == "next_publication_date":
        displayed_values = (
            "Not recorded"
            if first_month_values.isna().all()
            else ", ".join(
                first_month_values.dropna().dt.strftime("%d.%m.%Y")
            )
        )
    elif column in measurement_columns:
        displayed_values = ", ".join(
            f"{value:.4f}" for value in first_month_values
        )
    else:
        displayed_values = ", ".join(
            first_month_values.astype(str)
        )

    # LineChartColumn needs a list of numbers. I therefore only provide
    # chart values for columns that contain actual measurements.
    trend_values = (
        first_month_values.astype(float).tolist()
        if column in measurement_columns
        else None
    )

    table_rows.append(
        {
            "column": column,
            "data_type": str(reservoirs[column].dtype),
            "first_month_values": displayed_values,
            "first_month_trend": trend_values,
        }
    )
st.warning(
    "The next publication date was not recorded during January 1995. "
    "The original CSV uses 0001-01-01T00:00:00 for these rows, "
    "which I convert to NaT in the application."
)

st.dataframe(
    table_rows,
    column_config={
        "column": "Imported column",
        "data_type": "Data type",
        "first_month_values": "Values from January 1995",
        "first_month_trend": st.column_config.LineChartColumn(
            "Trend during January 1995",
            width="medium",
            help="Four weekly national observations from January 1995.",
        ),
    },
    hide_index=True,
)