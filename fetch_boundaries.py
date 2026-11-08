"""Neighborhood boundary shapes for the map, built from official Census 2020 tract boundaries.

Each neighborhood in data/neighborhoods.csv is defined as a list of census tracts (column census_tracts),
so its shape is the union of those tracts. Source: U.S. Census Bureau TIGERweb, Census 2020 tracts
(public domain, U.S. Government work). Tracts were assigned to the nearest neighborhood center, so these
are approximate neighborhood areas, not official City of Buffalo neighborhood lines.

    python fetch_boundaries.py      # writes frontend/public/data/neighborhoods.geojson
"""
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

HERE = Path(__file__).parent
OUT = HERE / "frontend" / "public" / "data" / "neighborhoods.geojson"
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/10/query"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    hoods = pd.read_csv(HERE / "data" / "neighborhoods.csv", dtype={"census_tracts": str})
    tract_of = {}
    for r in hoods.itertuples():
        for t in str(r.census_tracts).split():
            tract_of[t.zfill(6)] = r.neighborhood
    codes = ",".join(f"'{t}'" for t in sorted(tract_of))
    resp = requests.get(TIGER, params={
        "where": f"STATE='36' AND COUNTY='029' AND TRACT IN ({codes})",
        "outFields": "GEOID,TRACT", "returnGeometry": "true", "outSR": "4326", "f": "geojson",
    }, timeout=120)
    resp.raise_for_status()
    feats = resp.json()["features"]
    found = {f["properties"]["TRACT"] for f in feats}
    missing = sorted(set(tract_of) - found)

    parts = {}
    for f in feats:
        parts.setdefault(tract_of[f["properties"]["TRACT"]], []).append(shape(f["geometry"]).buffer(0))
    out = []
    for r in hoods.itertuples():
        geom = unary_union(parts.get(r.neighborhood, []))
        if geom.is_empty:
            continue
        geom = geom.simplify(0.0002, preserve_topology=True)      # ~20 m: smaller file, same look
        out.append({"type": "Feature", "id": slug(r.neighborhood),
                    "properties": {"id": slug(r.neighborhood), "name": r.neighborhood},
                    "geometry": mapping(geom)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "source": "U.S. Census Bureau TIGERweb, Census 2020 tracts (public domain); tracts grouped into "
                  f"neighborhoods per data/neighborhoods.csv. Retrieved {date.today()}.",
        "features": out}), encoding="utf-8")
    print(f"{len(feats)} tracts -> {len(out)} neighborhood shapes -> {OUT} ({OUT.stat().st_size // 1024} KB)")
    if missing:
        print(f"! tracts not found in TIGERweb: {missing}")


if __name__ == "__main__":
    main()
