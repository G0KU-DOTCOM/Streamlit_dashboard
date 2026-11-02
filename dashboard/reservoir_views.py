"""Shared reservoir selections and views; no database writes or extra downloads."""
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from dashboard.load_data import NVEDataError, load_areas, load_data_or_stop

MEASUREMENTS = {
    "filling_fraction": "Filling fraction (1.0 = 100%)",
    "capacity_twh": "Capacity (TWh)",
    "stored_energy_twh": "Stored energy (TWh)",
    "previous_week_filling_fraction": "Previous week filling fraction",
    "weekly_filling_change": "Weekly change in filling fraction",
}


@dataclass
class ReservoirSelection:
    history: pd.DataFrame
    data: pd.DataFrame
    area_type: str
    start: str
    end: str
    labels: dict
    area_number: int | None = None


def remember_selection(key, widget_key):
    # A separate non-widget key survives navigation through the pages/ directory.
    # This follows Streamlit's documented multipage widget-state pattern.
    st.session_state[key] = st.session_state[widget_key]


def area_controls(view, history):
    """Share area type and concrete area across reservoir and weather pages."""
    area_type = st.session_state.get("nve_area_type", "EL")
    st.session_state["nve_area_type"] = area_type if area_type in ("EL", "NO", "VASS") else "EL"
    area_key = f"_nve_area_type_{view}"
    area_type = st.radio(
        "Choose area type", ["EL", "NO", "VASS"], horizontal=True,
        index=["EL", "NO", "VASS"].index(st.session_state["nve_area_type"]),
        key=area_key, on_change=remember_selection, args=("nve_area_type", area_key),
    )
    st.caption({
        "EL": "Electricity price areas.",
        "NO": "Norway as a whole (area number 0).",
        "VASS": "NVE watercourse regions.",
    }[area_type])
    # Include known areas without observations so their absence remains visible.
    numbers = history.loc[history["area_type"].eq(area_type), "area_number"].unique()
    labels = {number: f"{area_type}{number}" for number in sorted(numbers)}
    try:
        areas = load_areas()
        for row in areas.loc[areas["area_type"].eq(area_type)].itertuples():
            labels[row.area_number] = f"{row.name} (area {row.area_number})"
    except NVEDataError as exc:
        st.warning(str(exc))
    labels = dict(sorted(labels.items()))
    # Keep an area choice per type; switching EL/VASS must not reinterpret its number.
    options = [None] + list(labels)
    saved_key = f"nve_area_number_{area_type}"
    default_number = next(iter(labels)) if len(labels) == 1 else None
    saved_number = st.session_state.get(saved_key, default_number)
    if saved_number not in options:
        saved_number = default_number
    st.session_state[saved_key] = saved_number
    widget_key = f"_{saved_key}_{view}"
    area_number = st.selectbox(
        "Choose area", options=options, index=options.index(saved_number),
        format_func=lambda number: "All areas" if number is None else labels[number],
        key=widget_key, on_change=remember_selection, args=(saved_key, widget_key),
    )
    st.caption("Area choices are shared by the reservoir and weather pages.")
    return area_type, area_number, labels


def reservoir_controls(view):
    """Render shared reservoir controls and filter after the cached download."""
    history = load_data_or_stop()
    dates = history["observation_date"]
    months = pd.period_range(dates.min(), dates.max(), freq="M").astype(str).tolist()
    default = (months[max(0, len(months) - 12)], months[-1])
    saved = st.session_state.get("nve_period", default)
    if len(saved) != 2 or any(month not in months for month in saved):
        saved = default
    st.session_state["nve_period"] = tuple(sorted(saved))
    period_key = f"_nve_period_{view}"
    start, end = st.select_slider(
        "Choose a period (months)", options=months,
        value=st.session_state["nve_period"], key=period_key,
        on_change=remember_selection, args=("nve_period", period_key), disabled=len(months) == 1,
    )
    area_type, area_number, labels = area_controls(view, history)
    selected = history.loc[
        dates.dt.strftime("%Y-%m").between(start, end) & history["area_type"].eq(area_type)
    ].copy()
    if area_number is not None:
        selected = selected.loc[selected["area_number"].eq(area_number)]
        labels = {area_number: labels[area_number]}
    st.caption(
        "The reservoir period is shared by Data Table and Data Plot. "
        "It filters cached NVE history after download."
    )
    missing = [name for number, name in labels.items() if not selected["area_number"].eq(number).any()]
    if missing:
        st.info("No observations in this period for: " + ", ".join(missing) + ".")
    st.caption(f"{len(selected):,} weekly area observations · {start} to {end}")
    return ReservoirSelection(history, selected, area_type, start, end, labels, area_number)


def area_lines(selection, column):
    """Align weekly observations without filling missing data or summing areas."""
    data = selection.data
    lines = data.pivot(index="observation_date", columns="area_number", values=column)
    # Explicit missing Sundays preserve positions in the weekly sparklines.
    # Retain any additional dates supplied by the source as well.
    weeks = pd.date_range(selection.start, pd.Period(selection.end, "M").end_time, freq="W-SUN")
    index = weeks.union(pd.DatetimeIndex(data["observation_date"].unique())).sort_values()
    lines = lines.reindex(index=index, columns=list(selection.labels))
    lines.index.name = "observation_date"
    return lines.rename(columns=selection.labels)


def area_summary(selection):
    """One row per area, with separate sparklines for the five measurements."""
    series = {column: area_lines(selection, column) for column in MEASUREMENTS}
    rows = []
    for number, name in selection.labels.items():
        area = selection.data.loc[selection.data["area_number"].eq(number)]
        row = {
            "area": name, "area_number": number, "observations": len(area),
            "first_observation": area["observation_date"].min(),
            "last_observation": area["observation_date"].max(),
        }
        for column, lines in series.items():
            values = lines[name]
            first, last = values.first_valid_index(), values.last_valid_index()
            # LineChartColumn rejects nulls inside an array. Trim only empty
            # edges; an interior gap leaves the whole cell empty rather than
            # replacing missing values or connecting across an unknown week.
            observed = values.loc[first:last] if first is not None else values.iloc[:0]
            row[column] = (
                observed.astype(float).tolist()
                if len(observed) and observed.notna().all() else None
            )
        rows.append(row)
    return pd.DataFrame(rows)


def plot_measurement(selection, column, label=None):
    st.line_chart(
        area_lines(selection, column), x_label="Observation date",
        y_label=label or MEASUREMENTS.get(column, column),
    )


def source_details(history):
    """Describe actual downloads, including the unresolved range limitation."""
    with st.expander("Data source and downloads"):
        st.markdown(
            "Source: [NVE Magasinstatistikk](https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/). "
            "[API documentation](https://biapi.nve.no/magasinstatistikk/swagger/index.html). "
            "The app uses `HentOffentligData` and `HentOmråder`."
        )
        st.write(
            "The documented history endpoint has no date-range parameters. "
            "The slider filters downloaded history locally; it does not limit "
            "the dates sent by NVE."
        )
        st.write(
            "History is cached for 24 hours and area descriptions for 7 days. "
            "Selections reuse these caches. After expiry, the next visit downloads "
            "fresh data; app restarts also clear the caches. History responses are "
            "limited to 8 MiB and area responses to 128 KiB. No database is written."
        )
        st.caption(
            f"History retrieved (UTC): {history.attrs.get('fetched_at', 'Unknown')} · "
            f"Decoded JSON: {history.attrs.get('download_bytes', 0) / 1024**2:.2f} MiB"
        )
