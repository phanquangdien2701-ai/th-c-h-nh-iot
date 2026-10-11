"""
Collector: Subscribe MQTT -> Validate -> Ghi InfluxDB 2.x.

Pipeline:
    MQTT broker  --[JSON]-->  Collector  --[Point]-->  InfluxDB (bucket: iot_raw)

Tính năng:
    * Validate payload (schema, range, timestamp hợp lệ)
    * Chống trùng lặp bằng (device_id, seq) với cache LRU trong RAM
    * Đo end-to-end latency = thời gian ghi DB - timestamp trên device
    * Metric gộp (points_in, points_written, points_dropped, invalid, dup) log định kỳ
    * Reconnect broker tự động, batch write có flush định kỳ
    * Cấu hình qua config.yaml hoặc biến môi trường (ENV ưu tiên hơn)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import yaml
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS, WriteOptions


# ============================= Logging =====================================
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
log = logging.getLogger("collector")


# ============================= Config ======================================
def load_config(path: str = "config/config.yaml") -> dict:
    """Đọc config.yaml và override bằng biến môi trường nếu có."""
    cfg: dict[str, Any] = {}
    cfg_path = Path(path)
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    def env_override(section: str, key: str, env: str, cast=str):
        v = os.getenv(env)
        if v is not None:
            cfg.setdefault(section, {})[key] = cast(v)

    env_override("mqtt", "host", "MQTT_HOST")
    env_override("mqtt", "port", "MQTT_PORT", int)
    env_override("mqtt", "username", "MQTT_USERNAME")
    env_override("mqtt", "password", "MQTT_PASSWORD")
    env_override("mqtt", "topic", "MQTT_TOPIC")
    env_override("influx", "url", "INFLUX_URL")
    env_override("influx", "token", "INFLUX_TOKEN")
    env_override("influx", "org", "INFLUX_ORG")
    env_override("influx", "bucket_raw", "INFLUX_BUCKET_RAW")
    return cfg


# ============================= Validation ==================================
# Giới hạn hợp lý cho cảm biến trong phòng
RANGES = {
    "temperature": (-40.0, 85.0),   # DHT22
    "humidity":    (0.0, 100.0),
    "distance_cm": (0.0, 450.0),    # HC-SR04 tối đa ~400 cm
    "light":       (0.0, 100_000.0),  # lux (giữ cho simulator)
}
REQUIRED_FIELDS = {"device_id", "timestamp", "data"}


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""


def validate(payload: dict) -> ValidationResult:
    if not isinstance(payload, dict):
        return ValidationResult(False, "payload is not an object")
    missing = REQUIRED_FIELDS - set(payload)
    if missing:
        return ValidationResult(False, f"missing fields: {missing}")
    if not isinstance(payload["data"], dict) or not payload["data"]:
        return ValidationResult(False, "data must be a non-empty object")

    # Timestamp: cho phép ISO-8601, lệch tối đa 1 ngày so với hiện tại
    try:
        ts = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception as e:
        return ValidationResult(False, f"invalid timestamp: {e}")
    now = datetime.now(tz=timezone.utc)
    if abs((now - ts).total_seconds()) > 86400:
        return ValidationResult(False, "timestamp drift > 1 day")

    # Giá trị cảm biến (nếu không null) phải nằm trong range
    for k, (lo, hi) in RANGES.items():
        v = payload["data"].get(k)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            return ValidationResult(False, f"{k} not numeric")
        if not (lo <= v <= hi):
            # Chú ý: vẫn ghi vào DB nhưng gắn tag quality=suspect — xem build_point.
            # Trả ok để không drop; preprocessing sẽ xử lý.
            payload.setdefault("_quality", {})[k] = "out_of_range"
    return ValidationResult(True)


# ============================= Point builder ===============================
def build_point(payload: dict, received_at: datetime) -> Point:
    """Chuyển payload JSON thành Point InfluxDB."""
    ts = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    latency_ms = (received_at - ts).total_seconds() * 1000.0
    quality = payload.get("_quality", {})

    p = (
        Point("sensor_raw")
        .tag("device_id", str(payload["device_id"]))
        .tag("location", str(payload.get("location", "unknown")))
        .time(ts, write_precision=WritePrecision.MS)
    )
    data = payload["data"]
    for key in ("temperature", "humidity", "distance_cm", "light"):
        v = data.get(key)
        if v is None:
            continue
        p = p.field(key, float(v))
        if key in quality:
            p = p.tag(f"q_{key}", quality[key])

    # Metadata
    if "seq" in payload:
        p = p.field("seq", int(payload["seq"]))
    if "rssi" in payload:
        p = p.field("rssi", int(payload["rssi"]))
    p = p.field("e2e_latency_ms", float(latency_ms))
    return p


# ============================= Dedup cache =================================
@dataclass
class DedupCache:
    """Nhớ (device_id, seq) gần nhất để chống trùng khi MQTT retry QoS1."""
    size: int = 10_000
    _seen: set[tuple[str, int]] = field(default_factory=set)
    _order: deque = field(default_factory=deque)

    def check(self, device_id: str, seq: int | None) -> bool:
        """Trả True nếu lần đầu thấy; False nếu đã có."""
        if seq is None:
            return True
        key = (device_id, int(seq))
        if key in self._seen:
            return False
        self._seen.add(key)
        self._order.append(key)
        if len(self._order) > self.size:
            old = self._order.popleft()
            self._seen.discard(old)
        return True


# ============================= Metrics =====================================
@dataclass
class Metrics:
    points_in: int = 0
    points_written: int = 0
    invalid: int = 0
    duplicates: int = 0
    last_report: float = field(default_factory=time.time)

    def tick_report(self, interval: float = 30.0):
        now = time.time()
        if now - self.last_report >= interval:
            log.info(
                "metrics: in=%d written=%d invalid=%d dup=%d (last %.0fs)",
                self.points_in, self.points_written, self.invalid, self.duplicates,
                now - self.last_report,
            )
            self.last_report = now


# ============================= Collector ===================================
class Collector:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.metrics = Metrics()
        self.dedup = DedupCache(size=cfg.get("collector", {}).get("dedup_cache", 10_000))

        # InfluxDB client + write API batch
        self.influx = InfluxDBClient(
            url=cfg["influx"]["url"],
            token=cfg["influx"]["token"],
            org=cfg["influx"]["org"],
            timeout=10_000,
        )
        self.bucket = cfg["influx"]["bucket_raw"]
        self.write_api = self.influx.write_api(
            write_options=WriteOptions(batch_size=100, flush_interval=1_000, jitter_interval=200)
        )

        # MQTT
        self.mqtt = mqtt.Client(client_id=f"collector-{os.getpid()}", clean_session=True)
        if cfg["mqtt"].get("username"):
            self.mqtt.username_pw_set(cfg["mqtt"]["username"], cfg["mqtt"].get("password"))
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_disconnect = self._on_disconnect
        self.mqtt.on_message = self._on_message
        self.mqtt.reconnect_delay_set(min_delay=1, max_delay=30)

        self._stop = False

    def _on_connect(self, client, _u, _f, rc):
        if rc == 0:
            topic = self.cfg["mqtt"]["topic"]
            client.subscribe(topic, qos=1)
            log.info("MQTT connected, subscribed topic=%s", topic)
        else:
            log.error("MQTT connect failed rc=%d", rc)

    def _on_disconnect(self, _c, _u, rc):
        log.warning("MQTT disconnected rc=%d, auto-reconnect …", rc)

    def _on_message(self, _c, _u, msg):
        self.metrics.points_in += 1
        received_at = datetime.now(tz=timezone.utc)
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            self.metrics.invalid += 1
            log.warning("drop invalid JSON on %s: %s", msg.topic, e)
            return

        vr = validate(payload)
        if not vr.ok:
            self.metrics.invalid += 1
            log.warning("drop invalid payload: %s | %.120s", vr.reason, msg.payload)
            return

        device_id = str(payload["device_id"])
        seq = payload.get("seq")
        if not self.dedup.check(device_id, seq):
            self.metrics.duplicates += 1
            return

        try:
            point = build_point(payload, received_at)
            self.write_api.write(bucket=self.bucket, record=point)
            self.metrics.points_written += 1
        except Exception as e:
            log.exception("influx write failed: %s", e)
        self.metrics.tick_report()

    def run(self):
        host = self.cfg["mqtt"]["host"]
        port = int(self.cfg["mqtt"].get("port", 1883))
        log.info("connecting MQTT %s:%d …", host, port)
        self.mqtt.connect(host, port, keepalive=30)

        def stop(*_):
            log.info("shutting down …")
            self._stop = True
            self.mqtt.loop_stop()
            self.mqtt.disconnect()
            try:
                self.write_api.close()
                self.influx.close()
            except Exception:
                pass
            sys.exit(0)

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

        self.mqtt.loop_forever()


def main():
    cfg = load_config(os.getenv("CONFIG_PATH", "config/config.yaml"))
    if not cfg.get("influx", {}).get("token"):
        log.error("Thiếu INFLUX_TOKEN — set trong config/config.yaml hoặc ENV")
        sys.exit(2)
    Collector(cfg).run()


if __name__ == "__main__":
    main()
