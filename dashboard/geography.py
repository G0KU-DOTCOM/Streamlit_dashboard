"""Small published NVE GeoJSON layers and a selectable price-area map."""

import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.theme import BLUE

ROOT = Path(__file__).resolve().parents[1]


@st.cache_data(show_spinner=False)
def load_geometry(kind):
    filename = {"EL": "price_areas.geojson", "NO": "norway.geojson"}.get(kind)
    if filename is None:
        return None
    return json.loads((ROOT / "data/geography" / filename).read_text())


def area_map(history, kind, selected, week, measure="Selected area"):
    import folium
    from branca.colormap import LinearColormap
    from shapely.geometry import shape

    geometry = load_geometry(kind)
    if geometry is None:
        return None
    snapshot = history.loc[
        history.area_type.eq(kind) & history.observation_date.eq(pd.Timestamp(week))
    ].set_index("area_number")
    values = {}
    for feature in geometry["features"]:
        code = feature["properties"]["region"]
        number = int(code[2:])
        value = float(snapshot.loc[number, "filling_fraction"]) * 100 if number in snapshot.index else None
        values[code] = value
        feature["properties"]["filling"] = "No observation" if value is None else f"{value:.2f}%"
    chosen = f"NO{selected}" if selected is not None else None
    palette = LinearColormap(["#d7e8f8", BLUE], vmin=0,
                              vmax=max(100, max((v for v in values.values() if v is not None), default=100)))
    def style(feature):
        code = feature["properties"]["region"]
        value = values[code]
        colour = palette(value) if measure == "Filling (%)" and value is not None else (
            BLUE if code == chosen else "#b8cee6")
        return {"fillColor": colour, "fillOpacity": .85, "color": "#12365b" if code == chosen else "white",
                "weight": 3 if code == chosen else 1}
    result = folium.Map(location=[64, 14], zoom_start=4, zoom_snap=.1, zoom_delta=.5, tiles=None,
                        scrollWheelZoom=False, zoom_control=True, attribution_control=False)
    result.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container {background:#e8f2fb!important;}</style>"))
    folium.GeoJson(geometry, style_function=style,
                   highlight_function=lambda feature: {"weight": 3, "color": "#12365b"},
                   tooltip=folium.GeoJsonTooltip(fields=["region", "filling"], aliases=["Area", "Filling"]),
                   name="NVE areas").add_to(result)
    if kind == "EL":
        for feature in geometry["features"]:
            code = feature["properties"]["region"]
            point = shape(feature["geometry"]).representative_point()
            text_colour = "white" if code == chosen else "#12365b"
            folium.Marker([point.y, point.x], tooltip=code,
                icon=folium.DivIcon(html=f'<span style="font:600 12px sans-serif;color:{text_colour};white-space:nowrap">{code}</span>',
                                    icon_size=(30, 18), icon_anchor=(15, 9))).add_to(result)
    bounds = [shape(feature["geometry"]).bounds for feature in geometry["features"]]
    result.fit_bounds([[min(v[1] for v in bounds), min(v[0] for v in bounds)],
                       [max(v[3] for v in bounds), max(v[2] for v in bounds)]], padding=(14, 14))
    if measure == "Filling (%)":
        palette.caption = "Filling (%)"
        palette.add_to(result)
    return result


def area_from_map_click(event, kind):
    from shapely.geometry import Point, shape
    geometry = load_geometry(kind)
    click = event.get("last_object_clicked") or event.get("last_clicked") if event else None
    if geometry is None or not click or "lat" not in click or "lng" not in click:
        return None
    try:
        longitude, latitude = float(click["lng"]), float(click["lat"])
    except (ValueError, TypeError):
        return None
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        return None
    point = Point(longitude, latitude)
    for feature in geometry["features"]:
        if shape(feature["geometry"]).covers(point):
            return int(feature["properties"]["region"][2:])
    return None
