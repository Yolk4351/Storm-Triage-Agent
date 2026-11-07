"""
Download past winters of REAL Buffalo weather + NYISO WEST-zone load to train the
demand forecast. The Dec 2022 blizzard is deliberately left out so the model is
tested on a storm it has never seen.

    python fetch_training_data.py        # -> data/train_hourly.csv (takes a few minutes)
"""
import pandas as pd

from fetch_storm_data import OUT_DIR, fetch_nyiso_load, fetch_weather

# Winters before the blizzard (the storm starts Dec 22, 2022)
PERIODS = [
    ("2019-12-01", "2020-02-29"),
    ("2020-12-01", "2021-02-28"),
    ("2021-12-01", "2022-02-28"),
    ("2022-11-15", "2022-12-20"),
]


def main():
    OUT_DIR.mkdir(exist_ok=True)
    parts = []
    for start, end in PERIODS:
        print(f"{start} -> {end}: weather...", flush=True)
        weather = fetch_weather(start, end)
        print(f"{start} -> {end}: NYISO load...", flush=True)
        load = fetch_nyiso_load(start, end)
        part = weather.merge(load, on="time", how="inner").dropna(subset=["west_load_mw"])
        print(f"  {len(part)} hours", flush=True)
        parts.append(part)

    train = pd.concat(parts, ignore_index=True).drop_duplicates("time").sort_values("time")
    path = OUT_DIR / "train_hourly.csv"
    train.to_csv(path, index=False)
    print(f"\nSaved {len(train)} hours -> {path}")
    print(f"WEST load range: {train['west_load_mw'].min():.0f}-{train['west_load_mw'].max():.0f} MW")


if __name__ == "__main__":
    main()
