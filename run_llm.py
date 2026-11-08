"""Three-way comparison on the real storm: largest_first vs rules vs llm_agent, same seed, crews and window.

    python run_llm.py --start "2022-12-23 00:00" --end "2022-12-23 08:00"   # short trial first
    python run_llm.py                                                        # full Dec 23-27 (~96 agent hours)
    python run_llm.py --replay                                               # re-run from cached decisions, no API calls
    python run_llm.py --save                                                 # also write all three runs to Tiger Cloud
    python run_llm.py --seed 2 --ablation no_vulnerability                   # LLM without 65+/medical data

Agent decisions are cached per hour in cache/llm_<window>_c<crews>_s<seed>/. Delete that folder after
changing the prompt or the engine, or replay will reuse stale decisions.
"""
import argparse
import json
import os

import simulator as S
from sim_engine import load_sim, RULE_POLICIES
from agent_tools import AgentSim

FULL_WINDOW = ("2022-12-23 00:00", "2022-12-27 00:00")   # load_sim's defaults


def tag(a):
    return f"{a.start}_{a.end}".replace(" ", "T").replace(":", "")


def run_llm_agent(a):
    from BaseSimulation import run_tick, SYSTEM, SYSTEM_NO_VULNERABILITY   # imported here so --replay works offline
    hide = a.ablation == "no_vulnerability"
    system = SYSTEM_NO_VULNERABILITY if hide else SYSTEM
    sim = AgentSim(load_sim(start=a.start, end=a.end, crews=a.crews, seed=a.seed), hide_vulnerability=hide)
    suffix = "_novuln" if hide else ""
    folder = os.path.join("cache", f"llm_{tag(a)}_c{a.crews}_s{a.seed}{suffix}")
    os.makedirs(folder, exist_ok=True)
    while not sim.done:
        path = os.path.join(folder, f"hour_{sim.t}.json")
        if a.replay and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                log = json.load(f)
            for act in log["actions"]:            # re-apply saved decisions, no API call
                if not act["tool"].startswith("get_"):
                    sim.apply(act["tool"], act["input"])
        else:
            if not any(sim._idle(cr) for cr in sim.crews):
                # Every crew is busy and busy crews can't be redirected: nothing to decide, so no API call.
                log = {"tick": sim.t, "actions": [], "explanation": "Skipped: no idle crew this hour.",
                       "skipped": True}
            else:
                if a.replay:
                    print(f"  hour {sim.t}: no cached decision, calling the API")
                jobs = sim.apply("list_open_jobs", {})    # sent in the first message: saves a round trip
                log = run_tick(sim, sim.t, system=system, first_observation=("list_open_jobs", jobs))
                left = min(len(jobs["idle_crews"]), jobs["open_outages_total"]) - sum(
                    1 for x in log["actions"] if x["tool"] == "dispatch_crew" and x["result"].get("ok"))
                if left > 0:
                    print(f"  ! hour {sim.t}: {left} idle crew(s) left unassigned while outages wait")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2, default=str)
        print(f"  hour {sim.t}: {sum(1 for x in log['actions'] if x['tool'] == 'dispatch_crew')} dispatches")
        sim.step()
    return sim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=FULL_WINDOW[0])
    ap.add_argument("--end", default=FULL_WINDOW[1])
    ap.add_argument("--crews", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--save", action="store_true", help="write all three runs to Tiger Cloud")
    ap.add_argument("--ablation", choices=["none", "no_vulnerability"], default="none",
                    help="no_vulnerability: hide 65+ share and medical-device households from the LLM")
    a = ap.parse_args()

    runs = {}
    for policy in RULE_POLICIES:                   # largest_first, rules
        sim = load_sim(start=a.start, end=a.end, crews=a.crews, seed=a.seed)
        sim.run_policy(policy)
        runs[policy] = sim
    label = "llm_agent" if a.ablation == "none" else f"llm_{a.ablation}"
    print(f"{label}:")
    runs[label] = run_llm_agent(a)

    names = list(runs)
    metrics = {n: s.metrics() for n, s in runs.items()}
    print(f"\nWindow {a.start} -> {a.end}, crews={a.crews}, seed={a.seed}")
    print(f"{'Metric':34}" + "".join(f"{n:>22}" for n in names))
    for k in metrics[names[0]]:
        print(f"{k:34}" + "".join(f"{metrics[n][k]:>22,}" for n in names))

    if a.save:
        import psycopg
        suffix = "" if (a.start, a.end) == FULL_WINDOW else f"-{tag(a)}"   # don't clobber full runs with trials
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
            for n, sim in runs.items():
                run_id = f"{n}-c{a.crews}-s{a.seed}{suffix}"
                S.save(conn, sim.result(n), run_id, a.crews, a.seed,
                       f"Real weather {a.start} to {a.end}; simulated grid, crews, indoor temps; "
                       f"perfect weather forecast for llm_agent")
                print(f"Saved {run_id}")


if __name__ == "__main__":
    main()
