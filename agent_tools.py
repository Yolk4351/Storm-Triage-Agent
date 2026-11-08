"""Extra tools for the LLM dispatcher, layered on sim_engine.Simulator without changing it.

The rule-based policies choose among individual outages (circuits) and know each one's indoor
temperature, time until it drops below 50°F, and the job time from each crew. The base LLM tools only
showed neighborhood totals and let the engine pick the outage. These tools give the LLM the same facts
and let it choose a specific outage, so the comparison with `rules` is fair. Physics and scoring are
untouched: a targeted dispatch uses the engine's own travel and repair-time functions.
"""
import copy
from pathlib import Path

import pandas as pd

import simulator as S
from sim_engine import TOOL_SCHEMAS

MAX_JOBS_LISTED = 30
LOAD_CSV = Path(__file__).parent / "data" / "storm_load_forecast.csv"
VULNERABILITY_FIELDS = ("age_65_plus_share", "medical_device_households")
_grid_signal = None


def _load_grid_signal():
    """Real NYISO WEST zone load vs demand_model.py's expected load, keyed by UTC hour (loaded once)."""
    global _grid_signal
    if _grid_signal is None:
        df = pd.read_csv(LOAD_CSV)
        df.index = pd.to_datetime(df["time"], utc=True)
        _grid_signal = df
    return _grid_signal


class AgentSim:
    """Wraps a Simulator; adds list_open_jobs, get_grid_signal and dispatch_crew(outage_id=...).
    Everything else passes through.

    hide_vulnerability=True is the ablation: the agent no longer sees age_65_plus_share or
    medical_device_households. Scoring is unchanged; only what the agent sees changes."""

    def __init__(self, sim, hide_vulnerability=False):
        self.sim = sim
        self.hide_vulnerability = hide_vulnerability

    def __getattr__(self, name):          # done, t, w, step(), metrics(), result(), ...
        return getattr(self.sim, name)

    def apply(self, name, args):
        if name == "list_open_jobs":
            return self.open_jobs()
        if name == "get_grid_signal":
            return self.grid_signal()
        if name == "dispatch_crew" and args.get("outage_id"):
            return self.dispatch_outage(args.get("crew_id", ""), args["outage_id"], args.get("reason", ""))
        out = self.sim.apply(name, args)
        if name == "get_grid_state" and self.hide_vulnerability and "neighborhoods" in out:
            for h in out["neighborhoods"]:
                for f in VULNERABILITY_FIELDS:
                    h.pop(f, None)
        return out

    def grid_signal(self):
        """Sense: the real regional load gap for the current storm hour."""
        df = _load_grid_signal()
        now = pd.Timestamp(self.sim.w["time"]).tz_convert("UTC")
        if now not in df.index:
            return {"error": f"No NYISO data for {now:%Y-%m-%d %H:00} UTC (covers {df.index.min():%b %d} to "
                             f"{df.index.max():%b %d})."}
        r = df.loc[now]
        return {
            "hour": self.sim.t,
            "zone": "NYISO WEST (Zone A), the whole region around Buffalo",
            "actual_load_mw": round(float(r["actual_mw"]), 1),
            "expected_load_mw": round(float(r["expected_mw"]), 1),
            "missing_demand_mw": round(float(r["missing_demand_mw"]), 1),
            "missing_demand_pct": round(float(r["missing_demand_mw"]) / float(r["expected_mw"]) * 100, 1),
            "note": "REAL regional signal: actual load minus what the weather-based demand model expected. "
                    "A positive gap suggests lost load (outages, closed businesses, travel bans). It covers the "
                    "whole zone, not our 13 neighborhoods, and is not an outage count for any neighborhood.",
        }

    # ---------------------------------------------------------------- helpers
    def _open(self):
        for nid, cs in self.sim.circuits.items():
            for c in cs:
                if not c.up and not c.assigned:
                    yield nid, c

    def open_jobs(self):
        sim, w = self.sim, self.sim.w
        idle = [cr for cr in sim.crews if sim._idle(cr)]
        jobs = []
        for nid, c in self._open():
            h = sim.H[nid]
            tau = S.tau_hours(h["median_year_built"], w["wind_mph"])
            repair = sim._repair_hours(h, w)
            share = c.households / max(h["households"] or 1, 1)
            jobs.append({
                "outage_id": f"{nid}:{c.idx}",
                "neighborhood": h["name"],
                "people": round(c.households * S.PERSONS_PER_HOUSEHOLD),
                "households": c.households,
                "indoor_temp_f": round(c.indoor_f, 1),
                "hours_until_below_50f": round(S.hours_to_danger(c.indoor_f, w["temp_f"], tau), 1),
                "hours_without_power": sim.t - c.down_since,
                "critical_facility": c.critical,
                "medical_device_households": round((h["medical_device_households"] or 0) * share, 1),
                "age_65_plus_share": h["age_65_plus_share"],
                "job_hours_by_idle_crew": {cr.cid: round(sim._travel_hours(cr, h) + repair, 1) for cr in idle},
            })
            if self.hide_vulnerability:
                for f in VULNERABILITY_FIELDS:
                    jobs[-1].pop(f)
        jobs.sort(key=lambda j: (j["hours_until_below_50f"], -j["people"]))
        return {
            "hour": sim.t,
            "outdoor_temp_f": round(w["temp_f"], 1),
            "idle_crews": [cr.cid for cr in idle],
            "open_outages_total": len(jobs),
            "listed": min(len(jobs), MAX_JOBS_LISTED),
            "note": "Sorted by hours_until_below_50f, then people. A restored home warms about 4°F per hour.",
            "outages": jobs[:MAX_JOBS_LISTED],
        }

    def dispatch_outage(self, crew_id, outage_id, reason):
        sim = self.sim
        cr = sim.C.get(crew_id)
        if cr is None:
            return {"error": f"Unknown crew_id '{crew_id}'. Valid: {', '.join(sim.C)}"}
        if not sim._idle(cr):
            return {"error": f"{crew_id} is busy ({max(cr.remaining_h, 0):.1f}h left). Pick an idle crew."}
        nid, _, idx = outage_id.rpartition(":")
        if nid not in sim.circuits or not idx.isdigit() or int(idx) >= len(sim.circuits[nid]):
            return {"error": f"Unknown outage_id '{outage_id}'. Use an outage_id from list_open_jobs."}
        c = sim.circuits[nid][int(idx)]
        if c.up:
            return {"error": f"{outage_id} already has power."}
        if c.assigned:
            return {"error": f"{outage_id} already has a crew assigned. Call list_open_jobs for open ones."}
        h, w = sim.H[nid], sim.w
        travel, repair = sim._travel_hours(cr, h), sim._repair_hours(h, w)
        c.assigned, cr.job, cr.remaining_h = True, c, travel + repair
        sim.events.append((w["time"], cr.cid, nid, "dispatched", reason or f"Repair {c.households} homes in {h['name']}"))
        return {"ok": True, "action": "repair", "outage_id": outage_id, "households": c.households,
                "critical_facility": c.critical, "hours_until_power_restored": round(travel + repair, 1)}


TOOLS = copy.deepcopy(TOOL_SCHEMAS)
for t in TOOLS:
    if t["name"] == "dispatch_crew":
        t["description"] = (
            "Send an idle crew to work. Pass outage_id (from list_open_jobs) to repair that specific outage. "
            "Pass only neighborhood_id, with no outage_id, to pre-position the crew there when no outage is waiting. "
            "Travel time grows as snow piles up.")
        t["input_schema"]["properties"]["outage_id"] = {
            "type": "string", "description": "e.g. 'masten_park:3' from list_open_jobs. Preferred for repairs."}
        t["input_schema"]["required"] = ["crew_id", "neighborhood_id", "reason"]
TOOLS.insert(1, {
    "name": "list_open_jobs",
    "description": "Every outage with no crew assigned: people affected, indoor temperature, hours until the "
                   "homes drop below 50°F, vulnerability, and the job time (travel + repair) for each idle crew.",
    "input_schema": {"type": "object", "properties": {}},
})
TOOLS.append({
    "name": "get_grid_signal",
    "description": "REAL regional signal for the current hour: NYISO WEST zone actual electricity load vs the load "
                   "a weather-based demand model expected. A large gap means demand is missing across the region "
                   "(outages and closures). Regional only: it does not say which neighborhood is out.",
    "input_schema": {"type": "object", "properties": {}},
})
