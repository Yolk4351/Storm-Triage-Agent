# Robustness across seeds

Window 2022-12-23 00:00 to 2022-12-27 00:00; 20 seeds per crew count. Real weather and neighborhood data; outages, crews and indoor temperatures are simulated. Lower is better for every metric. 'Rules better in' counts seeds where rules scored strictly lower than largest_first on the same storm.

| Crews | Metric | largest_first (mean ± sd) | rules (mean ± sd) | Change | Rules better in |
|---|---|---|---|---|---|
| 4 | person_hours_below_50f | 1,591,666 ± 490,413 | 1,410,769 ± 456,330 | -11% | 20/20 |
| 4 | medical_household_hours_at_risk | 14,092 ± 4,274 | 12,048 ± 3,795 | -15% | 20/20 |
| 4 | critical_facility_hours_dark | 87 ± 53 | 64 ± 41 | -27% | 16/20 (2 ties) |
| 4 | household_hours_out | 1,303,798 ± 291,672 | 1,316,341 ± 282,102 | +1% | 8/20 |
| 4 | peak_households_out | 30,528 ± 4,964 | 30,906 ± 4,797 | +1% | 7/20 |
| 8 | person_hours_below_50f | 274,855 ± 160,668 | 178,965 ± 120,391 | -35% | 20/20 |
| 8 | medical_household_hours_at_risk | 2,627 ± 1,540 | 1,565 ± 1,132 | -40% | 20/20 |
| 8 | critical_facility_hours_dark | 37 ± 25 | 31 ± 21 | -17% | 11/20 (2 ties) |
| 8 | household_hours_out | 598,566 ± 147,212 | 617,947 ± 148,212 | +3% | 4/20 |
| 8 | peak_households_out | 22,493 ± 4,455 | 22,850 ± 4,498 | +2% | 5/20 (8 ties) |
| 12 | person_hours_below_50f | 21,755 ± 33,287 | 8,025 ± 18,742 | -63% | 11/20 (9 ties) |
| 12 | medical_household_hours_at_risk | 218 ± 345 | 74 ± 194 | -66% | 11/20 (9 ties) |
| 12 | critical_facility_hours_dark | 24 ± 16 | 23 ± 14 | -5% | 10/20 (6 ties) |
| 12 | household_hours_out | 402,134 ± 73,890 | 402,733 ± 77,459 | +0% | 10/20 (1 ties) |
| 12 | peak_households_out | 18,280 ± 3,545 | 18,215 ± 3,580 | -0% | 3/20 (14 ties) |
