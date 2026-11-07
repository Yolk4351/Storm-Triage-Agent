"""
Stepwise Storm Triage simulator, so an LLM agent can make decisions hour by hour.

The physics, risk model and rule-based strategies are imported unchanged from
simulator.py, and the random failure draws are generated the same way, so the
rule-based runs here reproduce simulator.py's numbers exactly.

    sim = load_sim(crews=8, seed=42)          # real weather + neighborhoods from Tiger Cloud
    while not sim.done:
        sim.state()                            # what the agent sees this hour
        sim.apply("dispatch_crew", {...})      # agent actions, validated; errors come back as {"error": ...}
        sim.step()                             # record this hour, advance to the next
    sim.metrics()

Rule-based policies for comparison:
    sim.run_policy("baseline")   # largest outage first (National Grid's stated policy)
    sim.run_policy("rules")      # A's "most urgent first" formula (called "agent" in simulator.py)

Disclose on the slide: get_forecast uses the real future weather from the replay,
so the agent has a perfect weather forecast. Outage risk per hour is still random.

Usage:
    python sim_engine.py --dry-run           # check the rule-based runs match simulator.py
    python sim_engine.py --crews 4 --save    # save rule-based runs to Tiger Cloud
"""
import argparse
import math
import os
import random
from datetime import datetime

import simulator as S

RULE_POLICIES = {"baseline": "baseline", "rules": "agent"}  # our name -> simulator.py's name
MAX_FORECAST_HOURS = 12


class Simulator:
    def __init__(self, weather, hoods, n_crews=8, seed=42):
        self.weather, self.hoods = weather, hoods
        self.H = {h["neighborhood_id"]: h for h in hoods}
        self.max_trees = max((h["street_trees"] or 0) / max(h["households"] or 1, 1) for h in hoods) or 1

        # Same draw order as simulator.simulate() -> identical failures for every policy
        rng = random.Random(seed)
        self.draws = [[[rng.random() for _ in range(S.CIRCUITS_PER_NEIGHBORHOOD)] for _ in hoods]
                      for _ in weather]

        self.circuits = {}
        for h in hoods:
            per = max(1, round((h["households"] or 0) / S.CIRCUITS_PER_NEIGHBORHOOD))
            critical = bool((h["critical_facilities"] or "").strip())
            self.circuits[h["neighborhood_id"]] = [
                S.Circuit(h["neighborhood_id"], i, per, critical=(critical and i == 0))
                for i in range(S.CIRCUITS_PER_NEIGHBORHOOD)
            ]
        self.crews = [S.Crew(f"crew-{i + 1}") for i in range(n_crews)]
        for cr in self.crews:
            cr.staging = None  # neighborhood a crew is driving to with no repair job (pre-positioning)
        self.C = {cr.cid: cr for cr in self.crews}

        self.states, self.events = [], []
        self.cum_snow = 0.0
        self.road_kmh = 40.0
        self.t = 0
        self.done = not weather
        if not self.done:
            self._physics()

    # ------------------------------------------------------------------ helpers
    @property
    def w(self):
        return self.weather[self.t]

    def _tree_norm(self, h):
        return ((h["street_trees"] or 0) / max(h["households"] or 1, 1)) / self.max_trees

    def _repair_hours(self, h, w):
        return 2.5 + 1.5 * self._tree_norm(h) + (1.0 if (w["gust_mph"] or 0) > 45 else 0.0)

    def _travel_hours(self, crew, h):
        return S.km(crew.loc, (h["lat"], h["lon"])) / self.road_kmh

    def _idle(self, cr):
        return cr.job is None and cr.staging is None

    def _where(self, cr):
        if cr.loc == S.DEPOT:
            return "depot"
        return min(self.hoods, key=lambda h: S.km(cr.loc, (h["lat"], h["lon"])))["neighborhood_id"]

    # ------------------------------------------------- one hour (simulator.py steps 1-3 and 5)
    def _physics(self):
        """Steps 1-3 of an hour: failures, crews work, homes cool. Decisions come next."""
        w, t, H = self.w, self.t, self.H
        self.cum_snow += w["snowfall_in"]
        self.road_kmh = max(6.0, 40 - 0.6 * self.cum_snow) * (0.5 if (w["gust_mph"] or 0) >= 60 else 1.0)

        for hi, h in enumerate(self.hoods):
            p = S.failure_prob(w, self._tree_norm(h), h["overhead_line_share"])
            for c, u in zip(self.circuits[h["neighborhood_id"]], self.draws[t][hi]):
                if c.up and u < p:
                    c.up, c.down_since = False, t

        for cr in self.crews:
            if cr.job:
                cr.remaining_h -= 1
                if cr.remaining_h <= 0:
                    c = cr.job
                    c.up, c.assigned, c.down_since = True, False, -1
                    self.events.append((w["time"], cr.cid, c.nid, "restored",
                                        f"Power back for {c.households} homes in {H[c.nid]['name']}"))
                    cr.loc = (H[c.nid]["lat"], H[c.nid]["lon"])
                    cr.job = None
            elif cr.staging:
                cr.remaining_h -= 1
                if cr.remaining_h <= 0:
                    nid = cr.staging
                    cr.loc, cr.staging = (H[nid]["lat"], H[nid]["lon"]), None
                    self.events.append((w["time"], cr.cid, nid, "arrived",
                                        f"Staged in {H[nid]['name']}, waiting for orders"))

        for nid, cs in self.circuits.items():
            tau = S.tau_hours(H[nid]["median_year_built"], w["wind_mph"])
            for c in cs:
                c.indoor_f = (S.cool(c.indoor_f, w["temp_f"], tau) if not c.up
                              else min(S.SETPOINT_F, c.indoor_f + 4))

    def _record(self):
        """Step 5 of an hour: one state row per neighborhood (same columns as simulator.py)."""
        w = self.w
        for h in self.hoods:
            nid, cs = h["neighborhood_id"], self.circuits[h["neighborhood_id"]]
            p = S.failure_prob(w, self._tree_norm(h), h["overhead_line_share"])
            tau = S.tau_hours(h["median_year_built"], w["wind_mph"])
            down = [c for c in cs if not c.up]
            total = sum(c.households for c in cs) or 1
            self.states.append((
                w["time"], nid,
                round(1 - (1 - p) ** S.CIRCUITS_PER_NEIGHBORHOOD, 4),
                sum(c.households for c in down),
                round(sum(c.indoor_f * c.households for c in cs) / total, 1),
                round(min(S.hours_to_danger(c.indoor_f, w["temp_f"], tau) for c in down), 2) if down else None,
                sum(c.households for c in down if c.indoor_f < S.DANGER_F),
            ))

    def step(self):
        """Finish this hour (record it) and start the next. Returns True when the storm is over."""
        if self.done:
            return True
        self._record()
        self.t += 1
        if self.t >= len(self.weather):
            self.done = True
        else:
            self._physics()
        return self.done

    # ------------------------------------------------------- rule-based policies
    def auto_dispatch(self, policy):
        """Give every idle crew a job using a rule-based policy ('baseline' or 'rules')."""
        name = RULE_POLICIES[policy]
        for cr in self.crews:
            if not self._idle(cr):
                continue
            pick = S.choose_job(name, cr, self.circuits, self.H, self.w, self.road_kmh, self.max_trees)
            if pick:
                c, travel, repair, reason = pick
                c.assigned, cr.job, cr.remaining_h = True, c, travel + repair
                self.events.append((self.w["time"], cr.cid, c.nid, "dispatched", reason))

    def run_policy(self, policy):
        while not self.done:
            self.auto_dispatch(policy)
            self.step()
        return self.metrics()

    def metrics(self):
        if not self.states:
            return {}
        m = S.score(self.states, self.H)
        m["critical_facility_hours_out"] = sum(
            1 for s in self.states if s[3] > 0 and (self.H[s[1]]["critical_facilities"] or "").strip())
        return m

    def result(self, strategy):
        """Package the run for simulator.save() so it lands in Tiger Cloud."""
        return S.RunResult(strategy, self.states, self.events, self.metrics())

    # ------------------------------------------------------- what the agent sees
    def state(self):
        w, H = self.w, self.H
        hoods = []
        for h in self.hoods:
            nid, cs = h["neighborhood_id"], self.circuits[h["neighborhood_id"]]
            tau = S.tau_hours(h["median_year_built"], w["wind_mph"])
            p = S.failure_prob(w, self._tree_norm(h), h["overhead_line_share"])
            down = [c for c in cs if not c.up]
            total = sum(c.households for c in cs) or 1
            hoods.append({
                "neighborhood_id": nid,
                "name": h["name"],
                "households": h["households"],
                "households_out": sum(c.households for c in down),
                "open_outages_unassigned": sum(1 for c in down if not c.assigned),
                "outages_being_repaired": sum(1 for c in down if c.assigned),
                "avg_indoor_temp_f": round(sum(c.indoor_f * c.households for c in cs) / total, 1),
                "households_below_50f": sum(c.households for c in down if c.indoor_f < S.DANGER_F),
                "hours_until_first_home_below_50f":
                    round(min(S.hours_to_danger(c.indoor_f, w["temp_f"], tau) for c in down), 1) if down else None,
                "outage_risk_this_hour": round(1 - (1 - p) ** S.CIRCUITS_PER_NEIGHBORHOOD, 3),
                "age_65_plus_share": h["age_65_plus_share"],
                "medical_device_households": h["medical_device_households"],
                "critical_facilities": h["critical_facilities"] or "",
            })
        crews = []
        for cr in self.crews:
            if cr.job:
                status, target = "repairing", cr.job.nid
            elif cr.staging:
                status, target = "traveling", cr.staging
            else:
                status, target = "idle", None
            crews.append({"crew_id": cr.cid, "status": status, "location": self._where(cr),
                          "heading_to": target, "hours_until_free": round(max(cr.remaining_h, 0), 1)
                          if not self._idle(cr) else 0})
        return {
            "hour": self.t,
            "time": self.w["time"].isoformat(),
            "hours_left_in_storm": len(self.weather) - self.t,
            "weather": {k: round(w[k] or 0, 1) for k in ("temp_f", "wind_mph", "gust_mph", "snowfall_in")},
            "road_speed_kmh": round(self.road_kmh, 1),
            "neighborhoods": hoods,
            "crews": crews,
        }

    def forecast(self, neighborhood_id, hours):
        h = self.H[neighborhood_id]
        out = []
        for k in range(1, hours + 1):
            if self.t + k >= len(self.weather):
                break
            w = self.weather[self.t + k]
            p = S.failure_prob(w, self._tree_norm(h), h["overhead_line_share"])
            out.append({"hours_ahead": k, "temp_f": round(w["temp_f"], 1), "gust_mph": round(w["gust_mph"] or 0, 1),
                        "snowfall_in": round(w["snowfall_in"], 2),
                        "outage_risk": round(1 - (1 - p) ** S.CIRCUITS_PER_NEIGHBORHOOD, 3)})
        return {"neighborhood_id": neighborhood_id, "name": h["name"], "forecast": out}

    # ------------------------------------------------------- agent actions
    def apply(self, name, args):
        """Run one agent tool. Always returns a dict; illegal actions return {"error": "..."}."""
        try:
            if name == "get_grid_state":
                return self.state()
            if name == "get_forecast":
                hours = int(args.get("hours", 6))
                if not 1 <= hours <= MAX_FORECAST_HOURS:
                    return {"error": f"hours must be between 1 and {MAX_FORECAST_HOURS}"}
                return self.forecast(self._hood(args["neighborhood_id"]), hours)
            if name == "dispatch_crew":
                return self._dispatch(args["crew_id"], args["neighborhood_id"], args.get("reason", ""))
            if name == "send_alert":
                nid = self._hood(args["neighborhood_id"])
                self.events.append((self.w["time"], "dispatcher", nid, "alert", str(args["message"])[:500]))
                return {"ok": True}
            return {"error": f"Unknown tool '{name}'. Tools: get_grid_state, get_forecast, dispatch_crew, send_alert"}
        except KeyError as e:
            return {"error": f"Missing argument {e}"}
        except ValueError as e:
            return {"error": str(e)}

    def _hood(self, nid):
        if nid not in self.H:
            raise ValueError(f"Unknown neighborhood_id '{nid}'. Valid: {', '.join(self.H)}")
        return nid

    def _dispatch(self, crew_id, nid, reason):
        cr = self.C.get(crew_id)
        if cr is None:
            return {"error": f"Unknown crew_id '{crew_id}'. Valid: {', '.join(self.C)}"}
        nid = self._hood(nid)
        if not self._idle(cr):
            where = cr.job.nid if cr.job else cr.staging
            return {"error": f"{crew_id} is busy (heading to or working in {self.H[where]['name']}, "
                             f"{max(cr.remaining_h, 0):.1f}h left). Pick an idle crew."}
        h, w = self.H[nid], self.w
        travel = self._travel_hours(cr, h)
        open_jobs = [c for c in self.circuits[nid] if not c.up and not c.assigned]

        if open_jobs:
            # Critical facility first, then the coldest homes
            c = min(open_jobs, key=lambda c: (not c.critical, c.indoor_f))
            repair = self._repair_hours(h, w)
            c.assigned, cr.job, cr.remaining_h = True, c, travel + repair
            self.events.append((w["time"], cr.cid, nid, "dispatched",
                                reason or f"Repair {c.households} homes in {h['name']}"))
            return {"ok": True, "action": "repair", "households": c.households,
                    "critical_facility": c.critical, "hours_until_power_restored": round(travel + repair, 1)}

        if travel < 0.05:
            return {"error": f"{crew_id} is already in {h['name']} and there is no open outage there. "
                             "It will stay here until you send it somewhere else."}
        cr.staging, cr.remaining_h = nid, travel
        self.events.append((w["time"], cr.cid, nid, "staged",
                            reason or f"Pre-positioning in {h['name']}"))
        return {"ok": True, "action": "staging", "note": "No open outage there yet; crew will wait on site.",
                "hours_until_arrival": round(travel, 1)}


# Tool definitions for the Claude API (C imports these instead of keeping his own copy)
TOOL_SCHEMAS = [
    {"name": "get_grid_state",
     "description": "Current hour: weather, every neighborhood (outages, indoor temperatures, hours until homes "
                    "drop below 50°F, outage risk, vulnerable residents, critical facilities) and every crew.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_forecast",
     "description": f"Weather and outage risk for one neighborhood over the next 1-{MAX_FORECAST_HOURS} hours.",
     "input_schema": {"type": "object",
                      "properties": {"neighborhood_id": {"type": "string"},
                                     "hours": {"type": "integer", "minimum": 1, "maximum": MAX_FORECAST_HOURS}},
                      "required": ["neighborhood_id", "hours"]}},
    {"name": "dispatch_crew",
     "description": "Send an idle crew to a neighborhood. If it has an open outage the crew repairs it (critical "
                    "facility first, then coldest homes); otherwise the crew pre-positions there and waits. "
                    "Travel time grows as snow piles up.",
     "input_schema": {"type": "object",
                      "properties": {"crew_id": {"type": "string"}, "neighborhood_id": {"type": "string"},
                                     "reason": {"type": "string", "description": "One sentence: why this job now."}},
                      "required": ["crew_id", "neighborhood_id", "reason"]}},
    {"name": "send_alert",
     "description": "Send a public alert to a neighborhood (e.g. warming shelter info). Logged, no physical effect.",
     "input_schema": {"type": "object",
                      "properties": {"neighborhood_id": {"type": "string"}, "message": {"type": "string"}},
                      "required": ["neighborhood_id", "message"]}},
]


def load_sim(start="2022-12-23 00:00", end="2022-12-27 00:00", crews=8, seed=42,
             snow_target=S.REAL_DEC23_SNOW_IN):
    """Pull the real storm from Tiger Cloud and build a fresh Simulator."""
    import psycopg
    from psycopg.rows import dict_row
    s = datetime.fromisoformat(start).replace(tzinfo=S.TZ)
    e = datetime.fromisoformat(end).replace(tzinfo=S.TZ)
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        weather, hoods, _ = S.load_inputs(conn, s, e, snow_target)
    return Simulator(weather, hoods, crews, seed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crews", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true", help="print only (default)")
    ap.add_argument("--save", action="store_true", help="write the rule-based runs to Tiger Cloud")
    args = ap.parse_args()

    runs = {}
    for policy in RULE_POLICIES:
        sim = load_sim(crews=args.crews, seed=args.seed)
        sim.run_policy(policy)
        runs[policy] = sim

    keys = list(runs["baseline"].metrics())
    print(f"\n{'Metric':34}{'Baseline':>12}{'Rules':>12}{'Change':>10}")
    for k in keys:
        b, r = runs["baseline"].metrics()[k], runs["rules"].metrics()[k]
        print(f"{k:34}{b:>12,}{r:>12,}{(f'{(r - b) / b * 100:+.0f}%' if b else '-'):>10}")

    if args.save:
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
            for policy, sim in runs.items():
                run_id = f"{policy}-c{args.crews}-s{args.seed}"
                S.save(conn, sim.result(policy), run_id, args.crews, args.seed,
                       "Real weather Dec 23-27 2022; simulated grid, crews, indoor temps (sim_engine)")
                print(f"Saved {run_id}")
    else:
        print("\n(nothing saved; add --save to write to Tiger Cloud)")


if __name__ == "__main__":
    main()
