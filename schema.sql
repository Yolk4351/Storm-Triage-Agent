-- Storm Triage Agent: database schema for Tiger Cloud (Postgres + TimescaleDB)
-- Safe to run more than once.

-- ---------------------------------------------------------------
-- Reference data (regular table)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS neighborhoods (
  neighborhood_id            TEXT PRIMARY KEY,      -- e.g. 'fruit-belt'
  name                       TEXT NOT NULL,
  lat                        DOUBLE PRECISION,
  lon                        DOUBLE PRECISION,
  population                 INT,
  households                 INT,
  median_year_built          INT,                   -- drives home cooling rate (tau)
  street_trees               INT,
  overhead_line_share        DOUBLE PRECISION,      -- 0..1
  medical_device_households  INT,
  age_65_plus_share          DOUBLE PRECISION,      -- 0..1
  critical_facilities        TEXT,                  -- "hospital;warming center"
  data_quality               TEXT DEFAULT 'estimate' -- 'real' | 'estimate' | 'simulated'
);

-- ---------------------------------------------------------------
-- Real observed data (time-series)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_hourly (
  time           TIMESTAMPTZ NOT NULL,
  location       TEXT NOT NULL DEFAULT 'buffalo-downtown',
  temp_f         DOUBLE PRECISION,
  feels_like_f   DOUBLE PRECISION,
  wind_mph       DOUBLE PRECISION,
  gust_mph       DOUBLE PRECISION,
  wind_dir_deg   DOUBLE PRECISION,
  snowfall_in    DOUBLE PRECISION,
  snow_depth_in  DOUBLE PRECISION,
  precip_in      DOUBLE PRECISION,
  source         TEXT DEFAULT 'open-meteo-era5',
  PRIMARY KEY (location, time)
);

CREATE TABLE IF NOT EXISTS grid_load_hourly (
  time     TIMESTAMPTZ NOT NULL,
  zone     TEXT NOT NULL,                 -- 'WEST' (Zone A) or 'NYISO_TOTAL'
  load_mw  DOUBLE PRECISION,
  source   TEXT DEFAULT 'nyiso-pal',
  PRIMARY KEY (zone, time)
);

-- ---------------------------------------------------------------
-- Simulation output (time-series), written by the simulator / agent
-- Each run is one strategy playing the same storm: 'largest_first', 'rules' or 'llm_agent'.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sim_runs (
  run_id      TEXT PRIMARY KEY,
  strategy    TEXT NOT NULL,              -- 'largest_first' | 'rules' | 'llm_agent'
  crews       INT,
  seed        INT,
  created_at  TIMESTAMPTZ DEFAULT now(),
  notes       TEXT
);

CREATE TABLE IF NOT EXISTS neighborhood_state (
  time             TIMESTAMPTZ NOT NULL,
  run_id           TEXT NOT NULL REFERENCES sim_runs(run_id) ON DELETE CASCADE,
  neighborhood_id  TEXT NOT NULL REFERENCES neighborhoods(neighborhood_id),
  outage_risk      DOUBLE PRECISION,      -- predicted probability 0..1
  households_out   INT,
  indoor_temp_f    DOUBLE PRECISION,      -- from the cooling model
  hours_to_danger  DOUBLE PRECISION,      -- until indoor < 50 F (NULL if power on)
  PRIMARY KEY (run_id, neighborhood_id, time)
);

CREATE TABLE IF NOT EXISTS crew_events (
  time             TIMESTAMPTZ NOT NULL,
  run_id           TEXT NOT NULL REFERENCES sim_runs(run_id) ON DELETE CASCADE,
  crew_id          TEXT NOT NULL,
  neighborhood_id  TEXT REFERENCES neighborhoods(neighborhood_id),
  action           TEXT NOT NULL,         -- 'dispatched' | 'arrived' | 'restored' | 'staged'
  reason           TEXT                   -- agent's plain-English explanation
);

CREATE INDEX IF NOT EXISTS crew_events_run_time ON crew_events (run_id, time DESC);

-- Headline metric: person-hours spent in homes below 50 F, per run.
-- (One row per neighborhood per hour; persons = households_out * avg household size 2.2)
CREATE OR REPLACE VIEW run_scoreboard AS
SELECT r.run_id,
       r.strategy,
       round(sum(CASE WHEN s.indoor_temp_f < 50 THEN s.households_out * 2.2 ELSE 0 END)::numeric)
         AS person_hours_below_50f,
       sum(s.households_out)                                       AS household_hours_out,
       sum(CASE WHEN s.households_out > 0 AND n.critical_facilities <> '' THEN 1 ELSE 0 END)
         AS critical_facility_hours_out,
       sum(CASE WHEN s.indoor_temp_f < 50
                THEN n.medical_device_households * s.households_out::float
                     / NULLIF(n.households, 0) ELSE 0 END)::int    AS medical_household_hours_at_risk
FROM sim_runs r
JOIN neighborhood_state s ON s.run_id = r.run_id
JOIN neighborhoods n      ON n.neighborhood_id = s.neighborhood_id
GROUP BY r.run_id, r.strategy;
