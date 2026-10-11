"""
Trình giả lập (simulator) thiết bị ESP32 khi không có phần cứng.

Chạy trên máy tính, publish JSON giống hệt firmware thật lên MQTT broker.
Dùng để demo / phát triển khi chưa cắm board.

    python esp32_sim.py --host localhost --device esp32-sim-01 --interval 2
"""

from __future__ import annotations

import argparse
import json
import math
import random
import signal
import sys
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt


VN_TZ = timezone(timedelta(hours=7))


def iso_now() -> str:
    return datetime.now(tz=VN_TZ).isoformat(timespec="seconds")


class SensorSim:
    """Mô phỏng dao động mượt theo chu kỳ ngày + nhiễu + đôi khi thả 1 outlier."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.t0 = time.time()
        self.seq = 0

    def _diurnal(self, phase: float, amp: float, base: float) -> float:
        # chu kỳ 60s để demo thấy rõ, trong thực tế là 86400s
        omega = 2 * math.pi / 60.0
        return base + amp * math.sin(omega * (time.time() - self.t0) + phase)

    def read(self) -> dict:
        self.seq += 1
        t = self._diurnal(0.0, 2.0, 28.0) + self.rng.gauss(0, 0.25)
        h = self._diurnal(math.pi, 10.0, 65.0) + self.rng.gauss(0, 1.0)
        # HC-SR04 giả lập: khoảng cách lúc gần (vật thể đi lại) 20..200 cm
        dist = max(2.0, self._diurnal(0.5, 60.0, 120.0) + self.rng.gauss(0, 5.0))

        # 2% xác suất thả outlier để dashboard có cái mà bắt
        if self.rng.random() < 0.02:
            t += self.rng.choice([-15, 15])
        if self.rng.random() < 0.01:
            h = -5 if self.rng.random() < 0.5 else 110
        if self.rng.random() < 0.02:
            dist = 500.0   # ngoài tầm → outlier
        # 1% xác suất missing (null)
        temp_val = None if self.rng.random() < 0.01 else round(t, 2)
        hum_val = None if self.rng.random() < 0.01 else round(h, 2)
        dist_val = None if self.rng.random() < 0.01 else round(dist, 2)

        return {
            "device_id": None,  # fill ngoài
            "location": "lab-ptit",
            "timestamp": iso_now(),
            "seq": self.seq,
            "uptime_s": int(time.time() - self.t0),
            "rssi": self.rng.randint(-80, -40),
            "data": {
                "temperature": temp_val,
                "humidity": hum_val,
                "distance_cm": dist_val,
            },
            "unit_temperature": "C",
            "unit_humidity": "%",
            "unit_distance": "cm",
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--device", default="esp32-sim-01")
    ap.add_argument("--interval", type=float, default=2.0, help="giây giữa mỗi lần publish")
    args = ap.parse_args()

    topic_tele = f"iot/{args.device}/telemetry"
    topic_stat = f"iot/{args.device}/status"
    topic_cfg = f"iot/{args.device}/config"

    client = mqtt.Client(client_id=f"{args.device}-sim", clean_session=True)
    if args.user:
        client.username_pw_set(args.user, args.password)

    # LWT giống firmware
    client.will_set(topic_stat, json.dumps({"status": "offline"}), qos=1, retain=True)

    interval = args.interval

    def on_connect(c, _u, _f, rc):
        print(f"[MQTT] connected rc={rc}")
        c.publish(topic_stat, json.dumps({"status": "online"}), qos=1, retain=True)
        c.subscribe(topic_cfg, qos=1)

    def on_message(_c, _u, msg):
        nonlocal interval
        try:
            cfg = json.loads(msg.payload)
            if "interval_ms" in cfg:
                interval = max(0.5, int(cfg["interval_ms"]) / 1000.0)
                print(f"[CFG] interval = {interval}s")
        except Exception as e:
            print(f"[CFG] bad payload: {e}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    sim = SensorSim()

    def stop(*_):
        client.publish(topic_stat, json.dumps({"status": "offline"}), qos=1, retain=True)
        client.loop_stop()
        client.disconnect()
        print("\n[SIM] stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(f"[SIM] publishing to {topic_tele} every {interval}s")
    while True:
        payload = sim.read()
        payload["device_id"] = args.device
        client.publish(topic_tele, json.dumps(payload), qos=1, retain=False)
        print(f"  seq={payload['seq']} t={payload['data']['temperature']} "
              f"h={payload['data']['humidity']} dist={payload['data']['distance_cm']}")
        time.sleep(interval)


if __name__ == "__main__":
    main()