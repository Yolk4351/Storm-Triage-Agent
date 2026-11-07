"""
Storm Triage simulator: plays the REAL Dec 2022 blizzard weather (from Tiger Cloud)
over a simulated Buffalo power grid, once per restoration strategy, and writes the
results back to the database so `run_scoreboard` fills in.

Strategies (same storm, same random failures, same crews -> a fair comparison):
  baseline : "largest outage first" (National Grid's stated policy, WKBW 2022)
  agent    : "most urgent first": people at risk / hours until homes fall below 50°F,
             weighted for elderly residents, medical-device homes and critical sites,
             divided by how long the job takes (travel + repair)

Physical models (simplified, disclose on your slide):
  * Outages: each neighborhood has 8 circuits; each hour every working circuit fails with
    a probability from wind gusts, snowfall rate, tree density and overhead-line share.
  * Indoor cooling: Newton's law of cooling. Older homes and high wind cool faster.
    Calibrated so a typical older house loses heat over ~1-3 days in mild cold
    (Urban Green Council, "Baby It's Cold Inside").
  * Crews: travel between neighborhood centers; roads slow down as snow piles up
    and in extreme wind.

Usage:
  python simulator.py                    # run both strategies, save to Tiger Cloud
  python simulator.py --crews 4          # fewer crews = bigger difference
  python simulator.py --dry-run          # print results only, don't write to the DB
"""
import argparse
import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
TZ = ZoneInfo("America/New_York")

DEPOT = (42.8864, -78.8784)        # crews start downtown
CIRCUITS_PER_NEIGHBORHOOD = 8
PERSONS_PER_HOUSEHOLD = 2.2
DANGER_F = 50.0                    # indoor "unsafe" threshold
SETPOINT_F = 68.0                  # normal indoor temperature with power
REAL_DEC23_SNOW_IN = 22.3          # NWS: Buffalo airport daily record, Dec 23 2022


# =============================================================================
# Data
# =============================================================================
@dataclass
class Circuit:
    nid: str
    idx: int
    households: int
    critical: bool = False
    up: bool = True
    indoor_f: float = SETPOINT_F
    down_since: int = -1
    assigned: bool = False


@dataclass
class Crew:
    cid: str
    loc: tuple = DEPOT
    job: Circuit = None
    remaining_h: float = 0.0


@dataclass
class RunResult:
    strategy: str
    states: list = field(default_factory=list)   # rows for neighborhood_state
    events: list = field(default_factory=list)   # rows for crew_events
    metrics: dict = field(default_factory=dict)


def load_inputs(conn, start, end, snow_target):
    weather = conn.execute(
        """SELECT time, temp_f, wind_mph, gust_mph, snowfall_in
           FROM weather_hourly WHERE time >= %s AND time < %s ORDER BY time""",
        (start, end),
    ).fetchall()
    if not weather:
        raise SystemExit("No weather rows in that window. Did you run load_to_tigerdata.py?")

    # Lake-effect snow is badly underestimated by the coarse weather model, so scale
    # snowfall so Dec 23 matches the NWS-observed total. (Disclose this.)
    dec23 = sum(w["snowfall_in"] or 0 for w in weather
                if w["time"].astimezone(TZ).date() == datetime(2022, 12, 23).date())
    snow_scale = snow_target / dec23 if dec23 > 0 and snow_target else 1.0
    for w in weather:
        w["snowfall_in"] = (w["snowfall_in"] or 0) * snow_scale

    hoods = conn.execute("SELECT * FROM neighborhoods ORDER BY name").fetchall()
    attrs = {(h["households"], h["median_year_built"], h["street_trees"],
              h["overhead_line_share"], h["medical_device_households"]) for h in hoods}
    if len(attrs) == 1:
        print("! All neighborhoods have identical attributes (still placeholders).\n"
              "  Fill in real Census / Open Data Buffalo values in neighborhoods.csv and\n"
              "  re-run load_to_tigerdata.py, or both strategies will look similar.\n")
    return weather, hoods, snow_scale


# =============================================================================
# Physics and risk models
# =============================================================================
def tau_hours(year_built, wind_mph):
    """Thermal time constant: how slowly a home loses heat. Older + windier = faster."""
    base = 20 + 0.6 * max(0, (year_built or 1925) - 1900)       # 1925 home ~35 h
    base = min(max(base, 20), 90)
    return base / (1 + 0.01 * max(0, (wind_mph or 0) - 10))     # wind-driven drafts


def cool(indoor, outdoor, tau):
    return indoor + (outdoor - indoor) * (1 - math.exp(-1 / tau))


def hours_to_danger(indoor, outdoor, tau):
    if indoor <= DANGER_F:
        return 0.0
    if outdoor >= DANGER_F:
        return 99.0
    return -tau * math.log((DANGER_F - outdoor) / (indoor - outdoor))


def failure_prob(w, tree_norm, overhead):
    """Per circuit, per hour. The 'AI risk model' in its simplest form: replace with a
    trained model (e.g. gradient boosting) if you have time."""
    z = (-9.5
         + 0.09 * max((w["gust_mph"] or 0) - 25, 0)
         + 0.35 * w["snowfall_in"]
         + 1.2 * tree_norm
         + 1.0 * (overhead or 0))
    return 1 / (1 + math.exp(-z))


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# =============================================================================
# Simulation
# =============================================================================
def simulate(strategy, weather, hoods, n_crews, seed):
    rng = random.Random(seed)
    H = {h["neighborhood_id"]: h for h in hoods}
    max_trees_per_hh = max((h["street_trees"] or 0) / max(h["households"] or 1, 1) for h in hoods) or 1

    # Common random numbers: the SAME failure draws for every strategy -> fair comparison
    draws = [[[rng.random() for _ in range(CIRCUITS_PER_NEIGHBORHOOD)] for _ in hoods]
             for _ in weather]

    circuits = {}
    for h in hoods:
        per = max(1, round((h["households"] or 0) / CIRCUITS_PER_NEIGHBORHOOD))
        critical = bool((h["critical_facilities"] or "").strip())
        circuits[h["neighborhood_id"]] = [
            Circuit(h["neighborhood_id"], i, per, critical=(critical and i == 0))
            for i in range(CIRCUITS_PER_NEIGHBORHOOD)
        ]
    crews = [Crew(f"crew-{i + 1}") for i in range(n_crews)]
    res = RunResult(strategy)
    cum_snow = 0.0

    for t, w in enumerate(weather):
        cum_snow += w["snowfall_in"]
        road_kmh = max(6.0, 40 - 0.6 * cum_snow) * (0.5 if (w["gust_mph"] or 0) >= 60 else 1.0)

        # 1. Failures
        for hi, h in enumerate(hoods):
            tree_norm = ((h["street_trees"] or 0) / max(h["households"] or 1, 1)) / max_trees_per_hh
            p = failure_prob(w, tree_norm, h["overhead_line_share"])
            for c, u in zip(circuits[h["neighborhood_id"]], draws[t][hi]):
                if c.up and u < p:
                    c.up, c.down_since = False, t

        # 2. Crews work; finished jobs restore power
        for cr in crews:
            if cr.job:
                cr.remaining_h -= 1
                if cr.remaining_h <= 0:
                    c = cr.job
                    c.up, c.assigned, c.down_since = True, False, -1
                    res.events.append((w["time"], cr.cid, c.nid, "restored",
                                       f"Power back for {c.households} homes in {H[c.nid]['name']}"))
                    cr.loc = (H[c.nid]["lat"], H[c.nid]["lon"])
                    cr.job = None

        # 3. Indoor temperatures
        for nid, cs in circuits.items():
            tau = tau_hours(H[nid]["median_year_built"], w["wind_mph"])
            for c in cs:
                c.indoor_f = (cool(c.indoor_f, w["temp_f"], tau) if not c.up
                              else min(SETPOINT_F, c.indoor_f + 4))   # heat recovers

        # 4. Dispatch idle crews
        for cr in crews:
            if cr.job:
                continue
            pick = choose_job(strategy, cr, circuits, H, w, road_kmh, max_trees_per_hh)
            if pick:
                c, travel, repair, reason = pick
                c.assigned, cr.job, cr.remaining_h = True, c, travel + repair
                res.events.append((w["time"], cr.cid, c.nid, "dispatched", reason))

        # 5. Record per-neighborhood state
        for hi, h in enumerate(hoods):
            nid, cs = h["neighborhood_id"], circuits[h["neighborhood_id"]]
            tree_norm = ((h["street_trees"] or 0) / max(h["households"] or 1, 1)) / max_trees_per_hh
            p = failure_prob(w, tree_norm, h["overhead_line_share"])
            tau = tau_hours(h["median_year_built"], w["wind_mph"])
            down = [c for c in cs if not c.up]
            hh_out = sum(c.households for c in down)
            total = sum(c.households for c in cs) or 1
            res.states.append((
                w["time"], nid,
                round(1 - (1 - p) ** CIRCUITS_PER_NEIGHBORHOOD, 4),       # P(any outage this hour)
                hh_out,
                round(sum(c.indoor_f * c.households for c in cs) / total, 1),
                round(min(hours_to_danger(c.indoor_f, w["temp_f"], tau) for c in down), 2) if down else None,
                sum(c.households for c in down if c.indoor_f < DANGER_F),
            ))

    res.metrics = score(res.states, H)
    return res


def choose_job(strategy, crew, circuits, H, w, road_kmh, max_trees_per_hh):
    best, best_score = None, -1
    for nid, cs in circuits.items():
        h = H[nid]
        travel = km(crew.loc, (h["lat"], h["lon"])) / road_kmh
        tree_norm = ((h["street_trees"] or 0) / max(h["households"] or 1, 1)) / max_trees_per_hh
        repair = 2.5 + 1.5 * tree_norm + (1.0 if (w["gust_mph"] or 0) > 45 else 0.0)
        tau = tau_hours(h["median_year_built"], w["wind_mph"])
        for c in cs:
            if c.up or c.assigned:
                continue
            if strategy == "baseline":
                s = c.households * 1000 - c.down_since          # biggest first, then oldest
                reason = f"Largest open outage: {c.households} homes in {h['name']}"
            else:
                # Value of this job per crew-hour: people who are (or soon will be) in a
                # home below 50°F, weighted for vulnerability. A home that will stay warm
                # well past the time it takes to fix it gains little from being fixed now.
                htd = hours_to_danger(c.indoor_f, w["temp_f"], tau)
                job = travel + repair
                share = c.households / max(h["households"] or 1, 1)
                people = c.households * PERSONS_PER_HOUSEHOLD * (1 + 2 * (h["age_65_plus_share"] or 0))
                medical = (h["medical_device_households"] or 0) * share
                weight = people + 25 * medical + (500 if c.critical else 0)
                urgency = 1 / (1 + max(0.0, htd - job) / 6)
                s = weight * urgency / job
                reason = (f"{h['name']}: {c.households} homes at {c.indoor_f:.0f}°F, "
                          + ("already below 50°F" if htd == 0 else f"~{htd:.1f}h until 50°F")
                          + (f", ~{medical:.0f} medical-device homes" if medical >= 1 else "")
                          + (", critical facility" if c.critical else "")
                          + f"; {travel:.1f}h away")
            if s > best_score:
                best, best_score = (c, travel, repair, reason), s
    return best


def score(states, H):
    person_hours = sum(s[6] for s in states) * PERSONS_PER_HOUSEHOLD
    medical = sum(s[6] * (H[s[1]]["medical_device_households"] or 0) / max(H[s[1]]["households"] or 1, 1)
                  for s in states)
    by_hour = {}
    for s in states:
        by_hour[s[0]] = by_hour.get(s[0], 0) + s[3]
    return {
        "person_hours_below_50f": round(person_hours),
        "household_hours_out": sum(s[3] for s in states),
        "medical_household_hours_at_risk": round(medical),
        "peak_households_out": max(by_hour.values()),
    }


# =============================================================================
# Database output
# =============================================================================
UPGRADE_SQL = [
    "ALTER TABLE neighborhood_state ADD COLUMN IF NOT EXISTS households_below_50 INT",
    """CREATE OR REPLACE VIEW run_scoreboard AS
       SELECT r.run_id, r.strategy,
              round(sum(coalesce(s.households_below_50, 0) * 2.2)::numeric) AS person_hours_below_50f,
              sum(s.households_out) AS household_hours_out,
              sum(CASE WHEN s.households_out > 0 AND n.critical_facilities <> '' THEN 1 ELSE 0 END)
                AS critical_facility_hours_out,
              sum(coalesce(s.households_below_50, 0) * n.medical_device_households::float
                  / NULLIF(n.households, 0))::int AS medical_household_hours_at_risk
       FROM sim_runs r
       JOIN neighborhood_state s ON s.run_id = r.run_id
       JOIN neighborhoods n      ON n.neighborhood_id = s.neighborhood_id
       GROUP BY r.run_id, r.strategy""",
]


def save(conn, res, run_id, crews, seed, notes):
    for sql in UPGRADE_SQL:
        conn.execute(sql)
    conn.execute("DELETE FROM sim_runs WHERE run_id = %s", (run_id,))   # cascades
    conn.execute("INSERT INTO sim_runs (run_id, strategy, crews, seed, notes) VALUES (%s,%s,%s,%s,%s)",
                 (run_id, res.strategy, crews, seed, notes))
    with conn.cursor() as cur:
        with cur.copy("COPY neighborhood_state (time, run_id, neighborhood_id, outage_risk, households_out, "
                      "indoor_temp_f, hours_to_danger, households_below_50) FROM STDIN") as cp:
            for s in res.states:
                cp.write_row((s[0], run_id, *s[1:]))
        with cur.copy("COPY crew_events (time, run_id, crew_id, neighborhood_id, action, reason) "
                      "FROM STDIN") as cp:
            for e in res.events:
                cp.write_row((e[0], run_id, *e[1:]))


# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-12-23 00:00")
    ap.add_argument("--end", default="2022-12-27 00:00")
    ap.add_argument("--crews", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--snow-target", type=float, default=REAL_DEC23_SNOW_IN,
                    help="scale model snowfall so Dec 23 totals this many inches (0 = no scaling)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=TZ)
    end = datetime.fromisoformat(args.end).replace(tzinfo=TZ)

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL in .env")
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as conn:
        weather, hoods, snow_scale = load_inputs(conn, start, end, args.snow_target)
        print(f"Storm: {len(weather)} hours, {len(hoods)} neighborhoods, {args.crews} crews, "
              f"snowfall scaled x{snow_scale:.1f} to match NWS\n")

        results = {s: simulate(s, weather, hoods, args.crews, args.seed) for s in ("baseline", "agent")}

        print(f"{'Metric':34}{'Baseline':>12}{'Agent':>12}{'Change':>10}")
        for k in results["baseline"].metrics:
            b, a = results["baseline"].metrics[k], results["agent"].metrics[k]
            change = f"{(a - b) / b * 100:+.0f}%" if b else "-"
            print(f"{k:34}{b:>12,}{a:>12,}{change:>10}")

        if args.dry_run:
            print("\n(dry run: nothing saved)")
            return
        notes = (f"Real weather {args.start} to {args.end}; snowfall x{snow_scale:.2f}; "
                 "simulated grid, crews and indoor temperatures")
        for strategy, res in results.items():
            run_id = f"{strategy}-c{args.crews}-s{args.seed}"
            save(conn, res, run_id, args.crews, args.seed, notes)
            print(f"\nSaved {run_id}: {len(res.states)} state rows, {len(res.events)} crew events")
        print("\nIn Tiger Cloud:  SELECT * FROM run_scoreboard;")


if __name__ == "__main__":
    main()
