# Storm Triage Agent: data layer

Real December 2022 Buffalo blizzard data, stored in Tiger Cloud (TigerData).

> Utilities can't see indoor temperatures. Given that signal, an AI dispatcher can send crews where homes are about to become unsafe.

## Restoration policies compared

All three play the same storm with the same random failures and the same crews. Crews are generic restoration crews; the crew count (default 8) is an assumption, not a real staffing figure.

| Policy | What it is |
|---|---|
| `largest_first` | Simple reference policy: the outage affecting the most homes goes first |
| `rules` | Hand-built formula: people at risk, weighted for vulnerability, by how soon homes drop below 50°F, per hour of crew time |
| `llm_agent` | Claude as dispatcher, choosing crews hour by hour with tools (`BaseSimulation.py`, `run_llm.py`) |

## Setup (5 minutes)

1. Create a **free Tiger Cloud service** at tigerdata.com and copy its connection string.
2. In this folder:
   ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env        # paste your connection string into .env
   ```
3. Get the data and load it:
   ```bash
   python fetch_storm_data.py     # downloads real weather + NYISO load -> data/*.csv
   python load_to_tigerdata.py    # creates tables and loads everything
   ```
   Both scripts are safe to re-run.

## What's in the database

| Table | Type | Contents | Real or simulated |
|---|---|---|---|
| `weather_hourly` | hypertable | Buffalo hourly temp, wind, gusts, snow (Open-Meteo / ERA5) | Real |
| `grid_load_hourly` | hypertable | NYISO WEST zone (Zone A) + NY total load, MW | Real |
| `neighborhoods` | table | 13 Buffalo neighborhoods + attributes | Estimates until you replace the `_est` columns in `data/neighborhoods.csv` |
| `sim_runs` | table | One row per simulation run (`largest_first`, `rules` or `llm_agent`) | Simulated |
| `neighborhood_state` | hypertable | Per neighborhood, per hour: outage risk, households out, indoor temp, hours to danger | Simulated |
| `crew_events` | hypertable | Crew dispatches/arrivals + the agent's explanation | Simulated |
| `storm_summary_3h` | continuous aggregate | 3-hour storm summary (max gust, min temp, snowfall) | Real |
| `run_scoreboard` | view | **The demo scoreboard**: person-hours below 50°F, critical facility hours out, etc., per run | Simulated |

`queries.sql` has ready-made queries: worst storm hours, weather vs. grid load, a forecast lookup the agent can use as a tool, the live city state, and the scoreboard.

## For the simulator team

Write one `sim_runs` row per run, then one `neighborhood_state` row per neighborhood per hour, and a `crew_events` row each time a crew moves. The scoreboard updates automatically:

```sql
SELECT * FROM run_scoreboard;
```

## Plausibility check against real load (`calibrate.py`)

We compare the *shape over time* of two curves for Dec 23–27, 2022:
- **Real:** NYISO WEST zone lost load = actual load minus what `demand_model.py` expected from the weather.
- **Simulated:** households without power per hour under `largest_first`, averaged over 10 seeds.

Only the shape is compared (correlation, peak timing), never absolute MW: the NYISO zone is much larger than our 13 neighborhoods. Lost load also reflects changed human behavior (closed businesses, the driving ban, the Christmas holiday), so this is a **plausibility check, not validation**.

**Result:** the curves do not match. Hourly correlation is **−0.59** at the current failure intercept (−9.5), with the real neighborhood data. Simulated outages peak around Dec 24, about 2 days before real lost load peaks (Dec 26, 09:00). A coarse grid search over the failure intercept (−11 to −7.5), the only scalar we allowed ourselves to adjust, never gave a positive correlation (best −0.38). So we **kept −9.5**: the intercept scales how many outages happen but cannot move when they happen. The likely gap is restoration speed. In the real storm outages piled up for days while crews could not reach them; in the simulator they are repaired within hours. Full grid and decision: `data/calibration.json`.

## Neighborhood data sources (`fetch_real_attributes.py`, details in `data/sources.json`)

| Column | Status | Source | Notes |
|---|---|---|---|
| `street_trees` | **Real** | City of Buffalo [Tree Inventory](https://data.buffalony.gov/d/n4ni-uuec) (DPW Parks & Streets), Public Domain | Live trees only (vacant sites and stumps excluded), each assigned to the nearest neighborhood center within 1.5 km; 19,146 of 69,419 trees fall outside that radius and are not counted. Current inventory, not December 2022. Retrieved 2026-11-07. |
| `medical_device_households` | **Real, allocated** | [HHS emPOWER](https://services2.arcgis.com/ZQ4jTQn6k7VPXEwO/arcgis/rest/services/HHS_emPOWER_REST_Service_Public/FeatureServer/1), ZIP level, public HHS data | Medicare beneficiaries (people, Medicare only, not households) with a claim for electricity-dependent equipment. ZIP counts split to census tracts with the Census 2020 ZCTA–tract relationship file, weighted by tract households. Current monthly release, not December 2022. Retrieved 2026-11-07. |
| `overhead_line_share_est` | **Placeholder** | none found | 0.85 everywhere; no public data on overhead vs underground lines by neighborhood. |
| population, households, year built, 65+ share | Real | Census ACS 2023 5-year, by tract | Tracts assigned to the nearest neighborhood center, so boundaries are approximate. |

With real tree counts, outage risk now differs by neighborhood: 0.19 (Kaisertown) to 0.42 (Elmwood Village) at the worst storm hour, where before it was 0.42 everywhere. The failure model scales tree density relative to the densest neighborhood, so most neighborhoods now fail less often and the simulated storm is milder overall.

**Official values are `data/neighborhoods.csv`.** The shared Tiger Cloud `neighborhoods` table currently has the same tree counts but different medical-device numbers from an earlier load. Run `python load_to_tigerdata.py` once the team agrees, so the simulator (which reads the database) matches this file.

## Data disclosure (required by the hackathon rules)
- **Real:** hourly weather (Open-Meteo ERA5 reanalysis for one downtown grid cell) and NYISO load.
- **Estimated:** neighborhood attributes until replaced with Census / Open Data Buffalo values; map coordinates are approximate.
- **Real (added):** street tree counts (Open Data Buffalo) and electricity-dependent Medicare beneficiaries (HHS emPOWER), both current rather than 2022 snapshots.
- **Simulated:** power line types (placeholder 0.85), outages, crews, repair times, indoor temperatures.
