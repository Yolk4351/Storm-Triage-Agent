"""
Robustness check: run the rule-based policies on many random storms (seeds) and crew counts,
so the result isn't one lucky draw. No Claude calls, so it costs nothing.

Same real weather and neighborhoods every time; the seed changes which circuits fail and when.
Within each seed, both policies face the identical failures, so each comparison is paired.

    python eval_seeds.py                         # 20 seeds x 4, 8, 12 crews
    python eval_seeds.py --seeds 50 --crews 6 8  # custom

Outputs:
    results/eval_seeds.csv   one row per (policy, crews, seed)
    results/eval_seeds.md    summary table (mean, spread, how often rules beats largest_first)
"""
import argparse
import os
import statistics as st
from datetime import datetime
from pathlib import Path

import simulator as S
from sim_engine import Simulator

OUT = Path(__file__).parent / "results"
POLICIES = {"largest_first": "baseline", "rules": "rules"}   # display name -> engine policy name
METRICS = ["person_hours_below_50f", "medical_household_hours_at_risk", "critical_facility_hours_dark",
           "household_hours_out", "peak_households_out"]


def load_inputs(start, end):
    import psycopg
    from psycopg.rows import dict_row
    s = datetime.fromisoformat(start).replace(tzinfo=S.TZ)
    e = datetime.fromisoformat(end).replace(tzinfo=S.TZ)
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        weather, hoods, _ = S.load_inputs(conn, s, e, S.REAL_DEC23_SNOW_IN)
    return weather, hoods


def run_grid(weather, hoods, seeds, crew_counts):
    rows = []
    for crews in crew_counts:
        for seed in seeds:
            for name, policy in POLICIES.items():
                sim = Simulator(weather, hoods, crews, seed)
                m = sim.run_policy(policy)
                rows.append({"policy": name, "crews": crews, "seed": seed, **{k: m[k] for k in METRICS}})
        print(f"  {crews} crews done", flush=True)
    return rows


def summarize(rows, crew_counts):
    lines = ["| Crews | Metric | largest_first (mean ± sd) | rules (mean ± sd) | Change | Rules better in |",
             "|---|---|---|---|---|---|"]
    for crews in crew_counts:
        by = {p: {r["seed"]: r for r in rows if r["policy"] == p and r["crews"] == crews} for p in POLICIES}
        seeds = sorted(by["largest_first"])
        for k in METRICS:
            b = [by["largest_first"][s][k] for s in seeds]
            r = [by["rules"][s][k] for s in seeds]
            mb, mr = st.mean(b), st.mean(r)
            sdb, sdr = (st.stdev(b), st.stdev(r)) if len(seeds) > 1 else (0, 0)
            change = f"{(mr - mb) / mb * 100:+.0f}%" if mb else "-"
            wins = sum(1 for x, y in zip(b, r) if y < x)
            ties = sum(1 for x, y in zip(b, r) if y == x)
            win_txt = f"{wins}/{len(seeds)}" + (f" ({ties} ties)" if ties else "")
            lines.append(f"| {crews} | {k} | {mb:,.0f} ± {sdb:,.0f} | {mr:,.0f} ± {sdr:,.0f} | {change} | {win_txt} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--crews", type=int, nargs="+", default=[4, 8, 12])
    ap.add_argument("--start", default="2022-12-23 00:00")
    ap.add_argument("--end", default="2022-12-27 00:00")
    a = ap.parse_args()

    weather, hoods = load_inputs(a.start, a.end)
    print(f"Running {len(POLICIES)} policies x {a.seeds} seeds x crews {a.crews} "
          f"on {len(weather)} storm hours, {len(hoods)} neighborhoods...")
    rows = run_grid(weather, hoods, range(1, a.seeds + 1), a.crews)

    OUT.mkdir(exist_ok=True)
    with open(OUT / "eval_seeds.csv", "w", encoding="utf-8") as f:
        f.write(",".join(rows[0]) + "\n")
        for r in rows:
            f.write(",".join(str(v) for v in r.values()) + "\n")
    table = summarize(rows, a.crews)
    note = (f"Window {a.start} to {a.end}; {a.seeds} seeds per crew count. Real weather and neighborhood data; "
            "outages, crews and indoor temperatures are simulated. Lower is better for every metric. "
            "'Rules better in' counts seeds where rules scored strictly lower than largest_first on the same storm.")
    (OUT / "eval_seeds.md").write_text(f"# Robustness across seeds\n\n{note}\n\n{table}\n", encoding="utf-8")
    print("\n" + table + f"\n\nSaved {OUT / 'eval_seeds.csv'} and {OUT / 'eval_seeds.md'}")


if __name__ == "__main__":
    main()
