# Storm Triage Agent: data layer

Real December 2022 Buffalo blizzard data, stored in Tiger Cloud (TigerData).

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
| `sim_runs` | table | One row per simulation run (`baseline` or `agent`) | Simulated |
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

## Data disclosure (required by the hackathon rules)
- **Real:** hourly weather (Open-Meteo ERA5 reanalysis for one downtown grid cell) and NYISO load.
- **Estimated:** neighborhood attributes until replaced with Census / Open Data Buffalo values; map coordinates are approximate.
- **Simulated:** power line types, medical-device households, outages, crews, indoor temperatures.
