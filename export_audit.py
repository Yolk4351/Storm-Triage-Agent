"""Decision audit: every action the LLM dispatcher took in one cached storm run, with its one-sentence reason.

Reads only the cached per-hour decisions (no API calls, no database), so it works on any finished run.

    python export_audit.py --seed 2                       # default window, 8 crews
    python export_audit.py --seed 2 --ablation no_vulnerability
    python export_audit.py --folder cache/llm_2022-12-23T0000_2022-12-27T0000_c8_s2

Writes results/audit_<run>.csv (every action) and results/audit_<run>.md (summary + first dispatches).
"""
import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
FULL_TAG = "2022-12-23T0000_2022-12-27T0000"
COLUMNS = ["hour", "time", "action", "crew_id", "neighborhood_id", "outage_id", "people", "indoor_temp_f",
           "hours_until_below_50f", "critical_facility", "hours_until_power_restored", "reason"]


def folder_from_args(a):
    if a.folder:
        return Path(a.folder)
    suffix = "_novuln" if a.ablation == "no_vulnerability" else ""
    return HERE / "cache" / f"llm_{FULL_TAG}_c{a.crews}_s{a.seed}{suffix}"


def start_time(folder):
    m = re.search(r"llm_(\d{4}-\d{2}-\d{2}T\d{4})_", folder.name)
    return datetime.strptime(m.group(1), "%Y-%m-%dT%H%M") if m else None


def load_hours(folder):
    files = sorted(folder.glob("hour_*.json"), key=lambda p: int(p.stem.split("_")[1]))
    if not files:
        raise SystemExit(f"No cached hours in {folder}. Run run_llm.py for this run first.")
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


def rows_for(log, t0):
    hour = log["tick"]
    when = (t0 + timedelta(hours=hour)).strftime("%a %b %d %H:%M") if t0 else ""
    supplied = next((x["result"] for x in log["actions"] if x["tool"] == "list_open_jobs"), None)
    jobs = {j["outage_id"]: j for j in (supplied or {}).get("outages", [])}
    for x in log["actions"]:
        res, inp = x["result"], x["input"]
        if x["tool"] == "dispatch_crew" and res.get("ok"):
            j = jobs.get(inp.get("outage_id"), {})
            yield {"hour": hour, "time": when, "action": res.get("action", "dispatch"),
                   "crew_id": inp.get("crew_id"), "neighborhood_id": inp.get("neighborhood_id"),
                   "outage_id": inp.get("outage_id", ""), "people": j.get("people", ""),
                   "indoor_temp_f": j.get("indoor_temp_f", ""), "hours_until_below_50f": j.get("hours_until_below_50f", ""),
                   "critical_facility": res.get("critical_facility", ""),
                   "hours_until_power_restored": res.get("hours_until_power_restored", res.get("hours_until_arrival", "")),
                   "reason": inp.get("reason", "")}
        elif x["tool"] == "send_alert" and res.get("ok"):
            yield {"hour": hour, "time": when, "action": "alert", "crew_id": "", "neighborhood_id": inp.get("neighborhood_id"),
                   "outage_id": "", "people": "", "indoor_temp_f": "", "hours_until_below_50f": "",
                   "critical_facility": "", "hours_until_power_restored": "", "reason": inp.get("message", "")}


def md_cell(v):
    return str(v).replace("|", "/").replace("\n", " ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2)
    ap.add_argument("--crews", type=int, default=8)
    ap.add_argument("--ablation", choices=["none", "no_vulnerability"], default="none")
    ap.add_argument("--folder", help="a cache/llm_... folder (overrides --seed/--crews/--ablation)")
    ap.add_argument("--show", type=int, default=20, help="dispatches shown in the markdown file")
    a = ap.parse_args()

    folder = folder_from_args(a)
    logs = load_hours(folder)
    t0 = start_time(folder)
    rows = [r for log in logs for r in rows_for(log, t0)]

    out = HERE / "results"
    out.mkdir(exist_ok=True)
    name = folder.name.removeprefix("llm_")
    try:
        source = folder.resolve().relative_to(HERE.resolve()).as_posix()
    except ValueError:
        source = folder.as_posix()
    with open(out / f"audit_{name}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    kinds = Counter(r["action"] for r in rows)
    called = [l for l in logs if not l.get("skipped")]
    tokens = Counter()
    for l in logs:
        tokens.update(l.get("usage", {}))
    flags = sum(1 for l in logs if l.get("truncated"))
    repairs = [r for r in rows if r["action"] == "repair"]
    lines = [
        f"# Decision audit: {name}", "",
        f"Every action the LLM dispatcher took, with the one-sentence reason it gave. Source: `{source}` "
        f"(cached decisions; outages, crews and indoor temperatures are simulated, weather is real).", "",
        f"- Hours: {len(logs)} ({len(logs) - len(called)} skipped because every crew was busy)",
        f"- Repairs dispatched: {kinds.get('repair', 0)} | pre-positioning moves: {kinds.get('staging', 0)} | "
        f"public alerts: {kinds.get('alert', 0)}",
        f"- Repairs sent to homes already below 50°F: "
        f"{sum(1 for r in repairs if r['hours_until_below_50f'] == 0)} of {len(repairs)}",
        f"- Hours with a cut-off reply: {flags}",
    ]
    if tokens.get("calls"):
        lines.append(f"- API calls: {tokens['calls']} | output tokens: {tokens['output']:,} | "
                     f"cache-read tokens: {tokens['cache_read']:,}")
    lines += ["", f"## First {min(a.show, len(rows))} actions", "",
              "| Hour | Time | Action | Crew | Outage / area | People | Indoor °F | Hours to 50°F | Reason |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in rows[:a.show]:
        lines.append("| " + " | ".join(md_cell(v) for v in (
            r["hour"], r["time"], r["action"], r["crew_id"], r["outage_id"] or r["neighborhood_id"],
            r["people"], r["indoor_temp_f"], r["hours_until_below_50f"], r["reason"])) + " |")
    lines += ["", "## Hour summaries (hours where the agent acted)", ""]
    for l in called:
        if l.get("explanation"):
            sig = next((x["result"] for x in l["actions"] if x["tool"] == "get_grid_signal"
                        and "missing_demand_pct" in x["result"]), None)
            gap = f" _(regional load gap seen: {sig['missing_demand_pct']}%)_" if sig else ""
            lines.append(f"- **Hour {l['tick']}:**{gap} {md_cell(l['explanation'].strip())}")
    (out / f"audit_{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} actions ({dict(kinds)}) -> {out / f'audit_{name}.csv'} and .md")


if __name__ == "__main__":
    main()
