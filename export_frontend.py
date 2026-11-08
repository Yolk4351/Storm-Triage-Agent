"""Export data for the React frontend (frontend/public/data/). No API calls, no database.

    python export_frontend.py          # writes frontend/public/data/neighborhoods.json

Step 1 (now): the 13 neighborhoods from data/neighborhoods.csv (the official real-data file).
Step 2 (next): per-hour storm replays for largest_first, rules and llm_agent from finished runs.
"""
import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
OUT = HERE / "frontend" / "public" / "data"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def export_neighborhoods():
    df = pd.read_csv(HERE / "data" / "neighborhoods.csv").fillna({"critical_facilities": ""})
    df = df.rename(columns=lambda c: c.removesuffix("_est"))
    hoods = []
    for r in df.itertuples():
        hoods.append({
            "id": slug(r.neighborhood),
            "name": r.neighborhood,
            "lat": float(r.lat),
            "lon": float(r.lon),
            "population": int(r.population),
            "households": int(r.households),
            "median_year_built": int(r.median_year_built),
            "age_65_plus_share": float(r.age_65_plus_share),
            "medical_device_households": int(r.medical_device_households),
            "street_trees": int(r.street_trees),
            "critical_facilities": [s.strip() for s in str(r.critical_facilities).split(";") if s.strip()],
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "neighborhoods.json").write_text(json.dumps(hoods, indent=2), encoding="utf-8")
    print(f"{len(hoods)} neighborhoods -> {OUT / 'neighborhoods.json'}")


if __name__ == "__main__":
    export_neighborhoods()
