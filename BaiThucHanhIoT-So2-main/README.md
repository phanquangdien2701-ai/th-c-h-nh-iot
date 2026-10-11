# BTH2 — Thu thập, Lưu trữ và Tiền xử lý Dữ liệu IoT

**Học phần:** IoT và Ứng dụng (INT14149)
**Sinh viên:** AnhAnh
**Mã nguồn:** https://github.com/<your-handle>/iot-lab2

> Workflow khuyến nghị: **Wokwi** (giả lập ESP32) → **broker HiveMQ public** → **collector Python**
> → **InfluxDB Cloud (free)** → **Streamlit dashboard** local. Không cần Docker, không cần
> quyền admin, chạy được trên cả máy trường.

---

## 1. Kiến trúc hệ thống

```
 ┌──────────────┐  MQTT JSON (QoS 1, LWT)   ┌───────────────────┐
 │ ESP32 Wokwi  │ ─────────────────────────▶│ broker.hivemq.com │
 │ DHT22+HC-SR04│      v1/devices/me/*      │   (public, 1883)  │
 └──────┬───────┘ ────────┐                 └─────────┬─────────┘
        │        thingsboard.cloud:1883              │ subscribe
        │        (song song, giữ dashboard Bài 1)    │ anhanh/ptit/iot/+/telemetry
        ▼                                            ▼
 ┌───────────────┐                            ┌──────────────────┐
 │  ThingsBoard  │                            │  Collector (PC)  │
 │   dashboard   │                            │ mqtt_to_influx.py│
 └───────────────┘                            └────────┬─────────┘
                                                       │ HTTPS
                                                       ▼
                                        ┌─────────────────────────┐
                                        │ InfluxDB Cloud (free)   │
                                        │  bucket iot_raw         │
                                        │  bucket iot_processed   │
                                        └───────┬─────────────────┘
                                                │
                                 ┌──────────────┴──────────────────┐
                                 ▼                                 ▼
                        preprocess.py                      dashboard/app.py
                       (outlier/resample/                 (Streamlit, port 8501)
                        features/normalize)
```

Firmware trên Wokwi **publish song song 2 nơi**:
- `thingsboard.cloud` — kênh của Bài 1 (có thể tắt bằng `#define ENABLE_THINGSBOARD 0`).
- `broker.hivemq.com` — JSON đầy đủ schema Bài 2 cho collector local nhận và ghi vào InfluxDB.

## 2. Cấu trúc dự án

```
iot-lab2/
├── firmware/
│   ├── esp32_sensor.ino       # Bản dùng board thật (local Mosquitto)
│   ├── esp32_sim.py           # Simulator Python — không cần Wokwi/board
│   └── wokwi/                 # Project Wokwi (ưu tiên)
│       ├── sketch.ino
│       ├── diagram.json
│       ├── libraries.txt
│       └── README.md
├── collector/
│   └── mqtt_to_influx.py      # Subscribe MQTT → validate → ghi InfluxDB
├── preprocessing/
│   └── preprocess.py          # Làm sạch, outlier, resample, feature, chuẩn hoá
├── dashboard/
│   └── app.py                 # Streamlit dashboard
├── config/
│   ├── config.yaml            # Config chính (dùng khi chạy không set env)
│   ├── config.wokwi.yaml      # Config khi dùng Wokwi (broker public)
│   └── docker-compose.yml     # (Tuỳ chọn) stack local nếu có Docker
├── scripts/
│   ├── verify_influx.py       # Chẩn đoán kết nối InfluxDB
│   └── init_influxdb.sh       # (Tuỳ chọn) init bucket khi dùng Docker
├── tests/
│   └── test_preprocess_core.py # Smoke test pipeline tiền xử lý
├── docs/
│   └── BaoCao_BTH2.docx       # Báo cáo (có khung chèn ảnh demo)
├── requirements.txt
└── README.md
```

## 3. Chuẩn bị môi trường

### 3.1. Cài Python ≥ 3.10
Tải tại https://www.python.org/downloads/ (Windows tick "Add Python to PATH").
Kiểm tra: `python --version`.

### 3.2. Clone dự án và tạo venv

```bash
# Clone từ GitHub
git clone https://github.com/<your-handle>/iot-lab2.git
cd iot-lab2

# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

> PowerShell báo "cannot be loaded because running scripts is disabled":
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` rồi activate lại.

### 3.3. Verify tiền xử lý chạy được (không cần Influx)

```bash
python tests/test_preprocess_core.py
```
Phải thấy `ALL OK ✓`.

## 4. Dựng InfluxDB Cloud (free, không cần cài gì)

1. Đăng ký tại <https://cloud2.influxdata.com/signup> → chọn **AWS** / region **Singapore** → **Free Plan**.
2. Tạo 2 bucket: **Load Data → Buckets → Create Bucket**:
   - `iot_raw` (retention 30 ngày)
   - `iot_processed` (retention 30 ngày)
3. Tạo token: **Load Data → API Tokens → Generate API Token → All Access API Token**. Copy ngay vì chỉ hiện 1 lần.
4. Lấy URL + Org ID: trong URL browser khi đăng nhập, URL dạng
   `https://xxx-x-x.aws.cloud2.influxdata.com/orgs/<ORG_ID>`. Giữ phần gốc `https://xxx.cloud2.influxdata.com` và ORG ID riêng.

**Điền vào `config/config.yaml` VÀ `config/config.wokwi.yaml`** (cả 2):
```yaml
influx:
  url: "https://us-east-1-1.aws.cloud2.influxdata.com"   # URL gốc của bạn
  org: "067e14c4612da0fa"                                 # ORG ID
  token: "paste_token_cua_ban"
  bucket_raw: "iot_raw"
  bucket_processed: "iot_processed"
```

Kiểm tra:
```bash
python scripts/verify_influx.py
```
Phải thấy `buckets names: ['iot_processed', 'iot_raw', ...]`.

## 5. Chạy pipeline

### 5.1. Dựng project Wokwi

1. Vào https://wokwi.com → **New Project** → **ESP32** → **Blank**.
2. Dán nội dung `firmware/wokwi/diagram.json` vào tab **diagram.json**.
3. Dán nội dung `firmware/wokwi/sketch.ino` vào tab **sketch.ino**.
4. **Library Manager** → thêm:
   - `PubSubClient` (Nick O'Leary)
   - `DHT ESP` (beegee_tokyo)
   - `ArduinoJson` v6.x
5. Mở `sketch.ino`, chỉnh **TOPIC_PREFIX** cho khớp `topic` trong `config.wokwi.yaml`:
   ```cpp
   const char* TOPIC_PREFIX = "anhanh/ptit/iot";
   ```
   > ⚠️ Nên thay bằng chuỗi riêng (ví dụ `b23dccn183/iot`) để không đụng người khác trên broker public. Nhớ cập nhật đồng thời ở `config/config.wokwi.yaml`.
6. Bấm **▶ Start Simulation**. Serial Monitor sẽ in `[BTH2 PUB OK] seq=X` mỗi 5 giây.

### 5.2. Chạy collector

Mở một terminal mới trong thư mục dự án, activate venv, rồi:
```bash
python collector/mqtt_to_influx.py
```
Log mong đợi:
```
connecting MQTT broker.hivemq.com:1883 …
MQTT connected, subscribed topic=anhanh/ptit/iot/+/telemetry
metrics: in=X written=X invalid=0 dup=0 (last 30s)
```

> Nếu bạn cố ý giữ `config.yaml` dùng local Mosquitto (trường hợp có board thật), thì chạy collector cho Wokwi bằng cách set biến môi trường:
> - PowerShell: `$env:CONFIG_PATH = "config/config.wokwi.yaml"; python collector/mqtt_to_influx.py`
> - Bash: `CONFIG_PATH=config/config.wokwi.yaml python collector/mqtt_to_influx.py`

### 5.3. Chạy tiền xử lý

Đợi collector tích đủ ~10-15 phút data, rồi:
```bash
python preprocessing/preprocess.py --since=-1h --window=1min --export-csv=exports/processed.csv
```
Output:
```
Đầu vào: 180 dòng, 1 thiết bị
missing temperature: 0.5% -> 0.00%
outlier temperature: 2 / 180 (1.11%) [IQR | Z]
...
Đã ghi 60 điểm sang bucket iot_processed
Đã xuất CSV: exports/processed.csv
```
Chạy định kỳ 5 phút bằng Task Scheduler / cron:
```
*/5 * * * * cd /path/to/iot-lab2 && .venv/bin/python preprocessing/preprocess.py --since=-10m --window=1min
```

### 5.4. Mở dashboard

Mở một terminal mới trong thư mục dự án, activate venv:
```bash
streamlit run dashboard/app.py
```
Browser tự mở <http://localhost:8501>. Dashboard có:
- Trạng thái thiết bị (ONLINE/OFFLINE theo thời gian ghi gần nhất).
- 4 KPI: số điểm, nhiệt độ TB, độ ẩm TB, latency TB + p95.
- 5 tab: Nhiệt độ / Độ ẩm / Khoảng cách / Latency / Bảng dữ liệu.
- Phần "Dữ liệu sau tiền xử lý" với dew_point.

Sidebar: slider khung thời gian + auto-refresh (0 = tắt).

### 5.5. (Tuỳ chọn) Chạy simulator Python thay Wokwi

Khi không mở được Wokwi, có thể bơm data bằng simulator (có sẵn outlier + missing để demo):
```bash
python firmware/esp32_sim.py --host broker.hivemq.com --device esp32-sim-01 --interval 2
```

## 6. Định dạng JSON thiết bị publish
Topic: `<TOPIC_PREFIX>/<device_id>/telemetry` (ví dụ `anhanh/ptit/iot/esp32-wokwi-01/telemetry`)
```json
{
  "device_id": "esp32-wokwi-01",
  "location": "wokwi-lab",
  "timestamp": "2026-10-11T08:12:34+07:00",
  "seq": 42,
  "uptime_s": 325,
  "rssi": -58,
  "data": {
    "temperature": 28.7,
    "humidity": 65.4,
    "distance_cm": 152.3
  },
  "unit_temperature": "C",
  "unit_humidity": "%",
  "unit_distance": "cm"
}
```
Thiết bị cũng publish `<TOPIC_PREFIX>/<id>/status` dạng `{"status":"online"|"offline"}`
(retained + LWT) để dashboard biết trạng thái.

## 7. Schema InfluxDB

### bucket `iot_raw` (retention 30 ngày)
| measurement   | tags                              | fields                                                                        |
|---------------|-----------------------------------|-------------------------------------------------------------------------------|
| `sensor_raw`  | `device_id`, `location`, `q_*`    | `temperature`, `humidity`, `distance_cm`, `seq`, `rssi`, `e2e_latency_ms`     |

### bucket `iot_processed` (retention 30 ngày)
| measurement        | tags        | fields                                                                                                                              |
|--------------------|-------------|-------------------------------------------------------------------------------------------------------------------------------------|
| `sensor_processed` | `device_id` | `temperature`, `humidity`, `distance_cm`, `*_rollmean5`, `*_rollstd5`, `*_delta`, `*_roc`, `*_minmax`, `*_zscore`, `*_is_outlier`, `dew_point` |

Chống trùng: collector cache LRU `(device_id, seq)` 10.000 phần tử.
Phát hiện mất gói: do `seq` tăng đơn điệu — truy vấn Flux `difference()` trên seq.

## 8. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|------------|------------------------|------------|
| `python verify_influx.py` → `health: fail` nhưng buckets ra đủ | Quirk của InfluxDB Cloud Serverless | Bỏ qua — thực tế write/read vẫn OK |
| Collector `in=0 written=0` | Sai `topic` hoặc broker | Kiểm tra `TOPIC_PREFIX` ở sketch khớp `topic` ở config |
| Collector connect refused `localhost:8086` | Config vẫn trỏ local Influx | Sửa phần `influx:` trong config dùng URL Cloud |
| Wokwi `[WiFi] FAIL` | Mạng Wokwi tạm trục trặc | Dừng ▶ Start lại; hoặc chờ 1-2 phút |
| Dashboard "Chưa có dữ liệu raw" | Collector chưa ghi được, hoặc khung thời gian quá ngắn | Kéo slider thời gian lên 60, check collector log |
| `ParserError` khi query trên Data Explorer | Query Builder bị bug trên Serverless | Dùng Script Editor tự paste SQL (xem phần 9) |

## 9. Query SQL mẫu để kiểm tra data

Trong Data Explorer → Script Editor → chọn ngôn ngữ SQL → paste:

```sql
-- Xem 200 bản ghi gần nhất
SELECT time, device_id, temperature, humidity, distance_cm
FROM "sensor_raw"
WHERE time >= now() - INTERVAL '15 minutes'
ORDER BY time DESC
LIMIT 200;
```

```sql
-- Vẽ chart đường trung bình 10 giây
SELECT
  DATE_BIN(INTERVAL '10 seconds', time) AS bucket_time,
  AVG(temperature) AS temperature,
  AVG(humidity)    AS humidity,
  AVG(distance_cm) AS distance_cm
FROM "sensor_raw"
WHERE time >= now() - INTERVAL '15 minutes'
GROUP BY bucket_time
ORDER BY bucket_time;
```
Panel kết quả: chuyển view **TABLE → GRAPH** để ra 3 đường cong.

## 10. (Tuỳ chọn) Chạy với Docker thay vì Cloud

Nếu máy có Docker Desktop + quyền admin:
```bash
docker compose -f config/docker-compose.yml up -d
bash scripts/init_influxdb.sh
```
Rồi trong 2 file config đổi:
```yaml
mqtt:   { host: "localhost", topic: "iot/+/telemetry" }
influx: { url: "http://localhost:8086", org: "ptit", token: "my-super-secret-admin-token" }
```
Phần còn lại giữ nguyên.

## 11. Mở rộng

- **MQTT TLS (port 8883)**: cấp cert tự ký, dùng `WiFiClientSecure` thay cho `WiFiClient`.
- **Edge processing**: tính rolling mean/outlier trên ESP32 để giảm 50-70% băng thông.
- **So sánh DB**: ghi song song MongoDB Time-Series, đo ingest/throughput và latency truy vấn.
- **Anomaly detection**: Isolation Forest trên bucket processed, publish cảnh báo lại qua MQTT.

---
_© 2026 AnhAnh — PTIT · IoT và Ứng dụng (INT14149) · BTH2_
