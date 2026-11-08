# Results across storms

Real hourly weather for each storm (raw, no snowfall scaling); simulated grid, outages, crews and indoor temperatures. 20 seeds per cell. Each cell: mean paired % change of rules (hand-built formula) vs largest_first (largest outage first) on the same seed (negative = better), and in how many seeds it was lower.

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

## rules vs largest_first, 4 crews

| Storm | Max gust | Min temp | person_hours_below_50f | medical_household_hours_at_risk | household_hours_out | peak_households_out |
|---|---|---|---|---|---|---|
| Christmas Blizzard 2022 | 73 mph | 4°F | -20.5% (20/20) | -21.5% (20/20) | +3.6% (2/20) | +3.0% (2/20) |
| January 2014 blizzard | 53 mph | -6°F | n/a (0 in both) | n/a (0 in both) | +0.1% (0/20) | +0.0% (0/20) |
| Bills playoff blizzard 2024 | 67 mph | 11°F | n/a (0 in both) | n/a (0 in both) | +0.1% (5/20) | +0.0% (1/20) |
| March 2017 windstorm | 60 mph | 33°F | n/a (0 in both) | n/a (0 in both) | -0.0% (1/20) | +0.0% (0/20) |
| January 2020 windstorm | 73 mph | 29°F | n/a (0 in both) | n/a (0 in both) | -0.1% (3/20) | +0.0% (0/20) |
| Christmas lake-effect 2001 | 39 mph | 19°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |
| January 2022 lake-effect | 47 mph | 13°F | n/a (0 in both) | n/a (0 in both) | +0.0% (0/20) | +0.0% (0/20) |

## rules vs largest_first, 8 crews

| Storm | Max gust | Min temp | person_hours_below_50f | medical_household_hours_at_risk | household_hours_out | peak_households_out |
|---|---|---|---|---|---|---|
| Christmas Blizzard 2022 | 73 mph | 4°F | -72.5% (13/20) | -73.3% (13/20) | +0.7% (10/20) | +0.8% (2/20) |
| January 2014 blizzard | 53 mph | -6°F | n/a (0 in both) | n/a (0 in both) | +0.1% (1/20) | +0.0% (0/20) |
| Bills playoff blizzard 2024 | 67 mph | 11°F | n/a (0 in both) | n/a (0 in both) | +0.0% (1/20) | +0.0% (0/20) |
| March 2017 windstorm | 60 mph | 33°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |
| January 2020 windstorm | 73 mph | 29°F | n/a (0 in both) | n/a (0 in both) | -0.0% (1/20) | +0.0% (0/20) |
| Christmas lake-effect 2001 | 39 mph | 19°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |
| January 2022 lake-effect | 47 mph | 13°F | n/a (0 in both) | n/a (0 in both) | +0.0% (0/20) | +0.0% (0/20) |

## rules vs largest_first, 12 crews

| Storm | Max gust | Min temp | person_hours_below_50f | medical_household_hours_at_risk | household_hours_out | peak_households_out |
|---|---|---|---|---|---|---|
| Christmas Blizzard 2022 | 73 mph | 4°F | n/a (0 in both) | n/a (0 in both) | -0.0% (5/20) | -0.4% (2/20) |
| January 2014 blizzard | 53 mph | -6°F | n/a (0 in both) | n/a (0 in both) | +0.1% (1/20) | +0.0% (0/20) |
| Bills playoff blizzard 2024 | 67 mph | 11°F | n/a (0 in both) | n/a (0 in both) | +0.0% (1/20) | +0.0% (0/20) |
| March 2017 windstorm | 60 mph | 33°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |
| January 2020 windstorm | 73 mph | 29°F | n/a (0 in both) | n/a (0 in both) | -0.0% (1/20) | +0.0% (0/20) |
| Christmas lake-effect 2001 | 39 mph | 19°F | n/a (0 in both) | n/a (0 in both) | -0.1% (1/20) | +0.0% (0/20) |
| January 2022 lake-effect | 47 mph | 13°F | n/a (0 in both) | n/a (0 in both) | +0.0% (0/20) | +0.0% (0/20) |