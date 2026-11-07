"""
Storm Triage Agent - data fetcher
Pulls REAL data for the December 2022 Buffalo blizzard into CSVs your team can build on.

  1. Hourly weather for Buffalo      -> Open-Meteo Historical Weather API (free, no key)
  2. Hourly electricity load          -> NYISO public archive (real-time actual load, "pal")
                                         WEST zone (Zone A, includes Buffalo) + NY total
  3. Neighborhood starter table       -> 13 Buffalo neighborhoods with APPROXIMATE centers
                                         and placeholder attributes to replace with real data

Output (in ./data/):
  storm_hourly.csv     one row per hour: weather + grid load
  neighborhoods.csv    one row per neighborhood (fill in the ESTIMATE columns)

Usage:
  pip install pandas requests
  python fetch_storm_data.py
  python fetch_storm_data.py --start 2022-12-21 --end 2022-12-30
"""
import argparse
import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

TZ = "America/New_York"
BUFFALO_LAT, BUFFALO_LON = 42.8864, -78.8784  # downtown Buffalo
OUT_DIR = Path(__file__).parent / "data"

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
NYISO_MONTHLY_ZIP = "http://mis.nyiso.com/public/csv/pal/{yyyymm}01pal_csv.zip"
NYISO_DAILY_CSV = "http://mis.nyiso.com/public/csv/pal/{yyyymmdd}pal.csv"


# --------------------------------------------------------------------------
# 1. Weather (Open-Meteo, ERA5 reanalysis = real historical observations-based data)
# --------------------------------------------------------------------------
def fetch_weather(start: str, end: str) -> pd.DataFrame:
    params = {
        "latitude": BUFFALO_LAT,
        "longitude": BUFFALO_LON,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join([
            "temperature_2m", "apparent_temperature", "wind_speed_10m",
            "wind_gusts_10m", "wind_direction_10m", "snowfall", "snow_depth",
            "precipitation",
        ]),
        "timezone": TZ,
        # Request metric and convert ourselves so units are never ambiguous.
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=60)
    r.raise_for_status()
    h = r.json()["hourly"]

    df = pd.DataFrame({
        "time": _localize(pd.to_datetime(h["time"])),
        "temp_f": _c_to_f(h["temperature_2m"]),
        "feels_like_f": _c_to_f(h["apparent_temperature"]),
        "wind_mph": pd.Series(h["wind_speed_10m"], dtype=float) * 0.621371,
        "gust_mph": pd.Series(h["wind_gusts_10m"], dtype=float) * 0.621371,
        "wind_dir_deg": pd.Series(h["wind_direction_10m"], dtype=float),
        "snowfall_in": pd.Series(h["snowfall"], dtype=float) / 2.54,      # cm -> in
        "snow_depth_in": pd.Series(h["snow_depth"], dtype=float) * 39.37,  # m  -> in
        "precip_in": pd.Series(h["precipitation"], dtype=float) / 25.4,    # mm -> in
    })
    num = df.columns.drop("time")
    df[num] = df[num].round(2)
    return df


def _c_to_f(values):
    return pd.Series(values, dtype=float) * 9 / 5 + 32


# --------------------------------------------------------------------------
# 2. Grid load (NYISO real-time actual load, 5-minute, by zone)
# --------------------------------------------------------------------------
def fetch_nyiso_load(start: str, end: str) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    frames = []

    for month in sorted({d.strftime("%Y%m") for d in days}):
        try:
            frames.append(_nyiso_from_monthly_zip(month))
        except Exception as e:  # fall back to one file per day
            print(f"  monthly zip for {month} failed ({e}); trying daily files")
            for d in days[days.strftime("%Y%m") == month]:
                url = NYISO_DAILY_CSV.format(yyyymmdd=d.strftime("%Y%m%d"))
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                frames.append(pd.read_csv(io.StringIO(r.text)))

    raw = pd.concat(frames, ignore_index=True)
    return parse_nyiso(raw, start, end)


def _nyiso_from_monthly_zip(yyyymm: str) -> pd.DataFrame:
    r = requests.get(NYISO_MONTHLY_ZIP.format(yyyymm=yyyymm), timeout=120)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return pd.concat(
            [pd.read_csv(z.open(n)) for n in sorted(z.namelist()) if n.endswith(".csv")],
            ignore_index=True,
        )


def parse_nyiso(raw: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """5-minute zonal rows -> hourly WEST and NY-total load in MW."""
    raw.columns = [c.strip() for c in raw.columns]
    raw["time"] = pd.to_datetime(raw["Time Stamp"], format="%m/%d/%Y %H:%M:%S")
    raw["Load"] = pd.to_numeric(raw["Load"], errors="coerce")

    pivot = raw.pivot_table(index="time", columns="Name", values="Load", aggfunc="mean")
    hourly = pivot.resample("h").mean()

    out = pd.DataFrame(index=hourly.index)
    out["west_load_mw"] = hourly["WEST"]           # Zone A: Western NY incl. Buffalo
    out["nyiso_total_load_mw"] = hourly.sum(axis=1, min_count=1)
    out = out.loc[start: f"{end} 23:59"].reset_index()
    out["time"] = _localize(out["time"])
    num = out.columns.drop("time")
    out[num] = out[num].round(1)
    return out


# --------------------------------------------------------------------------
# 3. Neighborhood starter table
# --------------------------------------------------------------------------
# Centers are APPROXIMATE (good enough for map markers). Every *_est column is a
# placeholder: replace with Census / Open Data Buffalo values, or keep and disclose
# as simulated. Fruit Belt and East Side areas are included because they were among
# the last restored in 2022 (WKBW reporting).
NEIGHBORHOODS = [
    # name,               lat,     lon
    ("South Buffalo",      42.848, -78.810),
    ("Kaisertown",         42.873, -78.795),
    ("Lovejoy",            42.887, -78.797),
    ("Broadway-Fillmore",  42.894, -78.832),
    ("Fruit Belt",         42.899, -78.860),
    ("Masten Park",        42.915, -78.845),
    ("University Heights", 42.950, -78.820),
    ("North Buffalo",      42.950, -78.855),
    ("Riverside",          42.955, -78.905),
    ("Black Rock",         42.935, -78.900),
    ("Elmwood Village",    42.920, -78.877),
    ("West Side",          42.905, -78.895),
    ("Allentown",          42.903, -78.873),
]


def build_neighborhoods() -> pd.DataFrame:
    df = pd.DataFrame(NEIGHBORHOODS, columns=["neighborhood", "lat", "lon"])
    placeholders = {
        "population_est": 10000,           # Census ACS by tract
        "households_est": 4500,            # Census ACS by tract
        "median_year_built_est": 1925,     # Census ACS B25035 -> drives home cooling rate (tau)
        "street_trees_est": 3000,          # Open Data Buffalo "Tree Inventory"
        "overhead_line_share_est": 0.85,   # SIMULATED: share of lines above ground
        "medical_device_households_est": 40,  # SIMULATED
        "age_65_plus_share_est": 0.14,     # Census ACS
        "critical_facilities": "",         # e.g. "hospital;warming center" (Open Data Buffalo / manual)
    }
    for col, val in placeholders.items():
        df[col] = val
    return df


# --------------------------------------------------------------------------
def _localize(times):
    s = pd.Series(pd.to_datetime(times))
    return s.dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-12-22")
    ap.add_argument("--end", default="2022-12-28")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    print(f"Weather {args.start} -> {args.end} (Open-Meteo)...")
    weather = fetch_weather(args.start, args.end)

    print("Grid load (NYISO)...")
    try:
        load = fetch_nyiso_load(args.start, args.end)
    except Exception as e:
        print(f"  NYISO download failed: {e}\n  Continuing with weather only.")
        load = pd.DataFrame(columns=["time", "west_load_mw", "nyiso_total_load_mw"])

    hourly = weather.merge(load, on="time", how="left")
    hourly.to_csv(OUT_DIR / "storm_hourly.csv", index=False)

    hoods = build_neighborhoods()
    hoods_path = OUT_DIR / "neighborhoods.csv"
    if hoods_path.exists():
        print("neighborhoods.csv already exists - not overwriting your edits.")
    else:
        hoods.to_csv(hoods_path, index=False)

    # Quick sanity summary
    peak = hourly.loc[hourly["gust_mph"].idxmax()]
    print(f"\nSaved {len(hourly)} hours -> {OUT_DIR / 'storm_hourly.csv'}")
    print(f"  Peak gust:   {peak['gust_mph']:.0f} mph at {peak['time']}")
    print(f"  Coldest:     {hourly['temp_f'].min():.0f}°F "
          f"(feels like {hourly['feels_like_f'].min():.0f}°F)")
    print(f"  Total snow:  {hourly['snowfall_in'].sum():.1f} in (model grid cell; "
          "lake-effect bands vary a lot block to block)")
    if hourly["west_load_mw"].notna().any():
        print(f"  WEST load:   {hourly['west_load_mw'].min():.0f}-"
              f"{hourly['west_load_mw'].max():.0f} MW")
    print(f"Neighborhoods -> {hoods_path} (replace the *_est columns)")


if __name__ == "__main__":
    main()
