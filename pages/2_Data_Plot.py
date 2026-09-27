import streamlit as st

from load_data import load_data


st.title("Reservoir Data Plot")
st.write(
    "Choose a reservoir measurement and a range of months to display."
)

# I use the cached function so the CSV is not read again
# whenever the user changes one of the selections.
reservoirs = load_data()

# The national observations give me one continuous series per measurement.
national_data = (
    reservoirs[reservoirs["area_type"] == "NO"]
    .sort_values("observation_date")
    .copy()
)

# I only include columns that represent measurements and therefore
# make sense to display as lines over time.
measurement_columns = [
    "filling_fraction",
    "capacity_twh",
    "stored_energy_twh",
    "previous_week_filling_fraction",
    "weekly_filling_change",
]

selected_column = st.selectbox(
    "Choose a column",
    options=["All columns"] + measurement_columns,
)

# I create year-month labels so the user can select complete months.
national_data["month"] = (
    national_data["observation_date"].dt.strftime("%Y-%m")
)
month_options = national_data["month"].drop_duplicates().tolist()

selected_months = st.select_slider(
    "Choose a range of months",
    options=month_options,
    value=(month_options[0], month_options[0]),
)

start_month, end_month = selected_months

filtered_data = national_data[
    national_data["month"].between(start_month, end_month)
]

# One selected column gives one line, while "All columns"
# displays all reservoir measurements in the same chart.
columns_to_plot = (
    measurement_columns
    if selected_column == "All columns"
    else [selected_column]
)

st.subheader(f"National reservoir data from {start_month} to {end_month}")

st.line_chart(
    filtered_data,
    x="observation_date",
    y=columns_to_plot,
    x_label="Observation date",
    y_label="Value on original scale",
)

st.caption(
    "Only measurement columns are included because dates, area names and "
    "identification columns are not measurements that can be compared as lines."
)