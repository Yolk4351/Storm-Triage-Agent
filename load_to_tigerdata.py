"""
Load the Storm Triage CSVs into Tiger Cloud (TigerData).

  1. Creates the tables (schema.sql) and TimescaleDB features (timescale.sql:
     hypertables + a 3-hour storm-summary continuous aggregate)
  2. Upserts data/storm_hourly.csv   -> weather_hourly, grid_load_hourly
  3. Upserts data/neighborhoods.csv  -> neighborhoods
  Re-running is safe: rows are updated, never duplicated.

Setup:
  pip install pandas "psycopg[binary]" python-dotenv
  Put your Tiger Cloud connection string in a .env file next to this script:
     DATABASE_URL=postgres://tsdbadmin:PASSWORD@HOST:PORT/tsdb?sslmode=require

Usage:
  python fetch_storm_data.py      # creates the CSVs
  python load_to_tigerdata.py     # loads them
"""
import os
import re
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

HERE = Path(__file__).parent
DATA = HERE / "data"
load_dotenv(HERE / ".env")


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL in .env (Tiger Cloud console -> your service -> Connect).")
    return psycopg.connect(url, autocommit=True)


def run_sql_file(conn, path: Path):
    """Run statements one at a time (continuous aggregates can't run inside
    the implicit transaction a multi-statement query creates)."""
    text = re.sub(r"--[^\n]*", "", path.read_text())
    for stmt in (s.strip() for s in text.split(";")):
        if stmt:
            conn.execute(stmt)


def apply_schema(conn) -> bool:
    run_sql_file(conn, HERE / "schema.sql")
    available = conn.execute(
        "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'"
    ).fetchone()
    if not available:
        print("! TimescaleDB not available on this server: using plain Postgres tables.")
        return False
    run_sql_file(conn, HERE / "timescale.sql")
    print("Schema ready (hypertables + storm_summary_3h continuous aggregate).")
    return True


def _clean(v):
    """pandas NaN/NaT -> None so Postgres gets NULL."""
    return None if pd.isna(v) else v


def upsert(conn, table, cols, rows, conflict_cols):
    rows = list(rows)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in conflict_cols)
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT ({', '.join(conflict_cols)}) DO UPDATE SET {updates}"
    )
    with conn.cursor() as cur:
        cur.executemany(sql, [[_clean(v) for v in r] for r in rows])
    print(f"  {table}: {len(rows)} rows")


def load_storm(conn):
    df = pd.read_csv(DATA / "storm_hourly.csv")
    df["time"] = pd.to_datetime(df["time"], utc=True)

    weather_cols = ["time", "temp_f", "feels_like_f", "wind_mph", "gust_mph", "wind_dir_deg",
                    "snowfall_in", "snow_depth_in", "precip_in"]
    upsert(conn, "weather_hourly", weather_cols + ["location"],
           [list(r) + ["buffalo-downtown"] for r in df[weather_cols].itertuples(index=False)],
           ["location", "time"])

    load_rows = []
    for col, zone in [("west_load_mw", "WEST"), ("nyiso_total_load_mw", "NYISO_TOTAL")]:
        if col in df:
            for t, v in df[["time", col]].dropna().itertuples(index=False):
                load_rows.append([t, zone, v])
    if load_rows:
        upsert(conn, "grid_load_hourly", ["time", "zone", "load_mw"], load_rows, ["zone", "time"])
    else:
        print("  grid_load_hourly: no NYISO data in CSV, skipped")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_neighborhoods(conn):
    df = pd.read_csv(DATA / "neighborhoods.csv").fillna({"critical_facilities": ""})
    df["neighborhood_id"] = df["neighborhood"].map(slug)
    # Columns ending in _est are placeholders until your team replaces them
    estimated = any(c.endswith("_est") for c in df.columns)
    df = df.rename(columns=lambda c: c.removesuffix("_est")).rename(columns={"neighborhood": "name"})
    df["data_quality"] = "estimate" if estimated else "real"

    cols = ["neighborhood_id", "name", "lat", "lon", "population", "households",
            "median_year_built", "street_trees", "overhead_line_share",
            "medical_device_households", "age_65_plus_share", "critical_facilities",
            "data_quality"]
    upsert(conn, "neighborhoods", cols, df[cols].itertuples(index=False), ["neighborhood_id"])


def refresh_and_check(conn, timescale: bool):
    if timescale:
        conn.execute("CALL refresh_continuous_aggregate('storm_summary_3h', NULL, NULL)")
    worst = conn.execute(
        """SELECT time AT TIME ZONE 'America/New_York', gust_mph, temp_f
           FROM weather_hourly ORDER BY gust_mph DESC NULLS LAST LIMIT 1"""
    ).fetchone()
    counts = conn.execute(
        """SELECT (SELECT count(*) FROM weather_hourly),
                  (SELECT count(*) FROM grid_load_hourly),
                  (SELECT count(*) FROM neighborhoods)"""
    ).fetchone()
    print(f"\nIn database: {counts[0]} weather hours, {counts[1]} load rows, {counts[2]} neighborhoods")
    if worst:
        print(f"Peak gust {worst[1]:.0f} mph at {worst[0]:%a %b %d %I %p} ({worst[2]:.0f}°F)")


def main():
    with connect() as conn:
        ts = apply_schema(conn)
        print("Loading data...")
        load_storm(conn)
        load_neighborhoods(conn)
        refresh_and_check(conn, ts)


if __name__ == "__main__":
    main()
