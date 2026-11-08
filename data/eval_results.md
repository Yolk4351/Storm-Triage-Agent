# Evaluation: 2022-12-23 00:00 to 2022-12-27 00:00

Mean ± standard deviation across seeds (n = number of seeds). Lower is better for every metric.

## 4 crews

| policy | n | person_hours_below_50f | medical_household_hours_at_risk | critical_facility_hours_dark | household_hours_out | peak_households_out | critical_area_hours_any_outage |
|---|---|---|---|---|---|---|---|
| largest_first | 20 | 3,750,705 ± 618,454 | 35,106 ± 5,887 | 146 ± 54 | 2,515,947 ± 343,950 | 46,208 ± 4,654 | 280 ± 19 |
| rules | 20 | 3,616,273 ± 582,502 | 33,200 ± 5,516 | 107 ± 46 | 2,565,097 ± 327,230 | 46,831 ± 4,363 | 295 ± 28 |

## 8 crews

| policy | n | person_hours_below_50f | medical_household_hours_at_risk | critical_facility_hours_dark | household_hours_out | peak_households_out | critical_area_hours_any_outage |
|---|---|---|---|---|---|---|---|
| largest_first | 20 | 1,372,719 ± 395,581 | 12,921 ± 3,825 | 80 ± 42 | 1,392,655 ± 251,392 | 38,108 ± 4,649 | 205 ± 24 |
| rules | 20 | 1,173,284 ± 358,584 | 10,791 ± 3,383 | 59 ± 27 | 1,410,209 ± 252,618 | 38,629 ± 4,918 | 218 ± 26 |
| llm_agent | 1 | 629,435 ± 0 | 6,416 ± 0 | 37 ± 0 | 1,123,367 ± 0 | 31,166 ± 0 | 239 ± 0 |
| largest_first@llm_agent-seeds | 1 | 849,695 ± 0 | 8,390 ± 0 | 49 ± 0 | 1,087,972 ± 0 | 31,994 ± 0 | 203 ± 0 |
| rules@llm_agent-seeds | 1 | 698,722 ± 0 | 6,785 ± 0 | 32 ± 0 | 1,089,808 ± 0 | 29,770 ± 0 | 214 ± 0 |

## 12 crews

| policy | n | person_hours_below_50f | medical_household_hours_at_risk | critical_facility_hours_dark | household_hours_out | peak_households_out | critical_area_hours_any_outage |
|---|---|---|---|---|---|---|---|
| largest_first | 20 | 489,783 ± 211,749 | 4,696 ± 2,017 | 52 ± 27 | 941,768 ± 168,829 | 33,342 ± 4,837 | 172 ± 22 |
| rules | 20 | 373,452 ± 181,308 | 3,455 ± 1,698 | 44 ± 21 | 950,598 ± 177,505 | 33,177 ± 4,968 | 180 ± 26 |
