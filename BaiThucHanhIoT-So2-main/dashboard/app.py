"""
Dashboard Streamlit cho hệ thống IoT.

Chức năng:
    * Hiển thị real-time nhiệt độ, độ ẩm, ánh sáng từ bucket iot_raw
    * So sánh với dữ liệu đã tiền xử lý ở bucket iot_processed
    * Thống kê số điểm, outlier, thiết bị online/offline
    * Đo end-to-end latency (từ timestamp device → thời điểm ghi DB)
    * Auto-refresh mỗi N giây

Chạy:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from influxdb_client import InfluxDBClient


# ============================= Config ======================================
def load_config() -> dict:
    path = Path(os.getenv("CONFIG_PATH", "config/config.yaml"))
    if not path.exists():
        st.error(f"Không tìm thấy {path}")
        st.stop()
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


CFG = load_config()
INFLUX_URL = CFG["influx"]["url"]
INFLUX_TOKEN = CFG["influx"]["token"]
INFLUX_ORG = CFG["influx"]["org"]
BUCKET_RAW = CFG["influx"]["bucket_raw"]
BUCKET_PROC = CFG["influx"]["bucket_processed"]


# ============================= Flux queries ================================
Q_RAW = """
from(bucket: "{bucket}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "sensor_raw")
  |> filter(fn: (r) => r._field == "temperature"
                    or r._field == "humidity"
                    or r._field == "distance_cm"
                    or r._field == "e2e_latency_ms")
  |> pivot(rowKey: ["_time", "device_id"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: false)
"""

Q_PROC = """
from(bucket: "{bucket}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "sensor_processed")
  |> filter(fn: (r) => r._field == "temperature"
                    or r._field == "humidity"
                    or r._field == "distance_cm"
                    or r._field == "temperature_rollmean5"
                    or r._field == "humidity_rollmean5"
                    or r._field == "distance_cm_rollmean5"
                    or r._field == "temperature_is_outlier"
                    or r._field == "humidity_is_outlier"
                    or r._field == "distance_cm_is_outlier"
                    or r._field == "dew_point")
  |> pivot(rowKey: ["_time", "device_id"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: false)
"""

Q_LAST_SEEN = """
from(bucket: "{bucket}")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "sensor_raw" and r._field == "temperature")
  |> group(columns: ["device_id"])
  |> last()
  |> keep(columns: ["device_id", "_time"])
"""


def query_df(client: InfluxDBClient, flux: str) -> pd.DataFrame:
    tables = client.query_api().query_data_frame(flux)
    if isinstance(tables, list):
        tables = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    if tables.empty:
        return tables
    drop = [c for c in ("result", "table", "_start", "_stop", "_measurement") if c in tables.columns]
    if drop:
        tables = tables.drop(columns=drop)
    if "_time" in tables.columns:
        tables["_time"] = pd.to_datetime(tables["_time"], utc=True)
        tables = tables.sort_values("_time").reset_index(drop=True)
    return tables


# ============================= UI ==========================================
st.set_page_config(page_title="IoT Dashboard — BTH2", layout="wide", page_icon="📡")

st.title("📡 IoT Dashboard — Bài thực hành số 2")
st.caption("Thu thập · Lưu trữ · Tiền xử lý · Giám sát real-time")

with st.sidebar:
    st.header("Cấu hình hiển thị")
    minutes = st.slider("Khoảng thời gian (phút)", 1, 180, 60)
    refresh = st.slider("Auto-refresh (giây)", 0, 60, 0, help="0 = tắt")
    show_processed = st.checkbox("Hiển thị dữ liệu đã tiền xử lý", True)
    st.divider()
    st.caption(f"Influx URL: `{INFLUX_URL}`")
    st.caption(f"Bucket raw: `{BUCKET_RAW}`")
    st.caption(f"Bucket processed: `{BUCKET_PROC}`")

if refresh > 0:
    # Streamlit >= 1.27 có st.rerun; dùng meta refresh để nhẹ hơn
    st.markdown(f"<meta http-equiv='refresh' content='{refresh}'>", unsafe_allow_html=True)

client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, timeout=10_000)

# ----------- Query -----------
with st.spinner("Đang truy vấn InfluxDB…"):
    df_raw = query_df(client, Q_RAW.format(bucket=BUCKET_RAW, minutes=minutes))
    df_proc = query_df(client, Q_PROC.format(bucket=BUCKET_PROC, minutes=minutes)) if show_processed else pd.DataFrame()
    df_seen = query_df(client, Q_LAST_SEEN.format(bucket=BUCKET_RAW))

# ----------- Device status row -----------
st.subheader("🔌 Trạng thái thiết bị")
if df_seen.empty:
    st.warning("Chưa có thiết bị nào gửi dữ liệu trong 24h qua.")
else:
    cols = st.columns(min(4, len(df_seen)))
    now = datetime.now(timezone.utc)
    for i, (_, row) in enumerate(df_seen.iterrows()):
        age = (now - row["_time"]).total_seconds()
        online = age < 60
        icon = "🟢" if online else "🔴"
        with cols[i % len(cols)]:
            st.metric(
                f"{icon} {row['device_id']}",
                f"{'ONLINE' if online else 'OFFLINE'}",
                f"last seen {int(age)}s ago",
                delta_color="normal" if online else "inverse",
            )

# ----------- KPI row -----------
st.subheader("📈 Chỉ số tổng quan")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Số điểm (raw)", len(df_raw))
if not df_raw.empty and "temperature" in df_raw.columns:
    col2.metric("Nhiệt độ TB (°C)", f"{df_raw['temperature'].mean():.2f}")
if not df_raw.empty and "humidity" in df_raw.columns:
    col3.metric("Độ ẩm TB (%)", f"{df_raw['humidity'].mean():.2f}")
if not df_raw.empty and "e2e_latency_ms" in df_raw.columns:
    col4.metric("Latency TB (ms)", f"{df_raw['e2e_latency_ms'].mean():.1f}",
                f"p95: {df_raw['e2e_latency_ms'].quantile(0.95):.0f} ms")

# ----------- Charts -----------
st.subheader("🌡️ Biểu đồ cảm biến")
if df_raw.empty:
    st.info("Chưa có dữ liệu raw. Hãy chạy collector + ESP32 (hoặc trình giả lập).")
else:
    tabs = st.tabs(["Nhiệt độ", "Độ ẩm", "Khoảng cách", "Latency", "Bảng dữ liệu"])

    def _plot(field: str, label: str):
        pivot = df_raw.pivot_table(index="_time", columns="device_id", values=field, aggfunc="mean")
        st.line_chart(pivot, height=320, use_container_width=True)
        if show_processed and not df_proc.empty and f"{field}_rollmean5" in df_proc.columns:
            st.caption("Đường rolling-mean 5 cửa sổ (sau tiền xử lý)")
            pv2 = df_proc.pivot_table(index="_time", columns="device_id",
                                      values=f"{field}_rollmean5", aggfunc="mean")
            st.line_chart(pv2, height=200, use_container_width=True)
        flag = f"{field}_is_outlier"
        if show_processed and not df_proc.empty and flag in df_proc.columns:
            n_out = int(df_proc[flag].fillna(0).sum())
            if n_out > 0:
                st.warning(f"Phát hiện {n_out} điểm outlier ở {label} trong khoảng này")

    with tabs[0]:
        _plot("temperature", "nhiệt độ")
    with tabs[1]:
        _plot("humidity", "độ ẩm")
    with tabs[2]:
        _plot("distance_cm", "khoảng cách")
    with tabs[3]:
        if "e2e_latency_ms" in df_raw.columns:
            lat = df_raw.pivot_table(index="_time", columns="device_id",
                                     values="e2e_latency_ms", aggfunc="mean")
            st.line_chart(lat, height=280, use_container_width=True)
            desc = df_raw.groupby("device_id")["e2e_latency_ms"].describe(
                percentiles=[0.5, 0.9, 0.95, 0.99]
            )
            st.dataframe(desc)
    with tabs[4]:
        st.dataframe(df_raw.tail(200), use_container_width=True, height=400)

# ----------- Processed section -----------
if show_processed and not df_proc.empty:
    st.subheader("🧪 Dữ liệu sau tiền xử lý")
    with st.expander("Xem bảng dữ liệu đã xử lý"):
        st.dataframe(df_proc.tail(200), use_container_width=True, height=400)
    if "dew_point" in df_proc.columns:
        st.caption("Điểm sương (dew point) tính từ T + RH")
        dp = df_proc.pivot_table(index="_time", columns="device_id",
                                 values="dew_point", aggfunc="mean")
        st.line_chart(dp, height=240, use_container_width=True)

st.divider()
st.caption("© 2026 AnhAnh — PTIT · IoT và Ứng dụng (INT14149) · BTH2")
