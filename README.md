# Storm Triage Agent

**An AI dispatcher that sends power-repair crews to the homes getting cold fastest, tested on the real December 2022 Buffalo blizzard.**

> Utilities fix the biggest outages first, but they can't see indoor temperatures. If they could, an AI dispatcher could send crews where homes are about to become unsafe. We built a simulation to test that idea.

Built for UB Hacking 2026 (Radial Ventures track: AI that interacts with the physical world). It follows **Sense → Understand → Act**: real weather and grid data come in, the model estimates how fast each neighborhood's homes are cooling, and the dispatcher assigns crews and explains each choice.

## Results

Dec 23–27, 2022 blizzard, 8 crews, the same simulated outages for every policy (seed 2). Lower is better.

| Policy | What it does | Person-hours below 50°F |
|---|---|---|
| `largest_first` | The outage affecting the most homes goes first (how utilities usually prioritize) | 494,421 |
| `rules` | Hand-built formula: people at risk, weighted for vulnerability, by how soon homes drop below 50°F, per hour of crew time | 319,891 |
| `llm_agent` | Claude Sonnet 5.5 dispatches crews hour by hour with tools | **203,958 / 243,481 / 227,093** (3 runs) |

The AI cut cold person-hours by **51–59%** compared with `largest_first`, and beat `rules` in all three runs. LLM results vary from run to run, which is why all three are listed. They come from **one seed**; the rule-based policies were also tested across 20 seeds (see Robustness below).

**Person-hours below 50°F** means each person in a home below 50°F adds one for every hour it stays that cold. The simulator also tracks medical-device households at risk, critical facilities without power, household-hours out and peak households out.

## How it works

**Simulation** (`simulator.py`, `sim_engine.py`)
- 13 Buffalo neighborhoods, each with 8 power circuits.
- Every hour, each circuit has a chance of failing. The chance rises with wind gusts, snow, street-tree density and overhead lines.
- Homes without power lose heat at a rate set by the age of the housing and the wind. Older, draftier homes cool fastest.
- Repairs take 2.5–5 hours, and crews travel more slowly as snow builds up.
- The seed fixes which circuits fail and when. Every policy runs on the same seed, so comparisons are paired.
- Crews are generic restoration crews. The crew count (default 8) is an assumption, not a real staffing figure.

**AI dispatcher** (`BaseSimulation.py`, `agent_tools.py`, `run_llm.py`)
- Every simulated hour with an idle crew, Claude gets the open outages and the regional grid signal. It can inspect neighborhoods, then dispatches crews to specific outages and gives a one-line reason for each.
- Hours with no idle crew are skipped, and prompts are cached. One full storm costs roughly $1.40 in API usage.
- Every decision is saved under `cache/`, so runs replay for free. `export_audit.py` writes a full decision log to `results/audit_*.csv` and `.md`.

**Grid signal from real NYISO data** (`demand_model.py`)
- Trained on about 7,300 hours of NYISO WEST zone load and weather from past winters. It predicts normal load with a **2.7%** average error, against 4.4% for "same hour yesterday" (`models/demand_model_metrics.json`).
- During the blizzard, actual load fell short of the prediction by about **7% on average**. That gap measures the storm's real impact on the grid, and Claude sees it each hour as context.
- The signal is not an input to the simulated outages or the scores.

**Frontend** (`frontend/`, `server.py`, `replay.py`)
- React, Vite, Mapbox and deck.gl, with real Census 2020 tract boundaries grouped into the 13 neighborhoods.
- Replays any storm hour by hour, with Baseline and AI side by side. It colors neighborhoods by outages and cold homes, animates crews, and shows the AI's reasoning.
- A FastAPI backend serves the replays and can start a new AI run for any storm.

## Data

| Data | Source | Real or simulated |
|---|---|---|
| Hourly temperature, wind, gusts, snow | Open-Meteo (ERA5 reanalysis, one downtown Buffalo grid cell). Dec 2022 snowfall scaled to the NWS total of 22.3 in. | Real |
| Grid load | NYISO WEST zone (Zone A) and NY total, MW | Real |
| Population, households, year built, share aged 65+ | Census ACS 2023 5-year estimates, by tract | Real |
| Street trees | City of Buffalo Tree Inventory (Open Data Buffalo), live trees only | Real (current inventory, not 2022) |
| Electricity-dependent medical equipment | HHS emPOWER, Medicare beneficiaries by ZIP, split to tracts by households | Real (current release, not 2022) |
| Overhead line share | None found | Placeholder (0.85 everywhere) |
| Outages, crews, repair times, indoor temperatures | Simulator | Simulated |

Census tracts are assigned to the nearest neighborhood center, so neighborhood boundaries are approximate. Full sources are in `data/sources.json`.

### Database (Tiger Cloud / TimescaleDB)

| Table | Contents |
|---|---|
| `weather_hourly`, `grid_load_hourly` | Real weather and NYISO load (hypertables) |
| `storm_summary_3h` | 3-hour storm summary (continuous aggregate) |
| `neighborhoods` | 13 neighborhoods and their attributes |
| `sim_runs`, `neighborhood_state`, `crew_events` | Simulated runs, per-neighborhood hourly state, and crew moves with the AI's explanations |
| `run_scoreboard` | Score per run (view) |

`queries.sql` has ready-made queries.

## Robustness and limitations

- **Seeds:** across 20 seeds with 8 crews, `rules` beat `largest_first` on cold person-hours in 20 of 20 (−35% on average) (`results/eval_seeds.md`). The AI has been run on one seed so far.
- **Crew count matters most:** with 12 or more crews, few homes ever get cold, so any policy does well. The AI's advantage shows up when crews are scarce.
- **Other storms:** we replayed 6 other real Buffalo storms (`data/storms_summary.md`). Only the 2022 blizzard produced cold homes in the simulation; the others scored 0 under every policy.
- **Calibration** (`calibrate.py`, `data/calibration.json`): we compared the shape over time of simulated outages with real NYISO lost load. **They do not match** (correlation −0.59). Simulated outages peak around Dec 24, about 2 days before real lost load peaks. Adjusting the one scalar we allowed (the failure intercept) never gave a positive correlation, so we kept −9.5. The likely cause is restoration speed: in reality outages piled up for days, while the simulator repairs them within hours. Lost load also reflects closed businesses and the driving ban, so this is a plausibility check, not validation.
- **Database:** the shared `neighborhoods` table may carry medical-device numbers from an earlier load. `data/neighborhoods.csv` holds the official values.

## Run it

Python setup:

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with `DATABASE_URL` (your Tiger Cloud connection string) and `CENSUS_API_KEY`. Set `ANTHROPIC_API_KEY` to run the AI.

Load the data:

```bash
python fetch_storm_data.py
python load_to_tigerdata.py
```

Run the simulation:

```bash
python simulator.py --crews 8 --seed 2                    # largest_first and rules
python run_llm.py --crews 8 --seed 2                      # AI dispatcher (API cost), resumes from cache
python run_llm.py --crews 8 --seed 2 --replay             # replay a saved AI run, no API calls
python eval_seeds.py                                      # 20 seeds x 4/8/12 crews, no API calls
python evaluate_storms.py                                 # all 7 storms, no API calls
```

Frontend: put `VITE_MAPBOX_TOKEN=...` in `frontend/.env.local`, then run:

```bash
python -m uvicorn server:app --port 8000
```

```bash
cd frontend && npm install && npm run dev
```
