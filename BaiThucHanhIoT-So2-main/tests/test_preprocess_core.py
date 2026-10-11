"""
Smoke test độc lập (không cần InfluxDB) cho các hàm xử lý trong preprocess.py.
Chạy:   python tests/test_preprocess_core.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from preprocessing.preprocess import (  # noqa: E402
    handle_missing,
    tag_and_clip_outliers,
    resample,
    engineer_features,
    normalize,
    FIELDS,
)


def make_df(n: int = 180) -> pd.DataFrame:
    idx = pd.date_range("2026-10-11", periods=n, freq="10s", tz="UTC")
    rng = np.random.default_rng(0)
    t = 28 + np.sin(np.linspace(0, 6.28, n)) + rng.normal(0, 0.3, n)
    h = 65 + np.cos(np.linspace(0, 6.28, n)) * 5 + rng.normal(0, 1, n)
    d = np.clip(120 + 40 * np.cos(np.linspace(0, 6.28, n)) + rng.normal(0, 4, n), 2, None)

    # Inject outlier và missing
    t[20] = 100
    h[40] = -10
    d[60] = 500
    t[[5, 15]] = np.nan
    h[[7, 50, 80]] = np.nan

    df = pd.DataFrame({"_time": idx, "device_id": "devA",
                       "temperature": t, "humidity": h, "distance_cm": d})
    return df


def main():
    df = make_df()
    print(f"Input rows: {len(df)}  missing t={df.temperature.isna().sum()}, "
          f"h={df.humidity.isna().sum()}")
    df = handle_missing(df, FIELDS)
    assert df["temperature"].isna().sum() == 0
    assert df["humidity"].isna().sum() == 0

    df = tag_and_clip_outliers(df, FIELDS)
    assert df["temperature_is_outlier"].sum() >= 1
    assert df["humidity_is_outlier"].sum() >= 1
    assert df["distance_cm_is_outlier"].sum() >= 1

    df = resample(df, "1min", FIELDS)
    assert len(df) > 0 and "temperature" in df.columns
    print(f"After resample: {len(df)} rows")

    df = handle_missing(df, FIELDS)
    df = engineer_features(df, FIELDS)
    for c in ("temperature_rollmean5", "humidity_delta", "distance_cm_roc", "dew_point"):
        assert c in df.columns, f"missing {c}"

    df = normalize(df, FIELDS)
    assert df["temperature_minmax"].between(0, 1).all()
    assert np.isfinite(df["humidity_zscore"]).all()

    print("ALL OK ✓")
    print(df.head(3).to_string())


if __name__ == "__main__":
    main()
