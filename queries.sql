-- Useful queries for the Storm Triage team (run in Tiger Cloud's SQL editor or psql).
-- The agent can call these as tools.

-- 1. The worst hours of the storm
SELECT time AT TIME ZONE 'America/New_York' AS local_time, gust_mph, temp_f, feels_like_f, snowfall_in
FROM weather_hourly
ORDER BY gust_mph DESC
LIMIT 10;

-- 2. 3-hour storm summary (continuous aggregate)
SELECT bucket AT TIME ZONE 'America/New_York' AS starts, max_gust_mph, min_temp_f, snowfall_in
FROM storm_summary_3h
ORDER BY bucket;

-- 3. Weather + grid load side by side: does Western NY load DROP when the wind peaks?
--    A sudden drop during the worst hours suggests customers losing power.
SELECT w.time AT TIME ZONE 'America/New_York' AS local_time,
       w.gust_mph,
       w.temp_f,
       g.load_mw AS west_load_mw,
       round((g.load_mw - lag(g.load_mw, 24) OVER (ORDER BY w.time))::numeric, 1)
         AS change_vs_same_hour_yesterday
FROM weather_hourly w
JOIN grid_load_hourly g ON g.time = w.time AND g.zone = 'WEST'
ORDER BY w.time;

-- 4. Forecast tool for the agent: conditions over the next N hours from a given sim time
SELECT max(gust_mph) AS max_gust, min(temp_f) AS min_temp, sum(snowfall_in) AS snow_in
FROM weather_hourly
WHERE time >  '2022-12-23 10:00-05'
  AND time <= '2022-12-23 10:00-05'::timestamptz + INTERVAL '6 hours';

-- 5. Live city state at one simulated hour, most urgent first
SELECT n.name, s.households_out, round(s.indoor_temp_f::numeric, 1) AS indoor_f,
       round(s.hours_to_danger::numeric, 1) AS hours_to_danger, n.critical_facilities
FROM neighborhood_state s
JOIN neighborhoods n USING (neighborhood_id)
WHERE s.run_id = 'agent-1' AND s.time = '2022-12-23 18:00-05'
  AND s.households_out > 0
ORDER BY s.hours_to_danger NULLS LAST;

-- 6. The demo scoreboard: baseline vs agent
SELECT * FROM run_scoreboard ORDER BY strategy;

-- 7. Indoor temperature over time for one neighborhood, both strategies (for charts)
SELECT time_bucket(INTERVAL '1 hour', s.time) AS hour, r.strategy, avg(s.indoor_temp_f) AS indoor_f
FROM neighborhood_state s
JOIN sim_runs r USING (run_id)
WHERE s.neighborhood_id = 'fruit-belt'
GROUP BY hour, r.strategy
ORDER BY hour;
