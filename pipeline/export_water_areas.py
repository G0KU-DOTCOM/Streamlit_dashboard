"""Convert Part 3's grouped NVE-region shapefile to the VASS map layer.

Run from the project root with python -m pipeline.export_water_areas.
The grouping follows the assignment: East = RS + RØ, West = RV,
North = RM + RN. These are overview regions, not individual catchments.
"""

import json
from pathlib import Path

import geopandas as gpd
import shapely

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {1: ("Øst", ["RS", "RØ"]), 2: ("Vest", ["RV"]), 3: ("Nord", ["RM", "RN"])}


def export(root=ROOT):
    folder = Path(root) / "data/geography"
    regions = gpd.read_file(folder / "nve_regioner.shp").to_crs(25833)
    land = gpd.read_file(folder / "norge_land.shp").to_crs(regions.crs)
    land_mask = shapely.set_precision(shapely.union_all(shapely.make_valid(land.geometry)), 1)
    geometries = []
    for _, codes in GROUPS.values():
        boundary = shapely.union_all(regions.loc[regions.REGION.isin(codes), "geometry"])
        geometries.append(shapely.set_precision(boundary, 1).intersection(land_mask))
    assert shapely.coverage_is_valid(geometries), "Water regions must have matching, non-overlapping edges."
    geometries = shapely.coverage_simplify(geometries, tolerance=750)
    assert shapely.coverage_is_valid(geometries)
    layer = gpd.GeoDataFrame([
        {"region": f"VASS{number}", "area_number": number, "name": name,
         "source_regions": "+".join(codes)}
        for number, (name, codes) in GROUPS.items()
    ], geometry=geometries, crs=regions.crs).to_crs(4326)
    assert layer.geometry.is_valid.all() and not layer.geometry.is_empty.any()
    result = json.loads(layer.to_json(drop_id=True, to_wgs84=True))
    result["provenance"] = {
        "source": "https://kart.nve.no/enterprise/rest/services/Mapservices/Administrasjon2/MapServer/0",
        "method": "Part 3 assignment grouping of NVE regions, clipped to Norway land and simplified jointly at 750 metres.",
        "scope": "Overview outlines for the three published VASS groups; not detailed hydrological catchments.",
        "data_source": "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData",
        "publication_reference": "https://www.nve.no/nytt-fra-nve/rapporter-vassmagasinstatistikk/",
        "unreported_area": "VASS4 is listed in API metadata but has no observations in the retrieved history. No values or separate outline are invented for it.",
    }
    destination = folder / "water_areas.geojson"
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return destination


if __name__ == "__main__":
    print(export())
