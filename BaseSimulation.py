import json
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = "claude-sonnet-5-5"

SYSTEM = """You are a grid operations dispatcher during a lake-effect snowstorm.
Each turn you see the current grid state and forecast.
Priorities each hour:
1) Every outage that has no crew assigned gets one, largest customer count first, unless a critical facility is out (those come first).
2) Never redirect a crew that is mid-repair.
3) Only pre-position a crew if it is idle AND no outage is waiting.
Dispatch every idle crew every hour; an idle crew is wasted.
Use the tools to act. Actions are validated; if one is rejected, adjust and try again.
When done, give a 1-3 sentence explanation of your reasoning for this hour."""

TOOLS = [
    {
        "name": "get_grid_state",
        "description": "Current outages, loads, crew locations, and risk scores per node.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_forecast",
        "description": "Predicted outage risk and demand for a node over the next N hours.",
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}, "hours": {"type": "integer"}},
            "required": ["node_id", "hours"],
        },
    },
    {
        "name": "dispatch_crew",
        "description": "Send a repair crew to a node. Crews are limited and have travel time.",
        "input_schema": {
            "type": "object",
            "properties": {"crew_id": {"type": "string"}, "node_id": {"type": "string"}},
            "required": ["crew_id", "node_id"],
        },
    },
    {
        "name": "reroute_power",
        "description": "Shift load from one feeder to another, bounded by capacity.",
        "input_schema": {
            "type": "object",
            "properties": {"from_feeder": {"type": "string"}, "to_feeder": {"type": "string"}},
            "required": ["from_feeder", "to_feeder"],
        },
    },
    {
        "name": "shed_load",
        "description": "Reduce load on a feeder by a percent to protect critical nodes.",
        "input_schema": {
            "type": "object",
            "properties": {"feeder_id": {"type": "string"}, "percent": {"type": "integer"}},
            "required": ["feeder_id", "percent"],
        },
    },
    {
        "name": "open_shelter",
        "description": "Open a warming shelter in a neighborhood.",
        "input_schema": {
            "type": "object",
            "properties": {"neighborhood": {"type": "string"}},
            "required": ["neighborhood"],
        },
    },
]

MAX_STEPS = 8  # cap tool-call rounds per tick so it can't loop forever


def run_tick(sim, tick):
    messages = [{"role": "user", "content": f"It is hour {tick} of the storm. Review the grid and act."}]
    log = {"tick": tick, "actions": [], "explanation": ""}

    for _ in range(MAX_STEPS):
        resp = client.messages.create(
            model=MODEL, max_tokens=1500,
            system=SYSTEM, tools=TOOLS, messages=messages,
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
                    "content": json.dumps(out),
                })
        messages.append({"role": "user", "content": results})

    return log