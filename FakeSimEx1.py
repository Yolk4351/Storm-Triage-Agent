import json
from BaseSimulation import run_tick

class FakeSim:
    def apply(self, name, args):
        if name == "get_grid_state":
            return {"nodes": [{"id": "hospital_1", "critical": True, "risk": 0.8, "out": False}]}
        if name == "get_forecast":
            return {"node_id": args["node_id"], "risk_by_hour": [0.6, 0.8, 0.9]}
        return {"ok": True}

if __name__ == "__main__":
    print(json.dumps(run_tick(FakeSim(), 1), indent=2))