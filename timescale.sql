-- TimescaleDB features. Applied automatically by load_to_tigerdata.py when the
-- extension is available (it is on every Tiger Cloud service).

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Hypertables: automatic time partitioning for every time-series table
SELECT create_hypertable('weather_hourly',     by_range('time', INTERVAL '7 days'), if_not_exists => TRUE, migrate_data => TRUE);
SELECT create_hypertable('grid_load_hourly',   by_range('time', INTERVAL '7 days'), if_not_exists => TRUE, migrate_data => TRUE);
SELECT create_hypertable('neighborhood_state', by_range('time', INTERVAL '1 day'),  if_not_exists => TRUE, migrate_data => TRUE);
SELECT create_hypertable('crew_events',        by_range('time', INTERVAL '1 day'),  if_not_exists => TRUE, migrate_data => TRUE);

-- Continuous aggregate: 3-hour storm summary the agent can query cheaply
-- ("how bad were the next 6 hours?", "when did the wind peak?")
CREATE MATERIALIZED VIEW IF NOT EXISTS storm_summary_3h
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '3 hours', time) AS bucket,
       location,
       max(gust_mph)     AS max_gust_mph,
       min(temp_f)       AS min_temp_f,
       min(feels_like_f) AS min_feels_like_f,
       sum(snowfall_in)  AS snowfall_in
FROM weather_hourly
GROUP BY bucket, location
WITH NO DATA;
