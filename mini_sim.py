import json, os, random, sys
from BaseSimulation import run_tick

STORM = [0.2, 0.3, 0.5, 0.7, 0.9, 1.0, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2]  # storm intensity per hour

class MiniSim:
    def __init__(self, seed=7):
        self.hours, self.tick = len(STORM), 0
        self.nodes = {
            "hospital_1": dict(critical=True,  customers=1,    feeder="F1", vuln=0.9),
            "shelter_1":  dict(critical=True,  customers=1,    feeder="F2", vuln=0.6),
            "elmwood":    dict(critical=False, customers=4000, feeder="F1", vuln=0.8),
            "northtown":  dict(critical=False, customers=6500, feeder="F2", vuln=0.5),
            "southside":  dict(critical=False, customers=5200, feeder="F3", vuln=0.7),
            "eastside":   dict(critical=False, customers=3000, feeder="F3", vuln=0.4),
        }
        for n in self.nodes.values():
            n.update(out=False, repair_left=0, since=None)
        self.crews = {c: dict(at="depot", target=None, eta=0) for c in ("crew_1", "crew_2")}
        # Outages are pre-rolled from the seed, so every policy faces the identical storm.
        rng = random.Random(seed)
        self.events = {}
        for nid, n in self.nodes.items():
            for h, s in enumerate(STORM, start=1):
                if rng.random() < s * n["vuln"] * 0.35:
                    self.events.setdefault(h, []).append(nid)
                    break
        self.customer_hours = 0
        self.critical_hours = 0

    def _risk(self, nid, hour):
        return round(STORM[hour - 1] * self.nodes[nid]["vuln"], 2)

    def apply(self, name, a):
        if name == "get_grid_state":
            return {
                "hour": self.tick + 1,
                "hours_remaining": self.hours - self.tick,
                "nodes": {nid: dict(out=n["out"], critical=n["critical"], customers=n["customers"],
                                    feeder=n["feeder"], risk_now=self._risk(nid, min(self.tick + 1, self.hours)),
                                    repair_hours_left=n["repair_left"] if n["out"] else 0)
                          for nid, n in self.nodes.items()},
                "crews": self.crews,
            }
        if name == "get_forecast":
            nid = a["node_id"]
            if nid not in self.nodes:
                return {"error": f"unknown node {nid}"}
            hrs = [self._risk(nid, self.tick + k) for k in range(1, a["hours"] + 1) if self.tick + k <= self.hours]
            return {"node_id": nid, "risk_by_hour": hrs}
        if name == "dispatch_crew":
            c, nid = a["crew_id"], a["node_id"]
            if c not in self.crews:
                return {"error": f"unknown crew {c}; valid: {list(self.crews)}"}
            if nid not in self.nodes:
                return {"error": f"unknown node {nid}; valid: {list(self.nodes)}"}
            cur = self.crews[c]
            if cur["eta"] == 0 and cur["at"] in self.nodes and self.nodes[cur["at"]]["out"] and cur["at"] != nid:
                return {"error": f"{c} is mid-repair at {cur['at']}; finish it before redirecting"}
            if cur["eta"] == 0 and cur["at"] == nid:   # already on site: no travel, no repair stall
                cur["target"] = nid
                return {"ok": True, "note": f"{c} is already at {nid}", "arrives_in_hours": 0}
            self.crews[c].update(target=nid, eta=1)
            return {"ok": True, "arrives_in_hours": 1}
        return {"ok": True, "note": "not modeled yet"}   # reroute_power, shed_load, open_shelter

    def step(self):
        self.tick += 1
        for nid in self.events.get(self.tick, []):
            self.nodes[nid].update(out=True, repair_left=2, since=self.tick)
        for c in self.crews.values():
            if c["eta"] > 0:
                c["eta"] -= 1
                if c["eta"] == 0:
                    c["at"] = c["target"]
        for nid, n in self.nodes.items():
            if n["out"] and any(c["at"] == nid and c["eta"] == 0 for c in self.crews.values()):
                n["repair_left"] -= 1
                if n["repair_left"] <= 0:
                    n["out"] = False
                    for c in self.crews.values():
                        if c["target"] == nid:
                            c["target"] = None
        for n in self.nodes.values():
            if n["out"]:
                self.customer_hours += n["customers"]
                self.critical_hours += 1 if n["critical"] else 0

    def metrics(self):
        return {"customer_hours_out": self.customer_hours, "critical_facility_hours_out": self.critical_hours}


def baseline(sim):
    """First-come-first-served: oldest unattended outage gets the next free crew. No foresight."""
    waiting = sorted((n["since"], nid) for nid, n in sim.nodes.items()
                     if n["out"] and not any(c["target"] == nid for c in sim.crews.values()))
    free = [cid for cid, c in sim.crews.items() if c["target"] is None]
    for (_, nid), cid in zip(waiting, free):
        sim.apply("dispatch_crew", {"crew_id": cid, "node_id": nid})


def run_baseline(seed=7):
    sim = MiniSim(seed)
    for _ in range(sim.hours):
        baseline(sim)
        sim.step()
    return sim.metrics()


def run_agent(seed=7, replay=False):
    sim = MiniSim(seed)
    os.makedirs("cache", exist_ok=True)
    for t in range(1, sim.hours + 1):
        path = f"cache/seed{seed}_tick_{t}.json"
        if replay and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                log = json.load(f)
            for a in log["actions"]:                 # re-apply saved decisions, no API call
                if not a["tool"].startswith("get_"):
                    sim.apply(a["tool"], a["input"])
        else:
            log = run_tick(sim, t)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(log, f, indent=2)
        sim.step()
    return sim.metrics()


if __name__ == "__main__":
    replay = "replay" in sys.argv
    totals = {"baseline": [0, 0], "agent": [0, 0]}
    seeds = range(1, 6)
    for seed in seeds:
        b, a = run_baseline(seed), run_agent(seed, replay=replay)
        print(seed, "baseline:", b, "| agent:", a)
        for k, m in (("baseline", b), ("agent", a)):
            totals[k][0] += m["customer_hours_out"]
            totals[k][1] += m["critical_facility_hours_out"]
    for k, (ch, cr) in totals.items():
        print(f"avg {k:8}: customer_hours_out={ch / len(seeds):.0f}, critical_facility_hours_out={cr / len(seeds):.1f}")