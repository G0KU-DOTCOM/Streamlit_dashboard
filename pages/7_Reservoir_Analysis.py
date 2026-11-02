import matplotlib

# Streamlit renders figures in a worker thread, without a desktop plot window.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

from dashboard.load_data import load_data_or_stop
from dashboard.reservoir_analysis import plot_reservoir_spectrogram, plot_reservoir_stl
from dashboard.reservoir_views import area_controls

st.set_page_config(page_title="Reservoir Analysis", layout="wide")
st.title("Reservoir Analysis")
st.write("Explore seasonal patterns in weekly reservoir filling with STL and a spectrogram.")

history = load_data_or_stop()
area_type, area_number, labels = area_controls("analysis", history)
if area_number is None:
    st.info("Choose one area to analyse its filling history.")
    st.stop()

area = history.loc[
    history["area_type"].eq(area_type) & history["area_number"].eq(area_number)
].sort_values("observation_date")
if area.empty:
    st.info("There are no filling observations for this area.")
    st.stop()

dates = area["observation_date"]
years = list(range(dates.min().year, dates.max().year + 1))
# A separate multi-year period avoids the usual one-year table/plot selection,
# which was too short to estimate annual seasonality in STL.
last_date = dates.max()
last_full_year = last_date.year if last_date.month == 12 and last_date.day >= 25 else last_date.year - 1
end_year = last_full_year if last_full_year in years else years[-1]
start_year = max(years[0], end_year - 10)
start_year, end_year = st.select_slider(
    "Analysis years", options=years, value=(start_year, end_year),
    disabled=len(years) == 1,
)
st.caption("This period applies to both tabs and is separate from Data Table and Data Plot.")
selected = area.loc[area["observation_date"].dt.year.between(start_year, end_year)]
filling = selected.set_index("observation_date")["filling_fraction"]
filling.name = labels[area_number]
if filling.empty:
    st.info("There are no observations in these years.")
    st.stop()

st.caption(
    f"{filling.name} · {len(filling):,} weekly observations · "
    f"{filling.index.min():%Y-%m-%d} to {filling.index.max():%Y-%m-%d}"
)
stl_tab, spectrum_tab = st.tabs(["STL", "Spectrogram"])
with stl_tab:
    st.write("Separate filling into a long-term trend, an annual seasonal pattern and a residual.")
    columns = st.columns(3)
    seasonal = columns[0].number_input(
        "Seasonal smoother", min_value=3, value=13, step=2,
        help="An odd length. Larger values allow the seasonal pattern to change more slowly across years.",
    )
    trend = columns[1].number_input(
        "Trend smoother (weeks)", min_value=53, value=89, step=2,
        help="An odd length greater than 52. Larger values produce a smoother trend.",
    )
    robust = columns[2].checkbox(
        "Robust fitting", value=True,
        help="Reduce the influence of unusual observations on the fitted trend and seasonal pattern.",
    )
    st.caption("Annual period: 52 weeks. At least 104 consecutive weekly observations are required.")
    try:
        figure = plot_reservoir_stl(filling, seasonal=seasonal, trend=trend, robust=robust)
    except ValueError as exc:
        st.info(str(exc))
    else:
        st.pyplot(figure)
        plt.close(figure)
        st.caption("Filling and trend are percentages; seasonal and residual components are percentage points (pp).")

with spectrum_tab:
    st.write("See how the strength of different frequencies changes over time.")
    if len(filling) < 4:
        st.info("At least four consecutive weekly observations are required.")
    else:
        columns = st.columns(2)
        # Clamp retained settings when the selected series or window becomes shorter.
        st.session_state["spectrum_window"] = min(
            st.session_state.get("spectrum_window", 156), len(filling)
        )
        window = columns[0].number_input(
            "Window length (weeks)", min_value=4, max_value=len(filling), step=1,
            key="spectrum_window",
            help="Longer windows distinguish nearby frequencies but give less precise timing.",
        )
        st.session_state["spectrum_overlap"] = min(
            st.session_state.get("spectrum_overlap", 78), window - 1
        )
        overlap = columns[1].number_input(
            "Window overlap (weeks)", min_value=0, max_value=window - 1, step=1,
            key="spectrum_overlap",
            help="Must be smaller than the window length. More overlap gives more time slices.",
        )
        try:
            figure = plot_reservoir_spectrogram(filling, window_length=window, window_overlap=overlap)
        except ValueError as exc:
            st.info(str(exc))
        else:
            st.pyplot(figure)
            plt.close(figure)
        st.caption(
            "1 cycle per 52-week year represents an annual pattern. Colours show power relative "
            "to the strongest component (dB). Only complete windows are shown at their centre dates."
        )

st.caption("Source: [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/).")
