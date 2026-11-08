"""Hour-by-hour storm replays for the frontend: any storm x {largest_first, rules, llm_agent}.

largest_first and rules are simulated on demand (fast, no API). llm_agent is rebuilt from cached
decisions only; run_llm_storm() makes new decisions with the API and is called only when a user
explicitly asks for it (see server.py).

    python replay.py dec-2022-blizzard rules      # print a summary of one replay (no API)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import simulator as S
import sim_engine as E
from agent_tools import AgentSim, _load_grid_signal
from evaluate_storms import STORMS, load_hoods, storm_weather, describe

HERE = Path(__file__).parent
DEFAULT_SEED, DEFAULT_CREWS = 2, 8
POLICIES = ("largest_first", "rules", "llm_agent")
DB_STORM = "dec-2022-blizzard"          # loaded from Tiger Cloud (snow scaled to NWS), like run_llm.py
COST_PER_STORM_HOUR = 0.015             # USD, measured on a 96-hour Sonnet 5.5 run (~$1.36); an estimate
STORM_INFO = {s[0]: {"id": s[0], "name": s[1], "start": s[2], "end": s[3]} for s in STORMS}


def storm_hours(storm_id):
    i = STORM_INFO[storm_id]
    return int((pd.Timestamp(i["end"]) - pd.Timestamp(i["start"])).total_seconds() // 3600)


def make_sim(storm_id, seed=DEFAULT_SEED, crews=DEFAULT_CREWS):
    if storm_id not in STORM_INFO:
        raise KeyError(f"unknown storm {storm_id!r}")
    if storm_id == DB_STORM:
        return E.load_sim(seed=seed, crews=crews)          # same inputs as run_llm.py and cached LLM runs
    i = STORM_INFO[storm_id]
    w = storm_weather(storm_id, i["start"], i["end"])
    weather = [{"time": r.time.to_pydatetime(), "temp_f": r.temp_f, "wind_mph": r.wind_mph,
                "gust_mph": r.gust_mph, "snowfall_in": r.snowfall_in} for r in w.itertuples()]
    hoods = sorted(load_hoods(), key=lambda h: h["name"])   # database order, so seeds match
    return E.Simulator(weather, hoods, crews, seed)


def llm_folder(storm_id, seed=DEFAULT_SEED, crews=DEFAULT_CREWS):
    if storm_id == DB_STORM:      # the folder run_llm.py writes for the full Dec 2022 window
        return HERE / "cache" / f"llm_2022-12-23T0000_2022-12-27T0000_c{crews}_s{seed}"
    return HERE / "cache" / f"llm_{storm_id}_c{crews}_s{seed}"


def llm_hours_cached(storm_id, seed=DEFAULT_SEED, crews=DEFAULT_CREWS):
    folder = llm_folder(storm_id, seed, crews)
    n = storm_hours(storm_id)
    return sum(1 for t in range(n) if (folder / f"hour_{t}.json").exists())


def llm_available(storm_id, seed=DEFAULT_SEED, crews=DEFAULT_CREWS):
    return llm_hours_cached(storm_id, seed, crews) == storm_hours(storm_id)


def _crew_frame(sim):
    out = []
    for cr in sim.crews:
        target = cr.job.nid if cr.job else cr.staging
        lat, lon = (sim.H[target]["lat"], sim.H[target]["lon"]) if target else cr.loc
        out.append({"id": cr.cid, "status": "repairing" if cr.job else "moving" if cr.staging else "idle",
                    "target": target, "lat": round(lat, 5), "lon": round(lon, 5)})
    return out


def _apply_cached_hour(sim, folder):
    log = json.loads((folder / f"hour_{sim.t}.json").read_text(encoding="utf-8"))
    for act in log["actions"]:
        if not act["tool"].startswith("get_") and act["tool"] != "list_open_jobs":
            sim.apply(act["tool"], act["input"])
    return log


def build_replay(storm_id, policy, seed=DEFAULT_SEED, crews=DEFAULT_CREWS):
    """Run (or re-apply) one policy over a storm and return everything the map needs, per hour."""
    if policy not in POLICIES:
        raise KeyError(f"unknown policy {policy!r}")
    base = make_sim(storm_id, seed, crews)
    folder = None
    if policy == "llm_agent":
        if not llm_available(storm_id, seed, crews):
            raise FileNotFoundError(f"no complete llm_agent run for {storm_id} (seed {seed}, {crews} crews)")
        sim, folder = AgentSim(base), llm_folder(storm_id, seed, crews)
    else:
        sim = base
    H = base.H
    elderly = {nid: h["age_65_plus_share"] or 0 for nid, h in H.items()}
    signal = _load_grid_signal() if storm_id == DB_STORM else None

    crews_by_hour, notes = [], {}
    while not sim.done:
        if folder:
            notes[sim.t] = _apply_cached_hour(sim, folder).get("explanation", "")
        else:
            sim.auto_dispatch(policy)
        crews_by_hour.append(_crew_frame(sim))
        sim.step()

    times = list(dict.fromkeys(s[0] for s in base.states))
    t_of = {tm: i for i, tm in enumerate(times)}
    hours, cum_people = [], 0.0
    for t, tm in enumerate(times):
        rows = [s for s in base.states if s[0] == tm]
        w = base.weather[t]
        hoods = {}
        people = elderly_people = homes_out = 0.0
        for _, nid, risk, out, temp, _htd, below in rows:
            p = below * S.PERSONS_PER_HOUSEHOLD
            people += p
            elderly_people += p * elderly[nid]
            homes_out += out
            hoods[nid] = {"out": out, "below50": below, "temp": temp, "risk": risk,
                          "share_out": round(out / max(H[nid]["households"], 1), 4),
                          "people_at_risk": round(p)}
        cum_people += people
        frame = {"t": t, "time": pd.Timestamp(tm).tz_convert(S.TZ).isoformat(),
                 "weather": {k: round(w[k] or 0, 1) for k in ("temp_f", "wind_mph", "gust_mph", "snowfall_in")},
                 "people_at_risk": round(people), "elderly_at_risk": round(elderly_people),
                 "homes_out": round(homes_out), "person_hours_at_risk": round(cum_people),
                 "hoods": hoods, "crews": crews_by_hour[t]}
        if signal is not None:
            key = pd.Timestamp(tm).tz_convert("UTC")
            if key in signal.index:
                r = signal.loc[key]
                frame["grid_signal_pct"] = round(float(r["missing_demand_mw"]) / float(r["expected_mw"]) * 100, 1)
        if t in notes:
            frame["note"] = notes[t]
        hours.append(frame)

    events = [{"t": t_of.get(e[0], 0), "crew": e[1], "hood": e[2], "action": e[3], "reason": e[4]}
              for e in base.events if e[3] in ("dispatched", "staged", "alert")]
    m = base.metrics()
    return {
        "storm": {**STORM_INFO[storm_id], "hours": len(hours)},
        "policy": policy, "seed": seed, "crews": crews,
        "summary": {
            "person_hours_at_risk": m["person_hours_below_50f"],
            "elderly_person_hours_at_risk": round(sum(h["elderly_at_risk"] for h in hours)),
            "peak_people_at_risk": max(h["people_at_risk"] for h in hours),
            "household_hours_out": m["household_hours_out"],
            "peak_households_out": m["peak_households_out"],
        },
        "hours": hours, "events": events,
        "generated": datetime.now().isoformat(timespec="seconds"),
    }


def storm_list(seed=DEFAULT_SEED, crews=DEFAULT_CREWS):
    out = []
    for sid, info in STORM_INFO.items():
        n = storm_hours(sid)
        item = {**info, "hours": n, "llm_available": llm_available(sid, seed, crews),
                "llm_hours_cached": llm_hours_cached(sid, seed, crews),
                "llm_cost_estimate_usd": round(n * COST_PER_STORM_HOUR, 2),
                "snow_note": "snowfall scaled to NWS totals" if sid == DB_STORM else "raw model weather"}
        path = HERE / "data" / "storms" / f"{sid}_weather.csv"
        if path.exists():
            w = pd.read_csv(path)
            item.update(describe(w))
        out.append(item)
    return out


def run_llm_storm(storm_id, seed=DEFAULT_SEED, crews=DEFAULT_CREWS, on_hour=None):
    """Make llm_agent decisions for a storm with the API (resumes from any cached hours). Costs money."""
    from run_llm import drive_llm
    from BaseSimulation import SYSTEM
    sim = AgentSim(make_sim(storm_id, seed, crews))
    drive_llm(sim, str(llm_folder(storm_id, seed, crews)), SYSTEM, replay=True, on_hour=on_hour, verbose=False)


if __name__ == "__main__":
    sid, pol = (sys.argv[1:3] + ["dec-2022-blizzard", "rules"])[:2] if len(sys.argv) < 3 else sys.argv[1:3]
    r = build_replay(sid, pol)
    print(r["storm"]["name"], pol, r["summary"], f"{len(r['hours'])} hours, {len(r['events'])} events")
