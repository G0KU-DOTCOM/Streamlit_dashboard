import streamlit as st

from load_data import NVEDataError, load_areas, load_data_or_stop

st.title("Reservoir API")
st.write("Explore reservoir filling fractions by period and geographical area.")
reservoirs = load_data_or_stop()

# Like D2D's Streamlit examples, widgets rerun the page but reuse cached data.
months = reservoirs["observation_date"].dt.strftime("%Y-%m")
month_options = sorted(months.unique())
start_month, end_month = st.select_slider(
    "Choose a period (months)",
    options=month_options,
    value=(month_options[max(0, len(month_options) - 12)], month_options[-1]),
)
area_type = st.radio("Choose area type", ["EL", "NO", "VASS"], horizontal=True)
st.caption({
    "EL": "EL: electricity price areas (NO1–NO5).",
    "NO": "NO: Norway as a whole (area number 0).",
    "VASS": "VASS: NVE's watercourse regions.",
}[area_type])

selected = reservoirs.loc[
    months.between(start_month, end_month) & reservoirs["area_type"].eq(area_type)
].copy()
try:
    areas = load_areas()
    selected_areas = areas.loc[areas["area_type"].eq(area_type)]
except NVEDataError as exc:
    st.warning(str(exc))
    selected_areas = None

if selected.empty:
    st.info("There are no observations for this period and area type.")
else:
    # Each area has its own line. Missing values remain missing; overlapping
    # geographical groups are never added together.
    lines = selected.pivot(
        index="observation_date", columns="area_number", values="filling_fraction"
    ).sort_index()
    labels = {number: f"{area_type}{number}" for number in lines.columns}
    if selected_areas is not None:
        labels.update({
            row.area_number: f"{row.name} (area {row.area_number})"
            for row in selected_areas.itertuples()
        })
        missing = selected_areas.loc[
            ~selected_areas["area_number"].isin(lines.columns), "name"
        ].tolist()
        if missing:
            st.info("No observations in this period for: " + ", ".join(missing) + ".")
    st.line_chart(
        lines.rename(columns=labels),
        x_label="Observation date", y_label="Filling fraction (1.0 = 100%)",
    )
    st.caption(f"{len(selected):,} weekly area observations · {start_month} to {end_month}")

with st.expander("Data source and downloads"):
    st.markdown(
        "Source: [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/), "
        "using `HentOffentligData` and `HentOmråder`. "
        "[API documentation](https://biapi.nve.no/magasinstatistikk/swagger/index.html)."
    )
    st.write(
        "NVE's history endpoint has no date-range parameters. The period slider "
        "filters the downloaded history locally. Changing the period or area "
        "does not trigger another download while the cache is valid."
    )
    st.write(
        "History is cached for 24 hours and area descriptions for 7 days. "
        "The next page visit after expiry fetches fresh data; restarting the app "
        "also clears the cache. Each history response is limited to 8 MiB and "
        "each area response to 128 KiB. No data is written to a database."
    )
    st.caption(
        f"History retrieved (UTC): {reservoirs.attrs['fetched_at']} · "
        f"Decoded JSON: {reservoirs.attrs['download_bytes'] / 1024**2:.2f} MiB"
    )
    if selected_areas is not None:
        st.dataframe(selected_areas[["area_number", "name", "description"]], hide_index=True)
