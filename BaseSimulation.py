"""LLM dispatcher (llm_agent): one Claude tool-use loop per storm hour, against sim_engine.Simulator."""
import json

import anthropic
from dotenv import load_dotenv

load_dotenv()  # ANTHROPIC_API_KEY and DATABASE_URL from a local .env (never commit it)

from agent_tools import TOOLS

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = "claude-sonnet-5-5"

SYSTEM = """You are the power-restoration dispatcher for Buffalo, NY during the December 2022 blizzard.
Each hour you assign repair crews. You are scored mainly on PERSON-HOURS IN HOMES BELOW 50°F: every hour,
every person in a home below 50°F adds 1, whatever their age. Secondary scores: medical-device households in
cold homes, hours a neighborhood with a critical facility has any outage, and total household-hours without power.

How cold accrues (use this to judge each job):
- A home without power cools toward the outdoor temperature. It adds to the score only once it is below 50°F.
- When power returns, the home warms about 4°F per hour, so a home at 42°F still counts for about 2 more hours.
- The value of a job is roughly: people x (cold hours it prevents) / job_hours, where job_hours is travel + repair.
  An outage whose homes will still be above 50°F when the repair would finish gains little from being fixed now.
  Homes that are already cold, or that will go cold before the crew could finish, are the urgent ones.
  Among similar urgency, more people wins, and a shorter job wins because the crew is free sooner.
- Use critical facilities and medical-device households to break near-ties. Don't let them outweigh many more people.

Each hour:
1) Call list_open_jobs. If idle_crews is empty, there is nothing to do: just explain briefly and stop.
2) Assign every idle crew to a different outage with dispatch_crew, passing crew_id, outage_id and the outage's
   neighborhood_id (the part before ':'). Look at job_hours_by_idle_crew: give each outage to the crew that can
   finish it soonest, and don't send a crew across town when another idle crew is close to it.
   Make all the dispatches in one turn.
3) Only if idle crews remain after every open outage has a crew, you may pre-position them: call get_forecast
   and send a crew (neighborhood_id, no outage_id) toward the highest coming risk. Never send a crew to the
   neighborhood it is already in, and don't move pre-positioned crews again unless the risk picture changes.
4) Optional: send_alert with warming-shelter info where homes are already below 50°F and no crew can finish
   within ~3 hours.
Busy crews cannot be redirected. Actions are validated; if one is rejected, read the error and adjust.
Finish with a 1-3 sentence explanation of this hour's decisions."""

MAX_STEPS = 10  # cap tool-call rounds per hour so it can't loop forever


def run_tick(sim, tick, system=SYSTEM, tools=TOOLS):
    when = getattr(sim, "w", None)
    stamp = f" ({when['time']:%a %b %d %H:%M})" if when else ""
    messages = [{"role": "user", "content": f"It is hour {tick}{stamp} of the storm. Review the grid and act."}]
    log = {"tick": tick, "actions": [], "explanation": ""}

    for _ in range(MAX_STEPS):
        resp = client.messages.create(
            model=MODEL, max_tokens=2000,
            system=system, tools=tools, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            log["explanation"] = "".join(b.text for b in resp.content if b.type == "text")
            break

        results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = sim.apply(block.name, block.input)   # returns dict, may include {"error": "..."}
                log["actions"].append({"tool": block.name, "input": block.input, "result": out})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, default=str),
                })
        messages.append({"role": "user", "content": results})

    return log
