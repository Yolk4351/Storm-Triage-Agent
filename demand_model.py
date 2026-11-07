"""
Demand forecast: predicts hourly electricity load (MW) for NYISO's WEST zone
(Western NY, including Buffalo) from weather and the calendar.

Trained on REAL data from four earlier winters (data/train_hourly.csv), then tested
on the Dec 2022 blizzard week (data/storm_hourly.csv), which the model never saw.

    python demand_model.py      # train, test on the blizzard, save the model + forecast

Two results:
    1. Accuracy on normal winter weeks it never saw (Nov 15 - Dec 20, 2022), against a
       naive "same as this hour yesterday" forecast.
    2. During the blizzard the model predicts the load Buffalo SHOULD have drawn for that
       weather. Real load came in lower; the gap ("missing demand") is load that vanished
       because of outages and the driving ban. It's a real-data signal of how much of the
       grid went dark.

Outputs:
    models/demand_model.joblib          the trained model
    models/demand_model_metrics.json    accuracy on the blizzard vs a naive forecast
    data/storm_load_forecast.csv        hourly actual vs predicted load (for the dashboard)

Forecast horizon: up to 24 hours ahead (it uses the load at the same hour yesterday).
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
DATA, MODELS = HERE / "data", HERE / "models"
TZ = "America/New_York"
TARGET = "west_load_mw"
FEATURES = ["temp_f", "feels_like_f", "wind_mph", "snowfall_in", "temp_avg_24h", "temp_lag_3h",
            "hour", "dayofweek", "is_weekend", "is_holiday", "load_lag_24h"]


def load_csv(path):
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert(TZ)
    return df.sort_values("time").reset_index(drop=True)


def add_features(df):
    """Calendar + rolling features, computed separately for each unbroken stretch of hours."""
    df = df.copy()
    gap = df["time"].diff() != pd.Timedelta(hours=1)
    seg = gap.cumsum()
    g = df.groupby(seg)
    df["temp_avg_24h"] = g["temp_f"].transform(lambda s: s.rolling(24, min_periods=6).mean())
    df["temp_lag_3h"] = g["temp_f"].shift(3)
    df["load_lag_24h"] = g[TARGET].shift(24)

    local = df["time"].dt
    df["hour"], df["dayofweek"] = local.hour, local.dayofweek
    df["is_weekend"] = (df["dayofweek"] >= 5).astype(int)
    years = range(df["time"].dt.year.min() - 1, df["time"].dt.year.max() + 2)
    hol = set(USFederalHolidayCalendar().holidays(f"{years.start}-01-01", f"{years.stop}-12-31").date)
    hol |= {pd.Timestamp(y, 12, 24).date() for y in years} | {pd.Timestamp(y, 12, 31).date() for y in years}
    df["is_holiday"] = local.date.map(lambda d: d in hol).astype(int)
    return df


HOLDOUT_START = "2022-11-15"  # normal weeks held out to measure accuracy


def new_model():
    return HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=42)


def errors(pred, actual):
    err = pred - actual
    return {"mae_mw": round(float(err.abs().mean()), 1),
            "mape_pct": round(float((err.abs() / actual).mean() * 100), 2),
            "bias_mw": round(float(err.mean()), 1)}


def train():
    """Validate on held-out normal weeks, then retrain on all winters for the final model."""
    df = add_features(load_csv(DATA / "train_hourly.csv")).dropna(subset=[TARGET, "load_lag_24h"])
    hold = df["time"] >= pd.Timestamp(HOLDOUT_START, tz=TZ)
    check = new_model().fit(df.loc[~hold, FEATURES], df.loc[~hold, TARGET])
    te = df[hold]
    validation = {
        "test_set": f"Normal weeks {HOLDOUT_START} to 2022-12-20 (held out)",
        "test_hours": int(hold.sum()),
        "model": errors(pd.Series(check.predict(te[FEATURES]), index=te.index), te[TARGET]),
        "naive_same_hour_yesterday": errors(te["load_lag_24h"], te[TARGET]),
    }
    model = new_model().fit(df[FEATURES], df[TARGET])
    return model, len(df), validation


def evaluate(model):
    storm = add_features(load_csv(DATA / "storm_hourly.csv")).dropna(subset=[TARGET, "load_lag_24h"])
    storm["predicted_mw"] = model.predict(storm[FEATURES])
    storm["naive_mw"] = storm["load_lag_24h"]  # "same as this hour yesterday"

    storm["missing_demand_mw"] = storm["predicted_mw"] - storm[TARGET]
    storm["day"] = storm["time"].dt.date.astype(str)
    by_day = storm.groupby("day").agg(expected_mw=("predicted_mw", "mean"), actual_mw=(TARGET, "mean"),
                                      missing_mw=("missing_demand_mw", "mean")).round(0)
    metrics = {
        "test_set": "Dec 2022 Buffalo blizzard week (never seen in training)",
        "test_hours": len(storm),
        "avg_missing_demand_mw": round(float(storm["missing_demand_mw"].mean()), 1),
        "avg_missing_demand_pct": round(float((storm["missing_demand_mw"] / storm["predicted_mw"]).mean() * 100), 1),
        "by_day": by_day.reset_index().to_dict("records"),
    }
    out = storm[["time", TARGET, "predicted_mw", "missing_demand_mw", "naive_mw", "temp_f"]].rename(
        columns={TARGET: "actual_mw", "predicted_mw": "expected_mw"}).round(1)
    return metrics, out


def main():
    MODELS.mkdir(exist_ok=True)
    model, n, validation = train()
    storm_metrics, forecast = evaluate(model)
    metrics = {"train_hours": n, "validation": validation, "blizzard": storm_metrics}
    joblib.dump({"model": model, "features": FEATURES}, MODELS / "demand_model.joblib")
    (MODELS / "demand_model_metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    forecast.to_csv(DATA / "storm_load_forecast.csv", index=False)

    m, b = validation["model"], validation["naive_same_hour_yesterday"]
    print(f"Trained on {n:,} hours from 4 winters of real NYISO + weather data.\n")
    print(f"1) Accuracy on {validation['test_hours']} normal hours it never saw:")
    print(f"   {'Our model':30}{m['mape_pct']:>6}% avg error  ({m['mae_mw']} MW)")
    print(f"   {'Naive (same hour yesterday)':30}{b['mape_pct']:>6}% avg error  ({b['mae_mw']} MW)")
    print(f"\n2) Blizzard: load the weather says Buffalo should have drawn vs what it actually drew")
    print(f"   {'Day':12}{'Expected':>10}{'Actual':>10}{'Missing':>10}")
    for r in storm_metrics["by_day"]:
        print(f"   {r['day']:12}{r['expected_mw']:>7.0f} MW{r['actual_mw']:>7.0f} MW{r['missing_mw']:>7.0f} MW")
    print(f"   Average missing demand: {storm_metrics['avg_missing_demand_mw']} MW "
          f"({storm_metrics['avg_missing_demand_pct']}% of expected)")


if __name__ == "__main__":
    main()
