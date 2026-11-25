"""Small NVE GeoJSON layers with shared area selection and choropleth values."""

import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.theme import BLUE

ROOT = Path(__file__).resolve().parents[1]


@st.cache_data(show_spinner=False)
def load_geometry(kind):
    filename = {"EL": "price_areas.geojson", "NO": "norway.geojson",
                "VASS": "water_areas.geojson"}.get(kind)
    if filename is None:
        return None
    return json.loads((ROOT / "data/geography" / filename).read_text())


def feature_number(feature):
    """Use the explicit VASS number; retain compatibility with NO1–NO5/NO0."""
    properties = feature["properties"]
    return int(properties["area_number"]) if "area_number" in properties else int(properties["region"][2:])


def area_map(history, kind, selected, week, measure="Selected area", weather_values=None):
    import folium
    from branca.colormap import LinearColormap
    from shapely.geometry import shape
    weather_units = {"Temperature (°C)": ("temperature_c", "°C"),
                     "Precipitation (mm)": ("precipitation_mm", "mm")}
    weather = measure in weather_units

    geometry = load_geometry(kind)
    if geometry is None:
        return None
    snapshot = history.loc[
        history.area_type.eq(kind) & history.observation_date.eq(pd.Timestamp(week))
    ].set_index("area_number")
    values = {}
    for feature in geometry["features"]:
        code = feature["properties"]["region"]
        number = feature_number(feature)
        if weather:
            column, unit = weather_units[measure]
            value = (weather_values or {}).get(number, {}).get(column)
        else:
            unit = "%"
            value = float(snapshot.loc[number, "filling_fraction"]) * 100 if number in snapshot.index else None
        if value is not None and not math.isfinite(value):
            value = None
        values[code] = value
        feature["properties"]["map_value"] = "No observation for this week" if value is None else f"{value:.2f} {unit}"
    available = [v for v in values.values() if v is not None]
    low = min(available, default=0) if measure == "Temperature (°C)" else 0
    high = max(available, default=1) if weather else max(100, max(available, default=100))
    if high <= low:
        high = low + 1
    palette = LinearColormap(["#d7e8f8", BLUE], vmin=low, vmax=high)
    # Keep the legend inside the compact map column on laptop screens.
    palette.width = 260
    def style(feature):
        code = feature["properties"]["region"]
        chosen = feature_number(feature) == selected
        value = values[code]
        if measure == "Selected area":
            colour = BLUE if chosen else "#b8cee6"
        else:
            colour = palette(value) if value is not None else "#d8dee7"
        return {"fillColor": colour, "fillOpacity": .85, "color": "#12365b" if chosen else "white",
                "weight": 3 if chosen else 1}
    result = folium.Map(location=[64, 14], zoom_start=4, zoom_snap=.1, zoom_delta=.5, tiles=None,
                        scrollWheelZoom=False, zoom_control=True, attribution_control=False)
    result.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container {background:#e8f2fb!important;}</style>"))
    folium.GeoJson(geometry, style_function=style,
                   highlight_function=lambda feature: {"weight": 3, "color": "#12365b"},
                   tooltip=folium.GeoJsonTooltip(fields=["region", "map_value"],
                       aliases=["Area", measure if weather else "Filling"]),
                   name="NVE areas").add_to(result)
    if kind in ("EL", "VASS"):
        for feature in geometry["features"]:
            code = feature["properties"]["region"]
            point = shape(feature["geometry"]).representative_point()
            fill = style(feature)["fillColor"].lstrip("#")
            brightness = sum(int(fill[i:i + 2], 16) * weight
                             for i, weight in [(0, .299), (2, .587), (4, .114)])
            text_colour = "white" if brightness < 150 else "#12365b"
            folium.Marker([point.y, point.x], tooltip=code,
                icon=folium.DivIcon(html=f'<span style="font:600 12px sans-serif;color:{text_colour};white-space:nowrap">{code}</span>',
                                    icon_size=(48 if kind == "VASS" else 30, 18),
                                    icon_anchor=(24 if kind == "VASS" else 15, 9))).add_to(result)
    bounds = [shape(feature["geometry"]).bounds for feature in geometry["features"]]
    result.fit_bounds([[min(v[1] for v in bounds), min(v[0] for v in bounds)],
                       [max(v[3] for v in bounds), max(v[2] for v in bounds)]], padding=(14, 14))
    if measure != "Selected area" and (not weather or available):
        palette.caption = measure
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
            return feature_number(feature)
    return None
