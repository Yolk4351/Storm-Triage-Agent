# Results across storms

Real hourly weather for each storm (raw, no snowfall scaling); simulated grid, outages, crews and indoor temperatures. 20 seeds per cell. Each cell: mean paired % change of agent (rules formula) vs baseline (largest outage first) on the same seed (negative = better), and in how many seeds it was lower.

## Storms

| storm_id | storm | hours | max_gust_mph | hours_gust_50plus | min_temp_f | model_snow_in |
|---|---|---|---|---|---|---|
| dec-2022-blizzard | Christmas Blizzard 2022 | 96 | 73 | 37 | 4 | 9.4 |
| jan-2014-blizzard | January 2014 blizzard | 72 | 53 | 6 | -6 | 1.2 |
| jan-2024-blizzard | Bills playoff blizzard 2024 | 96 | 67 | 22 | 11 | 5.0 |
| mar-2017-windstorm | March 2017 windstorm | 48 | 60 | 8 | 33 | 0.0 |
| jan-2020-windstorm | January 2020 windstorm | 48 | 73 | 8 | 29 | 0.0 |
| dec-2001-lake-effect | Christmas lake-effect 2001 | 120 | 39 | 0 | 19 | 5.8 |
| jan-2022-lake-effect | January 2022 lake-effect | 48 | 47 | 0 | 13 | 1.9 |

## agent vs baseline, 4 crews

| Storm | Max gust | Min temp | person_hours_below_50f | medical_household_hours_at_risk | household_hours_out | peak_households_out |
|---|---|---|---|---|---|---|
| Christmas Blizzard 2022 | 73 mph | 4°F | -4.4% (17/20) | -6.4% (19/20) | +4.3% (4/20) | +3.2% (4/20) |
| January 2014 blizzard | 53 mph | -6°F | -72.7% (2/20) | -70.6% (2/20) | +0.1% (1/20) | +0.0% (0/20) |
| Bills playoff blizzard 2024 | 67 mph | 11°F | -73.3% (10/20) | -73.0% (10/20) | +1.3% (2/20) | +0.0% (0/20) |
| March 2017 windstorm | 60 mph | 33°F | n/a (0 in both) | n/a (0 in both) | -0.3% (6/20) | +0.0% (0/20) |
| January 2020 windstorm | 73 mph | 29°F | n/a (0 in both) | n/a (0 in both) | -0.0% (4/20) | +0.0% (0/20) |
| Christmas lake-effect 2001 | 39 mph | 19°F | n/a (0 in both) | n/a (0 in both) | +0.1% (0/20) | +0.0% (0/20) |
| January 2022 lake-effect | 47 mph | 13°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |

## agent vs baseline, 8 crews

| Storm | Max gust | Min temp | person_hours_below_50f | medical_household_hours_at_risk | household_hours_out | peak_households_out |
|---|---|---|---|---|---|---|
| Christmas Blizzard 2022 | 73 mph | 4°F | -20.1% (20/20) | -21.9% (20/20) | +4.4% (2/20) | +1.9% (6/20) |
| January 2014 blizzard | 53 mph | -6°F | n/a (0 in both) | n/a (0 in both) | +0.1% (0/20) | +0.0% (0/20) |
| Bills playoff blizzard 2024 | 67 mph | 11°F | n/a (0 in both) | n/a (0 in both) | +0.1% (1/20) | -0.2% (1/20) |
| March 2017 windstorm | 60 mph | 33°F | n/a (0 in both) | n/a (0 in both) | -0.2% (3/20) | +0.0% (0/20) |
| January 2020 windstorm | 73 mph | 29°F | n/a (0 in both) | n/a (0 in both) | -0.2% (4/20) | +0.0% (0/20) |
| Christmas lake-effect 2001 | 39 mph | 19°F | n/a (0 in both) | n/a (0 in both) | +0.1% (0/20) | +0.0% (0/20) |
| January 2022 lake-effect | 47 mph | 13°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |

## agent vs baseline, 12 crews

| Storm | Max gust | Min temp | person_hours_below_50f | medical_household_hours_at_risk | household_hours_out | peak_households_out |
|---|---|---|---|---|---|---|
| Christmas Blizzard 2022 | 73 mph | 4°F | -66.0% (19/20) | -67.8% (19/20) | +0.7% (7/20) | -0.4% (5/20) |
| January 2014 blizzard | 53 mph | -6°F | n/a (0 in both) | n/a (0 in both) | +0.1% (0/20) | +0.0% (0/20) |
| Bills playoff blizzard 2024 | 67 mph | 11°F | n/a (0 in both) | n/a (0 in both) | -0.0% (2/20) | -0.2% (1/20) |
| March 2017 windstorm | 60 mph | 33°F | n/a (0 in both) | n/a (0 in both) | -0.1% (2/20) | +0.0% (0/20) |
| January 2020 windstorm | 73 mph | 29°F | n/a (0 in both) | n/a (0 in both) | +0.1% (0/20) | +0.0% (0/20) |
| Christmas lake-effect 2001 | 39 mph | 19°F | n/a (0 in both) | n/a (0 in both) | +0.1% (0/20) | +0.0% (0/20) |
| January 2022 lake-effect | 47 mph | 13°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |