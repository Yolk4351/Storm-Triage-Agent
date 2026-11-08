"""
Does the result hold across storms? The baseline-vs-agent comparison of simulator.py, on 7 real Buffalo storms.

  baseline = largest outage first; agent = the "most urgent first" rules formula (simulator.py names)

For each storm: download REAL hourly weather (Open-Meteo) once and cache it in data/storms/,
then run both policies on many seeds x crew counts. Weather is used raw
(no snowfall scaling) for EVERY storm, including Dec 2022, so storms are comparable; Dec 2022
numbers therefore differ a little from the headline run (which scales snow to the NWS total).

    python evaluate_storms.py                  # 10 seeds x {4, 8, 12} crews, all 7 storms
    python evaluate_storms.py --seeds 20 --save   # also write runs (+ weather) to Tiger Cloud, tagged by storm

Writes data/storms_eval.csv and data/storms_summary.md. Nothing in data/storm_hourly.csv is touched.
"""
import argparse
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

import simulator as S

HERE = Path(__file__).parent
CACHE = HERE / "data" / "storms"
METRICS = ["person_hours_below_50f", "medical_household_hours_at_risk", "household_hours_out",
           "peak_households_out"]          # whatever simulator.score() returns, in this order
REFERENCE = "baseline"

# storm_id, name, first local hour, end (exclusive). NYISO era, all hit the city itself.
STORMS = [
    ("dec-2022-blizzard",   "Christmas Blizzard 2022",     "2022-12-23 00:00", "2022-12-27 00:00"),
    ("jan-2014-blizzard",   "January 2014 blizzard",       "2014-01-06 00:00", "2014-01-09 00:00"),
    ("jan-2024-blizzard",   "Bills playoff blizzard 2024", "2024-01-13 00:00", "2024-01-17 00:00"),
    ("mar-2017-windstorm",  "March 2017 windstorm",        "2017-03-08 00:00", "2017-03-10 00:00"),
    ("jan-2020-windstorm",  "January 2020 windstorm",      "2020-01-11 00:00", "2020-01-13 00:00"),
    ("dec-2001-lake-effect", "Christmas lake-effect 2001", "2001-12-24 00:00", "2001-12-29 00:00"),
    ("jan-2022-lake-effect", "January 2022 lake-effect",   "2022-01-06 00:00", "2022-01-08 00:00"),
]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_hoods():
    df = pd.read_csv(HERE / "data" / "neighborhoods.csv").fillna({"critical_facilities": ""})
    df = df.rename(columns=lambda c: c.removesuffix("_est")).rename(columns={"neighborhood": "name"})
    df["neighborhood_id"] = df["name"].map(slug)
    return df.to_dict("records")


def storm_weather(storm_id, start, end):
    """Hourly real weather for [start, end) local time; downloaded once, then read from data/storms/."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{storm_id}_weather.csv"
    if not path.exists():
        from fetch_storm_data import fetch_weather
        first = pd.Timestamp(start).strftime("%Y-%m-%d")
        last = (pd.Timestamp(end) - pd.Timedelta(hours=1)).strftime("%Y-%m-%d")
        fetch_weather(first, last).to_csv(path, index=False)
        print(f"  downloaded weather -> {path.relative_to(HERE)}")
    w = pd.read_csv(path)
    w["time"] = pd.to_datetime(w["time"], utc=True).dt.tz_convert(S.TZ)
    w = w[(w["time"] >= pd.Timestamp(start, tz=S.TZ)) & (w["time"] < pd.Timestamp(end, tz=S.TZ))]
    return w


def describe(w):
    return {"max_gust_mph": round(w["gust_mph"].max()), "hours_gust_50plus": int((w["gust_mph"] >= 50).sum()),
            "min_temp_f": round(w["temp_f"].min()), "model_snow_in": round(w["snowfall_in"].sum(), 1)}


def save_storm(conn, storm_id, w, results):
    """Weather into weather_hourly (no overlap with other storms) and runs tagged with storm_id."""
    conn.execute("ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS storm_id TEXT")
    # simulator.save() re-creates the scoreboard with CREATE OR REPLACE VIEW, which fails if an older
    # scoreboard with different columns exists; dropping it first is safe (save() rebuilds it).
    conn.execute("DROP VIEW IF EXISTS run_scoreboard")
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO weather_hourly (time, location, temp_f, feels_like_f, wind_mph, gust_mph, wind_dir_deg,
                                           snowfall_in, snow_depth_in, precip_in)
               VALUES (%s, 'buffalo-downtown', %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (location, time) DO NOTHING""",
            [(r.time.to_pydatetime(), r.temp_f, r.feels_like_f, r.wind_mph, r.gust_mph, r.wind_dir_deg,
              r.snowfall_in, r.snow_depth_in, r.precip_in) for r in w.itertuples()])
    for (policy, crews, seed), res in results.items():
        run_id = f"{policy}-{storm_id}-c{crews}-s{seed}"
        S.save(conn, res, run_id, crews, seed, f"evaluate_storms.py: {storm_id}, raw real weather")
        conn.execute("UPDATE sim_runs SET storm_id = %s WHERE run_id = %s", (storm_id, run_id))


def paired(df, storm, crews, strat, m):
    a = df[(df.storm_id == storm) & (df.crews == crews) & (df.strategy == strat)].set_index("seed")[m]
    b = df[(df.storm_id == storm) & (df.crews == crews) & (df.strategy == REFERENCE)].set_index("seed")[m]
    b = b.reindex(a.index).astype(float)
    pct = (a.astype(float) - b) / b.replace(0, np.nan) * 100
    return pct.mean(), int((a < b).sum()), len(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--crews", default="4,8,12")
    ap.add_argument("--policies", default="baseline,agent")
    ap.add_argument("--storms", default="all", help="comma list of storm_ids, or 'all'")
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args()
    crews_list = [int(c) for c in a.crews.split(",")]
    policies = a.policies.split(",")
    storms = [s for s in STORMS if a.storms == "all" or s[0] in a.storms.split(",")]
    hoods = load_hoods()

    conn = None
    if a.save:
        import psycopg
        from dotenv import load_dotenv
        load_dotenv(HERE / ".env")
        conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)

    rows, info = [], []
    for storm_id, name, start, end in storms:
        print(f"{name} ({start} -> {end})", flush=True)
        try:
            w = storm_weather(storm_id, start, end)
        except Exception as e:
            print(f"  ! skipped: weather unavailable ({e})")
            continue
        weather = [{"time": r.time.to_pydatetime(), "temp_f": r.temp_f, "wind_mph": r.wind_mph,
                    "gust_mph": r.gust_mph, "snowfall_in": r.snowfall_in} for r in w.itertuples()]
        d = describe(w)
        info.append({"storm_id": storm_id, "storm": name, "hours": len(weather), **d})
        results = {}
        for crews in crews_list:
            for seed in range(a.seeds):
                for p in policies:
                    res = S.simulate(p, weather, hoods, crews, seed)
                    results[(p, crews, seed)] = res
                    rows.append({"storm_id": storm_id, "strategy": p, "crews": crews, "seed": seed, **res.metrics})
        if conn is not None:
            save_storm(conn, storm_id, w, results)
            print(f"  saved {len(results)} runs to Tiger Cloud")
    if conn is not None:
        conn.close()

    df = pd.DataFrame(rows)
    df.to_csv(HERE / "data" / "storms_eval.csv", index=False)
    info = pd.DataFrame(info)

    # --- summary: one table per crew count, one row per storm
    lines = ["# Results across storms",
             "",
             f"Real hourly weather for each storm (raw, no snowfall scaling); simulated grid, outages, crews and "
             f"indoor temperatures. {a.seeds} seeds per cell. Each cell: mean paired % change of agent (rules formula) "
             f"vs baseline (largest outage first) on "
             f"the same seed (negative = better), and in how many seeds it was lower.",
             "", "## Storms", "", "| " + " | ".join(info.columns) + " |", "|" + "---|" * len(info.columns)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in info.itertuples(index=False)]
    for strat in [p for p in policies if p != REFERENCE]:
        for crews in crews_list:
            lines += ["", f"## {strat} vs {REFERENCE}, {crews} crews", "",
                      "| Storm | Max gust | Min temp | " + " | ".join(METRICS) + " |",
                      "|---|---|---|" + "---|" * len(METRICS)]
            for r in info.itertuples():
                cells = []
                for m in METRICS:
                    pct, better, n = paired(df, r.storm_id, crews, strat, m)
                    cells.append("n/a (0 in both)" if np.isnan(pct) else f"{pct:+.1f}% ({better}/{n})")
                lines.append(f"| {r.storm} | {r.max_gust_mph} mph | {r.min_temp_f}°F | " + " | ".join(cells) + " |")
    md = "\n".join(lines)
    (HERE / "data" / "storms_summary.md").write_text(md)
    print("\n" + md)


if __name__ == "__main__":
    main()
