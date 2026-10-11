# Chạy BTH2 với Wokwi (DHT22 + HC-SR04)

Thư mục này chứa đủ file để chạy ESP32 trên **wokwi.com** và vẫn tích hợp
được với collector + InfluxDB + dashboard chạy ở local.

**Mạch (giữ nguyên từ Bài 1):** ESP32 DevKit v1 + DHT22 (GPIO15) + HC-SR04
(TRIG=GPIO5, ECHO=GPIO18) + LED báo publish (GPIO12 qua điện trở 220Ω).
Cảm biến đo: nhiệt độ, độ ẩm, **khoảng cách (cm)** — không dùng LDR.

**Dual publish:** firmware publish song song 2 hướng:
- `thingsboard.cloud` — giữ dashboard ThingsBoard của Bài 1 (có thể tắt bằng
  `#define ENABLE_THINGSBOARD 0` nếu chỉ demo Bài 2).
- `broker.hivemq.com` — JSON đầy đủ schema BTH2 cho collector local.

## 1. Kiến trúc khi dùng Wokwi

```
[Wokwi ESP32 (cloud)]  --MQTT 1883--> [broker PUBLIC: broker.hivemq.com]
                                             ^ subscribe
                                             |
                              [Collector trên máy bạn]
                                             | HTTP
                                             v
                                      [InfluxDB local] --> [Streamlit dashboard]
```

Lý do: Wokwi chạy trên cloud nên **không thấy được** `localhost` hay
`192.168.x.x` trên máy bạn. Cách đơn giản nhất là cho cả ESP32 (Wokwi) và
collector (local) cùng gặp nhau ở một **broker MQTT public** trên Internet.

## 2. Chọn broker public

| Broker | Host | Port | Ghi chú |
|---|---|---|---|
| HiveMQ public | `broker.hivemq.com` | 1883 | **Khuyên dùng**, ổn định |
| EMQX public | `broker.emqx.io` | 1883 | Tốc độ tốt |
| Mosquitto test | `test.mosquitto.org` | 1883 | Đôi khi chậm, có log |

Mặc định `sketch.ino` và `config.wokwi.yaml` đã trỏ sang HiveMQ.

> ⚠️ Broker public ai cũng dùng được, nên bắt buộc đặt **topic prefix duy
> nhất** để không đọc nhầm dữ liệu người khác. Prefix mặc định ở đây là
> `anhanh/ptit/iot` — bạn **nên** đổi thành gì đó random hơn (ví dụ
> `anhanh/ptit/iot/abc123/…`) rồi update ở **hai** chỗ: `sketch.ino` và
> `config/config.wokwi.yaml`.

## 3. Dựng project trên Wokwi

1. Mở <https://wokwi.com> → đăng nhập → **New Project** → chọn **ESP32**.
2. Chuyển sang tab **diagram.json** và dán toàn bộ nội dung
   `firmware/wokwi/diagram.json` của repo này.
3. Sang tab **sketch.ino**, dán toàn bộ `firmware/wokwi/sketch.ino`.
4. Nhấn vào thanh menu **Library Manager** → thêm từng thư viện trong
   `libraries.txt`:
   - `PubSubClient` (Nick O'Leary)
   - `DHT ESP` (beegee_tokyo) — gọi `DHTesp` giống code Bài 1
   - `ArduinoJson` (v6.x)
5. Trong `sketch.ino`, kiểm tra:
   - `TOPIC_PREFIX` (nên đổi khỏi mặc định).
   - `DEVICE_ID` (nếu demo nhiều ESP cùng lúc).
6. Nhấn **▶ Start Simulation**. Mở **Serial Monitor** để xem log — bạn sẽ
   thấy:
   ```
   [BOOT] telemetry topic = anhanh/ptit/iot/esp32-wokwi-01/telemetry
   [WiFi] Kết nối SSID=Wokwi-GUEST .... OK
   [MQTT] Kết nối broker.hivemq.com:1883 ... OK
   [PUB OK] seq=1 t=28.50 h=62.00 lux=500.0
   ```

### Tương tác với mạch Wokwi
- Click vào **DHT22** → kéo thanh nhiệt độ / độ ẩm → xem giá trị thay đổi theo thời gian thực.
- Click vào **HC-SR04** → kéo thanh distance để mô phỏng vật thể lại gần / ra xa.
- LED xanh (GPIO12) **chớp 80 ms** mỗi lần publish — chứng tỏ firmware đang gửi.

## 4. Chạy collector + dashboard ở local

Trên máy bạn (vẫn Docker Mosquitto có thể **không cần**, nhưng cần InfluxDB):

```bash
# 1. Khởi tạo hạ tầng (bỏ qua Mosquitto nếu không dùng ESP32 thật)
docker compose -f config/docker-compose.yml up -d influxdb grafana
bash scripts/init_influxdb.sh

# 2. Chạy collector với config Wokwi (trỏ sang broker.hivemq.com)
CONFIG_PATH=config/config.wokwi.yaml python collector/mqtt_to_influx.py
```

Log collector sẽ hiện ra:
```
MQTT connected, subscribed topic=anhanh/ptit/iot/+/telemetry
metrics: in=20 written=20 invalid=0 dup=0 (last 30s)
```

Mở dashboard (vẫn như cũ):
```bash
streamlit run dashboard/app.py
```

## 5. Kiểm tra bằng mosquitto_sub (debug)

Nếu collector không nhận được gói nào, thử subscribe trực tiếp:
```bash
mosquitto_sub -h broker.hivemq.com -t 'anhanh/ptit/iot/#' -v
```
Thấy JSON xuất hiện → mạch Wokwi OK, lỗi nằm ở collector/InfluxDB.
Không thấy → kiểm tra lại WiFi/MQTT ở Serial Monitor của Wokwi.

## 6. Các giới hạn cần biết của Wokwi

- Mô phỏng chỉ chạy khi tab trình duyệt **active**; nếu để chạy nền lâu, nên
  mở tab ở màn hình phụ.
- Internet access của Wokwi-GUEST là **sandbox**: chỉ cho một số host DNS phổ
  biến. HiveMQ, EMQX, Mosquitto test, pool.ntp.org đều OK.
- Thời gian mỗi phiên free khoảng **≈ vài chục phút**; đủ cho demo. Nếu cần
  lâu hơn, lưu project rồi mở lại.
- RSSI báo về chỉ là giá trị giả.

## 7. File trong thư mục này

| File | Mục đích |
|------|----------|
| `sketch.ino` | Firmware phiên bản Wokwi (WiFi-GUEST + broker public) |
| `diagram.json` | Sơ đồ linh kiện: ESP32 + DHT22 + LDR + LED |
| `libraries.txt` | Danh sách thư viện cần cài trên Wokwi |
| `wokwi.toml` | Dùng khi build firmware ở local rồi upload (PlatformIO) |
| `README.md` | Chính file này |
