"""Local backend for the frontend: storm replays, plus on-demand AI runs.

    uvicorn server:app --port 8000          # then, in frontend/: npm run dev

GET  /api/storms                     storms, with whether an AI run exists and its cost estimate
GET  /api/replay/{storm}/{policy}    hour-by-hour replay (largest_first and rules: simulated now, free;
                                     llm_agent: from cached AI decisions only, never calls the API)
POST /api/llm-runs/{storm}           start an AI run for a storm (CALLS THE CLAUDE API, costs money)
GET  /api/llm-runs/{storm}           progress of that run

Only POST /api/llm-runs calls the Claude API, one run at a time.
"""
import threading
import traceback
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

import replay as R

load_dotenv()
app = FastAPI(title="Storm Triage Agent")
_runs = {}                       # storm_id -> {"state", "hour", "hours", "message"}
_lock = threading.Lock()


@lru_cache(maxsize=32)
def _replay(storm_id, policy, seed, crews, stamp):
    return R.build_replay(storm_id, policy, seed, crews)


@app.get("/api/storms")
def storms():
    out = R.storm_list()
    for s in out:
        s["llm_run"] = _runs.get(s["id"])
    return out


@app.get("/api/replay/{storm_id}/{policy}")
def get_replay(storm_id: str, policy: str, seed: int = R.DEFAULT_SEED, crews: int = R.DEFAULT_CREWS):
    if storm_id not in R.STORM_INFO:
        raise HTTPException(404, f"Unknown storm '{storm_id}'")
    if policy not in R.POLICIES:
        raise HTTPException(404, f"Unknown policy '{policy}'")
    if policy == "llm_agent" and not R.llm_available(storm_id, seed, crews):
        raise HTTPException(409, "No AI run for this storm yet. Start one with POST /api/llm-runs/{storm}.")
    # AI replays change when a run finishes, so key the cache on how many hours are cached
    stamp = R.llm_hours_cached(storm_id, seed, crews) if policy == "llm_agent" else 0
    return _replay(storm_id, policy, seed, crews, stamp)


@app.get("/api/llm-runs/{storm_id}")
def run_status(storm_id: str):
    if storm_id not in R.STORM_INFO:
        raise HTTPException(404, f"Unknown storm '{storm_id}'")
    if storm_id in _runs:
        return _runs[storm_id]
    done = R.llm_available(storm_id)
    return {"state": "done" if done else "idle", "hour": R.llm_hours_cached(storm_id),
            "hours": R.storm_hours(storm_id), "message": ""}


@app.post("/api/llm-runs/{storm_id}")
def start_run(storm_id: str):
    if storm_id not in R.STORM_INFO:
        raise HTTPException(404, f"Unknown storm '{storm_id}'")
    if R.llm_available(storm_id):
        return {"state": "done", "hour": R.storm_hours(storm_id), "hours": R.storm_hours(storm_id),
                "message": "Already available"}
    with _lock:
        busy = [s for s, r in _runs.items() if r["state"] == "running"]
        if busy:
            raise HTTPException(409, f"An AI run is already in progress ({busy[0]}). One at a time.")
        status = {"state": "running", "hour": R.llm_hours_cached(storm_id), "hours": R.storm_hours(storm_id),
                  "message": "Starting"}
        _runs[storm_id] = status

    def progress(t, total):
        status.update(hour=t, hours=total, message=f"Hour {t} of {total}")

    def work():
        try:
            R.run_llm_storm(storm_id, on_hour=progress)
            status.update(state="done", message="Finished")
        except Exception as e:                       # surface the error in the UI instead of dying silently
            traceback.print_exc()
            status.update(state="error", message=f"{type(e).__name__}: {e}"[:300])

    threading.Thread(target=work, daemon=True).start()
    return status
