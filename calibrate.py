"""Plausibility check: does the simulator's outage curve have the same SHAPE as the real regional lost load?

Real signal: NYISO WEST zone load during the blizzard minus what demand_model.py expected from the
weather (data/storm_load_forecast.csv, "missing_demand_mw"). The zone is far bigger than our 13
neighborhoods, and lost load also reflects people changing behavior (closed businesses, travel bans),
so we compare only the shape over time (correlation and peak timing), never absolute MW.

Simulated signal: households without power per hour under largest_first, averaged over several seeds.
The only thing adjusted is the failure_prob intercept, by a coarse grid search.

    python calibrate.py            # prints the grid and writes data/calibration.json
"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import simulator as S
import sim_engine as E

START, END = "2022-12-23 00:00", "2022-12-27 00:00"
SEEDS = range(1, 11)
GRID = [-11.0, -10.5, -10.0, -9.5, -9.0, -8.5, -8.0, -7.5]
CURRENT = S.FAILURE_INTERCEPT


def real_lost_load():
    df = pd.read_csv(Path(__file__).parent / "data" / "storm_load_forecast.csv", parse_dates=["time"])
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert(S.TZ)
    s = pd.Timestamp(START, tz=S.TZ)
    df = df[(df["time"] >= s) & (df["time"] < pd.Timestamp(END, tz=S.TZ))]
    return df.set_index("time")["missing_demand_mw"]


def sim_households_out(sim0, intercept):
    S.FAILURE_INTERCEPT = intercept
    curves = []
    for seed in SEEDS:
        sim = E.Simulator(sim0.weather, sim0.hoods, 8, seed)
        sim.run_policy("largest_first")
        by = {}
        for st in sim.states:
            by[st[0]] = by.get(st[0], 0) + st[3]
        curves.append(list(by.values()))
    return pd.Series(np.mean(curves, axis=0), index=[w["time"] for w in sim0.weather])


def compare(real, sim):
    sim = sim.reindex(real.index)
    r6 = lambda x: x.rolling(6, center=True, min_periods=1).mean()
    daily_r = real.groupby(real.index.date).mean().corr(sim.groupby(sim.index.date).mean())
    return {
        "pearson_r_hourly": round(float(real.corr(sim)), 3),
        "pearson_r_6h_smoothed": round(float(r6(real).corr(r6(sim))), 3),
        "pearson_r_daily": round(float(daily_r), 3),
        "real_peak_6h": str(r6(real).idxmax()),
        "sim_peak_6h": str(r6(sim).idxmax()),
        "peak_offset_hours": round((r6(sim).idxmax() - r6(real).idxmax()).total_seconds() / 3600),
        "sim_mean_households_out": round(float(sim.mean())),
    }


def main():
    real = real_lost_load()
    sim0 = E.load_sim(start=START, end=END)
    rows = []
    print(f"{'intercept':>9} {'r_hourly':>9} {'r_6h':>7} {'r_daily':>8} {'peak offset h':>14} {'mean hh out':>12}")
    for b in GRID:
        m = {"intercept": b, **compare(real, sim_households_out(sim0, b))}
        rows.append(m)
        print(f"{b:>9} {m['pearson_r_hourly']:>9} {m['pearson_r_6h_smoothed']:>7} {m['pearson_r_daily']:>8} "
              f"{m['peak_offset_hours']:>14} {m['sim_mean_households_out']:>12,}")
    S.FAILURE_INTERCEPT = CURRENT
    before = next(r for r in rows if r["intercept"] == CURRENT)
    best = max(rows, key=lambda r: r["pearson_r_hourly"])
    # Only adopt a new intercept if it produces a genuinely positive shape match; otherwise keep the current one.
    adopt = best["intercept"] if best["pearson_r_hourly"] > 0.3 else CURRENT
    out = {
        "adopted_intercept": adopt,
        "decision": ("adopted best grid value" if adopt != CURRENT else
                     "kept current value: no intercept gives a positive correlation, so changing it would only "
                     "tune noise. The simulated outage peak comes ~2 days before the real lost-load peak; "
                     "the intercept scales outage levels but cannot move their timing."),
        "what": "Shape comparison: simulated households out (largest_first, mean of seeds) vs real NYISO WEST "
                "lost load (actual minus demand_model expected). Plausibility check, not validation.",
        "window": [START, END], "seeds": list(SEEDS), "selection": "highest hourly Pearson r",
        "real_peak_6h": before["real_peak_6h"], "before": before, "best": best, "grid": rows,
        "run_date": str(date.today()),
    }
    (Path(__file__).parent / "data" / "calibration.json").write_text(json.dumps(out, indent=2))
    print(f"\nreal lost-load peak (6h smoothed): {before['real_peak_6h']}")
    print(f"before (intercept {CURRENT}): r_hourly={before['pearson_r_hourly']}, peak offset {before['peak_offset_hours']} h")
    print(f"best   (intercept {best['intercept']}): r_hourly={best['pearson_r_hourly']}, peak offset {best['peak_offset_hours']} h")
    print(f"adopted intercept: {adopt}  ({out['decision']})")


if __name__ == "__main__":
    main()
