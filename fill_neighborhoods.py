"""
Fill data/neighborhoods.csv with REAL data instead of placeholders.

  Census (American Community Survey 2023 5-year, by census tract, Erie County):
    population, households, median year built, share of residents 65+
  Open Data Buffalo (data.buffalony.gov): street tree counts
  Hospitals: major Buffalo hospitals, placed in the nearest neighborhood

How neighborhoods are built: each Buffalo census tract is assigned to the nearest
neighborhood center (within 1.5 km); tract numbers are then added up per
neighborhood. Boundaries are therefore approximate: say so on your data slide.

Still ESTIMATED (no public data): overhead_line_share, medical_device_households
(scaled from households and elderly share).

Usage:
  python fill_neighborhoods.py          # writes data/neighborhoods.csv (backs up the old one)
  python load_to_tigerdata.py           # reload into Tiger Cloud
  python simulator.py                   # rerun
"""
import io
import math
import os
import shutil
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
CSV = HERE / "data" / "neighborhoods.csv"

ACS_YEAR = 2023
ACS_URL = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
GAZETTEER_URL = ("https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
                 "2023_Gazetteer/2023_gaz_tracts_36.txt")
SOCRATA_CATALOG = "https://api.us.socrata.com/api/catalog/v1"
BUFFALO_DOMAIN = "data.buffalony.gov"
MAX_KM = 1.5

AGE_65_PLUS = ([f"B01001_{i:03d}E" for i in range(20, 26)] +     # male 65+
               [f"B01001_{i:03d}E" for i in range(44, 50)])      # female 65+
ACS_VARS = ["B01003_001E", "B11001_001E", "B25035_001E", *AGE_65_PLUS]

# Approximate locations (verify on a map). Assigned to the nearest neighborhood center.
HOSPITALS = [
    ("Buffalo General Medical Center", 42.9003, -78.8665),
    ("Roswell Park Comprehensive Cancer Center", 42.8964, -78.8662),
    ("Oishei Children's Hospital", 42.9010, -78.8670),
    ("Erie County Medical Center (ECMC)", 42.9264, -78.8295),
    ("Sisters of Charity Hospital", 42.9290, -78.8515),
    ("Mercy Hospital of Buffalo", 42.8420, -78.8075),
    ("VA Western New York Medical Center", 42.9512, -78.8146),
]


def km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def nearest(lat, lon, hoods, max_km=MAX_KM):
    best = min(hoods.itertuples(), key=lambda h: km(lat, lon, h.lat, h.lon))
    d = km(lat, lon, best.lat, best.lon)
    return (best.neighborhood, d) if d <= max_km else (None, d)


# --------------------------------------------------------------------------
# Census
# --------------------------------------------------------------------------
def tract_centers():
    r = requests.get(GAZETTEER_URL, timeout=60)
    r.raise_for_status()
    g = pd.read_csv(io.StringIO(r.text), sep="\t", dtype={"GEOID": str})
    g.columns = [c.strip() for c in g.columns]
    g = g[g["GEOID"].str.startswith("36029")]                    # Erie County
    return g[["GEOID", "INTPTLAT", "INTPTLONG"]].rename(
        columns={"INTPTLAT": "lat", "INTPTLONG": "lon"})


def acs_tracts():
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "The Census API needs a free key.\n"
            "  1. Request one at https://www.census.gov/data/developers/api-key.html\n"
            "  2. Click the activation link in the email they send\n"
            "  3. Add this line to your .env file:  CENSUS_API_KEY=your_key_here")
    params = {"get": ",".join(["NAME", *ACS_VARS]), "for": "tract:*",
              "in": "state:36 county:029", "key": key}
    r = requests.get(ACS_URL, params=params, timeout=60)
    try:
        rows = r.json()
    except ValueError:
        hint = ("Your key may not be activated yet: click the link in the Census email."
                if "key" in r.url.lower() and "missing" not in r.url.lower() else "")
        raise SystemExit(f"Census API error (HTTP {r.status_code}). {hint}\n{r.text[:300]}")
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    for v in ACS_VARS:
        df[v] = pd.to_numeric(df[v], errors="coerce")
    df.loc[df["B25035_001E"] < 1800, "B25035_001E"] = None        # Census "no data" codes
    df["age65"] = df[AGE_65_PLUS].sum(axis=1)
    return df


def census_by_neighborhood(hoods):
    tracts = tract_centers().merge(acs_tracts(), on="GEOID")
    tracts["neighborhood"], tracts["km"] = zip(*(nearest(t.lat, t.lon, hoods)
                                                  for t in tracts.itertuples()))
    # Neighborhoods with no tract within range get their single closest tract
    for h in hoods.itertuples():
        if not (tracts["neighborhood"] == h.neighborhood).any():
            i = tracts.apply(lambda t: km(t.lat, t.lon, h.lat, h.lon), axis=1).idxmin()
            tracts.loc[i, "neighborhood"] = h.neighborhood
    used = tracts.dropna(subset=["neighborhood"])

    out = {}
    for name, g in used.groupby("neighborhood"):
        hh = g["B11001_001E"].sum()
        built = g.dropna(subset=["B25035_001E"])
        out[name] = {
            "population": int(g["B01003_001E"].sum()),
            "households": int(hh),
            # household-weighted average of tract medians (Census top-codes very old
            # housing as 1939, so the real age of many homes is older than this)
            "median_year_built": int(round((built["B25035_001E"] * built["B11001_001E"]).sum()
                                           / max(built["B11001_001E"].sum(), 1))) if len(built) else None,
            "age_65_plus_share": round(g["age65"].sum() / max(g["B01003_001E"].sum(), 1), 3),
            "tracts": " ".join(t[5:] for t in sorted(g["GEOID"])),
        }
    return out


# --------------------------------------------------------------------------
# Trees (Open Data Buffalo / Socrata)
# --------------------------------------------------------------------------
def tree_counts(hoods):
    cat = requests.get(SOCRATA_CATALOG, params={"domains": BUFFALO_DOMAIN, "q": "tree inventory",
                                                "only": "dataset"}, timeout=60).json()
    ids = [(x["resource"]["id"], x["resource"]["name"]) for x in cat.get("results", [])
           if "tree" in x["resource"]["name"].lower()]
    if not ids:
        raise RuntimeError("no tree dataset found in Open Data Buffalo catalog")
    rid, rname = ids[0]
    print(f"  Using Open Data Buffalo dataset '{rname}' ({rid})")

    counts = {n: 0 for n in hoods["neighborhood"]}
    offset, page = 0, 50000
    while True:
        rows = requests.get(f"https://{BUFFALO_DOMAIN}/resource/{rid}.json",
                            params={"$limit": page, "$offset": offset}, timeout=120).json()
        if not rows:
            break
        for r in rows:
            text = " ".join(str(v).lower() for k, v in r.items()
                            if "species" in k.lower() or "common" in k.lower() or "botanical" in k.lower())
            if "vacant" in text or "stump" in text:
                continue                                    # empty planting sites
            lat, lon = _latlon(r)
            if lat is None:
                continue
            name, _ = nearest(lat, lon, hoods)
            if name:
                counts[name] += 1
        offset += page
    return counts


def _latlon(r):
    lat = next((r[k] for k in r if k.lower() in ("latitude", "lat", "y")), None)
    lon = next((r[k] for k in r if k.lower() in ("longitude", "long", "lon", "x")), None)
    if lat is None:
        for v in r.values():
            if isinstance(v, dict) and "latitude" in v:
                lat, lon = v.get("latitude"), v.get("longitude")
            elif isinstance(v, dict) and v.get("type") == "Point":
                lon, lat = v["coordinates"]
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


# --------------------------------------------------------------------------
def main():
    hoods = pd.read_csv(CSV)
    hoods = hoods.rename(columns=lambda c: c.removesuffix("_est"))
    report = []

    print("Census ACS by tract...")
    census = census_by_neighborhood(hoods)
    for col in ("population", "households", "median_year_built", "age_65_plus_share"):
        hoods[col] = hoods["neighborhood"].map(lambda n: census.get(n, {}).get(col))
    hoods["census_tracts"] = hoods["neighborhood"].map(lambda n: census.get(n, {}).get("tracts", ""))
    report.append(f"Census ACS {ACS_YEAR} 5-year (real)")

    print("Street trees...")
    try:
        trees = tree_counts(hoods)
        hoods["street_trees"] = hoods["neighborhood"].map(trees)
        report.append("Open Data Buffalo tree inventory (real)")
    except Exception as e:
        print(f"  ! Tree download failed ({e}); keeping previous street_trees values")
        report.append("street trees: previous values (estimate)")

    print("Hospitals...")
    facilities = {n: [] for n in hoods["neighborhood"]}
    for name, lat, lon in HOSPITALS:
        n, d = nearest(lat, lon, hoods, max_km=3.0)
        if n:
            facilities[n].append(name)
            print(f"  {name} -> {n} ({d:.1f} km from center)")
    hoods["critical_facilities"] = hoods["neighborhood"].map(lambda n: "; ".join(facilities[n]))

    # Estimates (no public data): disclosed via column suffix and data_quality
    hoods["medical_device_households"] = (hoods["households"]
                                          * (0.01 + 0.08 * hoods["age_65_plus_share"])).round().astype(int)
    hoods = hoods.rename(columns={"overhead_line_share": "overhead_line_share_est",
                                  "medical_device_households": "medical_device_households_est"})
    hoods["data_quality"] = "census+open-data; lines & medical estimated"

    if CSV.exists():
        shutil.copy(CSV, CSV.with_suffix(".backup.csv"))
    hoods.to_csv(CSV, index=False)

    cols = ["neighborhood", "population", "households", "median_year_built",
            "age_65_plus_share", "street_trees", "critical_facilities"]
    print("\n" + hoods[cols].to_string(index=False))
    print(f"\nSaved {CSV}  (old file kept as neighborhoods.backup.csv)")
    print("Sources: " + "; ".join(report))
    print("Next: python load_to_tigerdata.py && python simulator.py")


if __name__ == "__main__":
    main()
