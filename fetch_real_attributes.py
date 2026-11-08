"""Replace two neighborhood placeholders with real public data, and record where each value came from.

  street_trees               City of Buffalo "Tree Inventory" (Open Data Buffalo, dataset n4ni-uuec).
                             Live street trees, assigned to the nearest neighborhood center within 1.5 km
                             (the same rule fill_neighborhoods.py uses for census tracts).
  medical_device_households  HHS emPOWER: Medicare beneficiaries with a claim for electricity-dependent
                             durable medical equipment, by ZIP code. ZIP counts are split across census
                             tracts by the Census 2020 ZCTA-to-tract relationship file, weighted by each
                             tract's households (ACS), then summed over each neighborhood's tracts.
                             NOTE: this counts people (Medicare only), not households; column name kept so
                             the simulator keeps working.

  overhead_line_share        no public source found -> stays a labeled placeholder (overhead_line_share_est).

Usage:
    python fetch_real_attributes.py          # updates data/neighborhoods.csv, writes data/sources.json
    python load_to_tigerdata.py              # then reload the neighborhoods table
"""
import csv
import io
import json
import math
import os
import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
CSV = HERE / "data" / "neighborhoods.csv"
SOURCES = HERE / "data" / "sources.json"

TREES_ID = "n4ni-uuec"
TREES_URL = f"https://data.buffalony.gov/resource/{TREES_ID}.json"
NOT_TREES = ("VACANT", "STUMP", "STUMP OBSTRUCTED", "unsuitable vacant")
EMPOWER_URL = ("https://services2.arcgis.com/ZQ4jTQn6k7VPXEwO/arcgis/rest/services/"
               "HHS_emPOWER_REST_Service_Public/FeatureServer/1/query")
REL_URL = ("https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/"
           "tab20_zcta520_tract20_natl.txt")
ACS_URL = "https://api.census.gov/data/2023/acs/acs5"
ERIE = ("36", "029")
MAX_KM = 1.5


def km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def nearest(lat, lon, hoods):
    best = min(hoods.itertuples(), key=lambda h: km(lat, lon, h.lat, h.lon))
    return best.neighborhood if km(lat, lon, best.lat, best.lon) <= MAX_KM else None


# ------------------------------------------------------------------ street trees
def tree_counts(hoods):
    where = " AND ".join(f"common_name != '{n}'" for n in NOT_TREES) + " AND latitude IS NOT NULL"
    counts, total, unassigned, offset = defaultdict(int), 0, 0, 0
    while True:
        rows = requests.get(TREES_URL, params={"$select": "latitude,longitude", "$where": where,
                                               "$limit": 50000, "$offset": offset, "$order": "site_id"},
                            timeout=120).json()
        if not rows:
            break
        for r in rows:
            total += 1
            n = nearest(float(r["latitude"]), float(r["longitude"]), hoods)
            if n:
                counts[n] += 1
            else:
                unassigned += 1
        offset += len(rows)
    return dict(counts), total, unassigned


# ------------------------------------------------------------------ emPOWER
def empower_by_zip():
    r = requests.get(EMPOWER_URL, params={
        "where": "STATE='NY' AND COUNTY='Erie'", "outFields": "Zip_Code,Medicare_Benes,Power_Dependent_Devices_DME",
        "returnGeometry": "false", "f": "json"}, timeout=120).json()
    if "error" in r:
        raise RuntimeError(r["error"])
    return {f["attributes"]["Zip_Code"]: int(f["attributes"]["Power_Dependent_Devices_DME"] or 0)
            for f in r["features"]}


def zcta_tract_pieces():
    """(zcta, 6-digit Erie tract, land area of the overlap) for every Erie County tract piece."""
    text = requests.get(REL_URL, timeout=300).text
    rows = csv.DictReader(io.StringIO(text), delimiter="|")
    pieces = []
    for r in rows:
        t = r["GEOID_TRACT_20"]
        if t.startswith("".join(ERIE)) and r["GEOID_ZCTA5_20"]:
            pieces.append((r["GEOID_ZCTA5_20"], t[5:], float(r["AREALAND_PART"] or 0), float(r["AREALAND_TRACT_20"] or 0)))
    return pieces


def tract_households():
    params = {"get": "B11001_001E", "for": "tract:*", "in": f"state:{ERIE[0]} county:{ERIE[1]}"}
    if os.environ.get("CENSUS_API_KEY"):
        params["key"] = os.environ["CENSUS_API_KEY"].strip()
    data = requests.get(ACS_URL, params=params, timeout=120).json()
    h = data[0]
    return {r[h.index("tract")]: int(r[0] or 0) for r in data[1:]}


def medical_by_neighborhood(hoods):
    zip_counts = empower_by_zip()
    pieces = zcta_tract_pieces()
    hh = tract_households()
    # weight of each (zip, tract) piece = tract households x share of the tract's land in that ZIP
    w = [(z, t, hh.get(t, 0) * (a / at if at else 0)) for z, t, a, at in pieces]
    zip_total = defaultdict(float)
    for z, _, x in w:
        zip_total[z] += x
    tract_count = defaultdict(float)
    for z, t, x in w:
        if z in zip_counts and zip_total[z] > 0:
            tract_count[t] += zip_counts[z] * x / zip_total[z]
    out = {}
    for row in hoods.itertuples():
        tracts = str(row.census_tracts).split()
        out[row.neighborhood] = round(sum(tract_count.get(t.zfill(6), 0) for t in tracts))
    return out, len(zip_counts)


def main():
    hoods = pd.read_csv(CSV, dtype={"census_tracts": str})
    today = str(date.today())

    print("Street trees (Open Data Buffalo)...")
    trees, total, unassigned = tree_counts(hoods)
    print("emPOWER electricity-dependent Medicare beneficiaries...")
    med, n_zips = medical_by_neighborhood(hoods)

    old = hoods[["neighborhood", "street_trees", "medical_device_households_est"]].copy()
    hoods["street_trees"] = hoods["neighborhood"].map(trees).fillna(0).astype(int)
    hoods = hoods.rename(columns={"medical_device_households_est": "medical_device_households"})
    hoods["medical_device_households"] = hoods["neighborhood"].map(med).astype(int)
    hoods["data_quality"] = "census + Open Data Buffalo trees + HHS emPOWER; overhead lines estimated"

    shutil.copy(CSV, CSV.with_suffix(".backup.csv"))
    hoods.to_csv(CSV, index=False)

    sources = {
        "street_trees": {
            "status": "real", "source": "City of Buffalo, Tree Inventory (Dept. of Public Works, Parks & Streets)",
            "url": f"https://data.buffalony.gov/d/{TREES_ID}", "license": "Public Domain (U.S. Government Works)",
            "granularity": "one row per tree site with lat/lon", "data_as_of": "current inventory on retrieval date "
            "(not December 2022)", "method": f"excluded {', '.join(NOT_TREES)}; assigned to nearest neighborhood "
            f"center within {MAX_KM} km", "trees_total": total, "trees_unassigned_beyond_1_5km": unassigned,
            "retrieved": today},
        "medical_device_households": {
            "status": "real (allocated)", "source": "HHS emPOWER REST Service, Electricity Dependent DME - ALL - ZipLevel",
            "url": EMPOWER_URL.removesuffix("/query"), "license": "public HHS data (de-identified; no license stated)",
            "measure": "Medicare FFS + Medicare Advantage beneficiaries with a claim for electricity-dependent DME "
                       "(people, Medicare only; not households)",
            "granularity": "ZIP code", "zips_in_erie_county": n_zips,
            "data_as_of": "current monthly release on retrieval date (not December 2022)",
            "method": "ZIP counts split to 2020 census tracts by Census ZCTA-tract relationship file, weighted by "
                      "ACS 2023 tract households x land-area share; summed over each neighborhood's tracts",
            "crosswalk_url": REL_URL, "retrieved": today},
        "overhead_line_share": {"status": "placeholder", "value": 0.85,
                                "note": "no public data on overhead vs underground lines by neighborhood found"},
    }
    SOURCES.write_text(json.dumps(sources, indent=2))

    cmp = old.merge(hoods[["neighborhood", "street_trees", "medical_device_households"]], on="neighborhood",
                    suffixes=("_old", "_new"))
    cmp["trees_per_hh"] = (hoods["street_trees"] / hoods["households"]).round(3)
    print(cmp.to_string(index=False))
    print(f"\nTrees: {total} live trees, {unassigned} beyond {MAX_KM} km of any center (not counted)")
    print(f"Saved {CSV} (old kept as neighborhoods.backup.csv) and {SOURCES}")


if __name__ == "__main__":
    main()
