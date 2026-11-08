"""Multi-seed, multi-crew evaluation: mean and spread of every metric, for every policy.

Rule-based policies (largest_first, rules) run live on every seed (no API cost).
llm_agent results come only from cached decisions (cache/llm_..._c<crews>_s<seed>[_persistence]/),
replayed without API calls; a run is included only if every hour is cached.

    python evaluate.py                         # seeds 1-20, crews 4 8 12
    python evaluate.py --seeds 1-30 --crews 8

Writes data/eval_results.json and data/eval_results.md.
"""
import argparse
import json
import os
import statistics as st
from pathlib import Path

import sim_engine as E
from agent_tools import AgentSim

START, END = "2022-12-23 00:00", "2022-12-27 00:00"
TAG = "2022-12-23T0000_2022-12-27T0000"
METRICS = ["person_hours_below_50f", "medical_household_hours_at_risk", "critical_facility_hours_dark",
           "household_hours_out", "peak_households_out", "critical_area_hours_any_outage"]
HERE = Path(__file__).parent


def seeds_arg(s):
    a, _, b = s.partition("-")
    return list(range(int(a), int(b) + 1)) if b else [int(x) for x in s.split(",")]


def llm_replay(base, crews, seed, forecast):
    fc = "" if forecast == "perfect" else f"_{forecast}"
    folder = HERE / "cache" / f"llm_{TAG}_c{crews}_s{seed}{fc}"
    n = len(base.weather)
    if not all((folder / f"hour_{t}.json").exists() for t in range(n)):
        return None
    sim = AgentSim(E.Simulator(base.weather, base.hoods, crews, seed), forecast=forecast)
    while not sim.done:
        for act in json.loads((folder / f"hour_{sim.t}.json").read_text(encoding="utf-8"))["actions"]:
            if not act["tool"].startswith("get_") and act["tool"] != "list_open_jobs":
                sim.apply(act["tool"], act["input"])
        sim.step()
    return sim.metrics()


def summarize(vals):
    if not vals:
        return None
    return {"n": len(vals), "mean": st.mean(vals), "sd": st.stdev(vals) if len(vals) > 1 else 0.0,
            "min": min(vals), "max": max(vals)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-20")
    ap.add_argument("--crews", default="4,8,12")
    a = ap.parse_args()
    seeds, crew_list = seeds_arg(a.seeds), [int(c) for c in a.crews.split(",")]

    base = E.load_sim(start=START, end=END)
    raw, summary = {}, {}
    for crews in crew_list:
        for policy in ("largest_first", "rules"):
            runs = {}
            for seed in seeds:
                runs[seed] = E.Simulator(base.weather, base.hoods, crews, seed).run_policy(policy)
            raw[f"{policy}|c{crews}"] = runs
        for forecast in ("perfect", "persistence"):
            label = "llm_agent" if forecast == "perfect" else "llm_agent_persistence"
            runs = {}
            for seed in sorted(set(seeds) | {42}):
                m = llm_replay(base, crews, seed, forecast)
                if m:
                    runs[seed] = m
            if runs:
                raw[f"{label}|c{crews}"] = runs
        print(f"crews={crews} done")

    # Paired comparison: rules and largest_first on exactly the seeds the LLM has, so differences aren't seed luck
    for key, runs in list(raw.items()):
        if key.startswith("llm_agent"):
            crews = key.split("|c")[1]
            for policy in ("largest_first", "rules"):
                paired = {s: (raw.get(f"{policy}|c{crews}", {}).get(s) or
                              E.Simulator(base.weather, base.hoods, int(crews), s).run_policy(policy)) for s in runs}
                raw[f"{policy}@{key.split('|')[0]}-seeds|c{crews}"] = paired

    for key, runs in raw.items():
        summary[key] = {m: summarize([r[m] for r in runs.values()]) for m in METRICS}
        summary[key]["seeds"] = sorted(runs)

    (HERE / "data" / "eval_results.json").write_text(json.dumps({"summary": summary, "raw": raw}, indent=2, default=str))

    lines = [f"# Evaluation: {START} to {END}", "",
             "Mean ± standard deviation across seeds (n = number of seeds). Lower is better for every metric.", ""]
    for crews in crew_list:
        keys = [k for k in summary if k.endswith(f"|c{crews}")]
        lines += [f"## {crews} crews", "", "| policy | n | " + " | ".join(METRICS) + " |",
                  "|---|---|" + "---|" * len(METRICS)]
        for k in keys:
            s = summary[k]
            cells = [f"{s[m]['mean']:,.0f} ± {s[m]['sd']:,.0f}" for m in METRICS]
            lines.append(f"| {k.split('|')[0]} | {s[METRICS[0]]['n']} | " + " | ".join(cells) + " |")
        lines.append("")
    (HERE / "data" / "eval_results.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
