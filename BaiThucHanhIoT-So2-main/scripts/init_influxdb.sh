#!/usr/bin/env bash
# ============================================================================
#  Khởi tạo bucket iot_processed và retention policy
#  Chạy sau khi docker compose up.
# ============================================================================
set -euo pipefail

INFLUX_URL="${INFLUX_URL:-http://localhost:8086}"
INFLUX_TOKEN="${INFLUX_TOKEN:-my-super-secret-admin-token}"
INFLUX_ORG="${INFLUX_ORG:-ptit}"

echo "[init] Tạo bucket iot_processed (retention 90d) …"
docker exec iot-influxdb influx bucket create \
  --name iot_processed \
  --org "$INFLUX_ORG" \
  --retention 90d \
  --token "$INFLUX_TOKEN" || echo "(bucket có thể đã tồn tại)"

echo "[init] Cập nhật retention bucket iot_raw -> 30d …"
BUCKET_ID=$(docker exec iot-influxdb influx bucket list \
  --org "$INFLUX_ORG" --token "$INFLUX_TOKEN" \
  | awk '/iot_raw/ {print $1}')
if [[ -n "${BUCKET_ID:-}" ]]; then
  docker exec iot-influxdb influx bucket update \
    --id "$BUCKET_ID" --retention 30d --token "$INFLUX_TOKEN"
fi

echo "[init] Hoàn tất. Mở UI: $INFLUX_URL (user: admin / pass: adminpassword)"
