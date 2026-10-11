"""
Tiền xử lý dữ liệu IoT:
    sensor_raw (bucket iot_raw)  --->  preprocess  --->  sensor_processed (bucket iot_processed)

Các bước (đúng yêu cầu đề bài):
    1. Đọc dữ liệu từ InfluxDB trong khoảng thời gian [--since, --until]
    2. Xử lý missing values (interpolation theo thời gian + ffill ngắn)
    3. Phát hiện outlier theo cả IQR và Z-score, đánh dấu + loại bỏ
    4. Resample theo cửa sổ thời gian (--window, mặc định 1 phút)
    5. Tạo đặc trưng: rolling mean (5 cửa sổ), delta (step-to-step),
       rate_of_change, humidity_dew_point xấp xỉ
    6. Chuẩn hóa: min-max và z-score
    7. Ghi vào measurement mới sensor_processed

Chạy:
    python preprocessing/preprocess.py --since -1h --window 1min
    python preprocessing/preprocess.py --since 2026-10-11T00:00:00Z \\
                                       --until 2026-10-11T06:00:00Z \\
                                       --window 1min
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yaml
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("preprocess")


# ============================= Config ======================================
def load_config(path: str = "config/config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ============================= Fetch =======================================
FLUX_READ = """
from(bucket: "{bucket}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "sensor_raw")
  |> filter(fn: (r) => r._field == "temperature"
                    or r._field == "humidity"
                    or r._field == "distance_cm")
  |> pivot(rowKey: ["_time", "device_id"], columnKey: ["_field"], valueColumn: "_value")
"""


def fetch(client: InfluxDBClient, bucket: str, start: str, stop: str) -> pd.DataFrame:
    q = FLUX_READ.format(bucket=bucket, start=start, stop=stop)
    log.info("Flux query: %s", q.replace("\n", " "))
    tables = client.query_api().query_data_frame(q)
    if isinstance(tables, list):
        tables = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    if tables.empty:
        return pd.DataFrame(columns=["_time", "device_id", "temperature", "humidity", "distance_cm"])

    cols = [c for c in ["_time", "device_id", "temperature", "humidity", "distance_cm"] if c in tables.columns]
    df = tables[cols].copy()
    df["_time"] = pd.to_datetime(df["_time"], utc=True)
    df = df.sort_values(["device_id", "_time"]).reset_index(drop=True)
    return df


# ============================= 2. Missing values ===========================
def handle_missing(df: pd.DataFrame, fields: Iterable[str]) -> pd.DataFrame:
    """Nội suy theo thời gian + ffill tối đa 3 bước; log tỷ lệ missing trước/sau."""
    out = df.copy()
    for f in fields:
        if f not in out.columns:
            continue
        before = out[f].isna().mean() * 100
        out[f] = (
            out.groupby("device_id", group_keys=False)[f]
            .apply(lambda s: s.interpolate(method="linear", limit=3, limit_direction="both"))
        )
        out[f] = out.groupby("device_id")[f].ffill(limit=3)
        after = out[f].isna().mean() * 100
        log.info("missing %s: %.2f%% -> %.2f%%", f, before, after)
    return out


# ============================= 3. Outlier ==================================
def detect_outliers_iqr(s: pd.Series, k: float = 1.5) -> pd.Series:
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return (s < lo) | (s > hi)


def detect_outliers_zscore(s: pd.Series, thr: float = 3.0) -> pd.Series:
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(False, index=s.index)
    return ((s - mu).abs() / sd) > thr


def tag_and_clip_outliers(df: pd.DataFrame, fields: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for f in fields:
        if f not in out.columns:
            continue
        iqr_mask = out.groupby("device_id")[f].transform(detect_outliers_iqr)
        z_mask = out.groupby("device_id")[f].transform(detect_outliers_zscore)
        mask = iqr_mask | z_mask
        out[f"{f}_is_outlier"] = mask.astype(int)
        log.info("outlier %s: %d / %d (%.2f%%) [IQR | Z]",
                 f, int(mask.sum()), len(mask), 100 * mask.mean())
        # thay outlier bằng NaN để resample mean bỏ qua
        out.loc[mask, f] = np.nan
    return out


# ============================= 4. Resample =================================
def resample(df: pd.DataFrame, window: str, fields: Iterable[str]) -> pd.DataFrame:
    if df.empty:
        return df

    def _res(g: pd.DataFrame) -> pd.DataFrame:
        g = g.set_index("_time")
        agg = {f: "mean" for f in fields if f in g.columns}
        # Giữ cờ outlier bằng OR
        for f in fields:
            flag = f"{f}_is_outlier"
            if flag in g.columns:
                agg[flag] = "max"
        r = g.resample(window).agg(agg)
        return r

    out = (
        df.groupby("device_id", group_keys=True)
        .apply(_res, include_groups=False)
        .reset_index()
    )
    return out


# ============================= 5. Feature engineering =======================
def engineer_features(df: pd.DataFrame, fields: Iterable[str], roll: int = 5) -> pd.DataFrame:
    out = df.copy()
    for f in fields:
        if f not in out.columns:
            continue
        g = out.groupby("device_id")[f]
        out[f"{f}_rollmean{roll}"] = g.transform(lambda s: s.rolling(roll, min_periods=1).mean())
        out[f"{f}_rollstd{roll}"] = g.transform(lambda s: s.rolling(roll, min_periods=1).std().fillna(0.0))
        out[f"{f}_delta"] = g.diff()
        out[f"{f}_roc"] = g.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # Dew point (Magnus) từ nhiệt độ + độ ẩm
    if "temperature" in out.columns and "humidity" in out.columns:
        a, b = 17.625, 243.04
        t = out["temperature"]
        rh = out["humidity"].clip(lower=1e-3)
        alpha = np.log(rh / 100.0) + (a * t) / (b + t)
        out["dew_point"] = (b * alpha) / (a - alpha)
    return out


# ============================= 6. Normalization =============================
def normalize(df: pd.DataFrame, fields: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for f in fields:
        if f not in out.columns:
            continue
        g = out.groupby("device_id")[f]
        mn = g.transform("min")
        mx = g.transform("max")
        rng = (mx - mn).replace(0, np.nan)
        out[f"{f}_minmax"] = ((out[f] - mn) / rng).fillna(0.0)

        mu = g.transform("mean")
        sd = g.transform("std").replace(0, np.nan)
        out[f"{f}_zscore"] = ((out[f] - mu) / sd).fillna(0.0)
    return out


# ============================= 7. Write back ================================
def write_processed(client: InfluxDBClient, bucket: str, org: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    write_api = client.write_api(write_options=SYNCHRONOUS)
    points: list[Point] = []
    numeric_cols = [c for c in df.columns if c not in ("_time", "device_id")]
    for _, row in df.iterrows():
        if pd.isna(row["_time"]):
            continue
        p = (
            Point("sensor_processed")
            .tag("device_id", str(row["device_id"]))
            .time(row["_time"].to_pydatetime(), write_precision=WritePrecision.MS)
        )
        has_field = False
        for c in numeric_cols:
            v = row[c]
            if pd.isna(v):
                continue
            try:
                p = p.field(c, float(v))
                has_field = True
            except (TypeError, ValueError):
                continue
        if has_field:
            points.append(p)
    if points:
        write_api.write(bucket=bucket, org=org, record=points)
    write_api.close()
    return len(points)


# ============================= Pipeline ====================================
FIELDS = ("temperature", "humidity", "distance_cm")


def pipeline(df: pd.DataFrame, window: str) -> pd.DataFrame:
    if df.empty:
        log.warning("Không có dữ liệu đầu vào")
        return df
    log.info("Đầu vào: %d dòng, %d thiết bị", len(df), df["device_id"].nunique())
    df = handle_missing(df, FIELDS)
    df = tag_and_clip_outliers(df, FIELDS)
    df = resample(df, window, FIELDS)
    df = df.dropna(subset=list(FIELDS), how="all")
    df = handle_missing(df, FIELDS)   # bù lại sau khi resample
    df = engineer_features(df, FIELDS)
    df = normalize(df, FIELDS)
    log.info("Đầu ra sau pipeline: %d dòng, %d cột", len(df), df.shape[1])
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="-1h", help="Flux time (ví dụ -1h, -24h, hoặc ISO)")
    ap.add_argument("--until", default="now()", help="Flux time (mặc định now())")
    ap.add_argument("--window", default="1min", help="Resample window: 30s, 1min, 5min…")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--export-csv", default=None, help="Đồng thời xuất CSV để dễ kiểm tra")
    args = ap.parse_args()

    cfg = load_config(args.config)
    url = cfg["influx"]["url"]
    token = cfg["influx"]["token"]
    org = cfg["influx"]["org"]
    bucket_raw = cfg["influx"]["bucket_raw"]
    bucket_proc = cfg["influx"]["bucket_processed"]

    with InfluxDBClient(url=url, token=token, org=org, timeout=20_000) as client:
        df_raw = fetch(client, bucket_raw, args.since, args.until)
        df_out = pipeline(df_raw, args.window)
        n = write_processed(client, bucket_proc, org, df_out)
        log.info("Đã ghi %d điểm sang bucket %s", n, bucket_proc)

    if args.export_csv:
        Path(args.export_csv).parent.mkdir(parents=True, exist_ok=True)
        df_out.to_csv(args.export_csv, index=False)
        log.info("Đã xuất CSV: %s", args.export_csv)


if __name__ == "__main__":
    main()
