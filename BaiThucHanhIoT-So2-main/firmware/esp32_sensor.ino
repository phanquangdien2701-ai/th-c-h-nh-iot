/*
 * ============================================================================
 *  BÀI THỰC HÀNH SỐ 2 - IoT và Ứng dụng (INT14149)
 *  Firmware: ESP32 đọc cảm biến DHT22 + LDR và publish MQTT
 *  Author:  AnhAnh
 *  Date:    2026-10-11
 *
 *  Chức năng:
 *   - Kết nối WiFi
 *   - Đọc DHT22 (nhiệt độ, độ ẩm) và LDR (ánh sáng, ADC)
 *   - Publish JSON lên MQTT broker theo topic: iot/<device_id>/telemetry
 *   - LWT (Last Will & Testament) để báo trạng thái offline
 *   - Tự reconnect WiFi/MQTT khi mất kết nối
 *   - QoS 1 để đảm bảo at-least-once delivery
 *
 *  Thư viện cần cài qua Arduino Library Manager:
 *   - PubSubClient (Nick O'Leary)
 *   - DHT sensor library (Adafruit)
 *   - Adafruit Unified Sensor
 *   - ArduinoJson (Benoit Blanchon) - v6.x
 * ============================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <time.h>

// ============================= CẤU HÌNH ====================================
// WiFi
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// MQTT Broker (đổi thành IP máy chạy Mosquitto)
const char* MQTT_HOST     = "192.168.1.100";
const uint16_t MQTT_PORT  = 1883;
const char* MQTT_USER     = "";          // để trống nếu broker không yêu cầu auth
const char* MQTT_PASSWORD = "";

// Device identity
const char* DEVICE_ID     = "esp32-01";
const char* LOCATION      = "lab-ptit";

// Topics
String TELEMETRY_TOPIC;    // iot/<device_id>/telemetry
String STATUS_TOPIC;       // iot/<device_id>/status
String CONFIG_TOPIC;       // iot/<device_id>/config (subscribe)

// NTP (lấy thời gian thực để gắn timestamp ISO-8601)
const char* NTP_SERVER    = "pool.ntp.org";
const long  GMT_OFFSET_SEC = 7 * 3600;   // GMT+7 Việt Nam
const int   DST_OFFSET_SEC = 0;

// Chu kỳ sampling (ms)
uint32_t PUBLISH_INTERVAL_MS = 3000;

// Chân cảm biến
#define DHT_PIN   4
#define DHT_TYPE  DHT22
#define LDR_PIN   34   // ADC1_CH6
#define LED_PIN   2    // LED on-board, báo trạng thái

// ============================= GLOBAL =====================================
WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
DHT dht(DHT_PIN, DHT_TYPE);

uint32_t lastPublish = 0;
uint32_t messageSeq  = 0;

// ============================= HÀM TRỢ GIÚP ===============================
String isoTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return String("1970-01-01T00:00:00Z");
  }
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S+07:00", &timeinfo);
  return String(buf);
}

void connectWiFi() {
  Serial.printf("[WiFi] Kết nối tới %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] OK, IP=%s, RSSI=%d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("\n[WiFi] FAILED, sẽ thử lại sau");
  }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  // Nhận lệnh cấu hình từ server (ví dụ: đổi chu kỳ publish)
  StaticJsonDocument<128> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.printf("[MQTT] JSON parse error: %s\n", err.c_str());
    return;
  }
  if (doc.containsKey("interval_ms")) {
    uint32_t v = doc["interval_ms"].as<uint32_t>();
    if (v >= 500 && v <= 60000) {
      PUBLISH_INTERVAL_MS = v;
      Serial.printf("[MQTT] Cập nhật PUBLISH_INTERVAL_MS = %u\n", v);
    }
  }
}

void connectMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);

  while (!mqtt.connected()) {
    Serial.printf("[MQTT] Kết nối broker %s:%u ... ", MQTT_HOST, MQTT_PORT);
    String clientId = String(DEVICE_ID) + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);

    // LWT: nếu mất kết nối bất ngờ, broker tự publish "offline"
    bool ok = mqtt.connect(
      clientId.c_str(),
      (strlen(MQTT_USER) ? MQTT_USER : nullptr),
      (strlen(MQTT_PASSWORD) ? MQTT_PASSWORD : nullptr),
      STATUS_TOPIC.c_str(), 1, true, "{\"status\":\"offline\"}"
    );

    if (ok) {
      Serial.println("OK");
      // Báo online (retained) để dashboard biết thiết bị đang hoạt động
      mqtt.publish(STATUS_TOPIC.c_str(), "{\"status\":\"online\"}", true);
      mqtt.subscribe(CONFIG_TOPIC.c_str(), 1);
      Serial.printf("[MQTT] Subscribed: %s\n", CONFIG_TOPIC.c_str());
    } else {
      Serial.printf("FAIL rc=%d, thử lại sau 3s\n", mqtt.state());
      delay(3000);
    }
  }
}

// Đọc LDR và quy đổi sang lux xấp xỉ (chỉ có tính minh họa)
float readLightLux() {
  const int N = 10;
  uint32_t sum = 0;
  for (int i = 0; i < N; i++) {
    sum += analogRead(LDR_PIN);
    delay(2);
  }
  float adc = sum / (float)N;             // 0..4095
  // Mapping tuyến tính đơn giản: ADC 0 -> tối (0 lux), 4095 -> rất sáng (1000 lux)
  float lux = (adc / 4095.0f) * 1000.0f;
  return lux;
}

bool publishTelemetry() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  float lux = readLightLux();

  // Validate: DHT22 fail -> NaN
  bool tOk = !isnan(t) && t > -40 && t < 85;
  bool hOk = !isnan(h) && h >= 0 && h <= 100;

  StaticJsonDocument<384> doc;
  doc["device_id"]  = DEVICE_ID;
  doc["location"]   = LOCATION;
  doc["timestamp"]  = isoTimestamp();
  doc["seq"]        = ++messageSeq;
  doc["uptime_s"]   = millis() / 1000;
  doc["rssi"]       = WiFi.RSSI();

  JsonObject data = doc.createNestedObject("data");
  if (tOk)  data["temperature"] = round(t * 100) / 100.0;
  else      data["temperature"] = nullptr;
  if (hOk)  data["humidity"]    = round(h * 100) / 100.0;
  else      data["humidity"]    = nullptr;
  data["light"] = round(lux * 10) / 10.0;

  doc["unit_temperature"] = "C";
  doc["unit_humidity"]    = "%";
  doc["unit_light"]       = "lux";

  char buf[384];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  bool ok = mqtt.publish(TELEMETRY_TOPIC.c_str(), (const uint8_t*)buf, n, false);

  Serial.printf("[PUB %s] seq=%u t=%.2f h=%.2f lux=%.1f -> %s\n",
                ok ? "OK" : "FAIL", messageSeq, t, h, lux, buf);
  return ok;
}

// ============================= SETUP / LOOP ===============================
void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(LED_PIN, OUTPUT);
  dht.begin();
  analogReadResolution(12);

  TELEMETRY_TOPIC = String("iot/") + DEVICE_ID + "/telemetry";
  STATUS_TOPIC    = String("iot/") + DEVICE_ID + "/status";
  CONFIG_TOPIC    = String("iot/") + DEVICE_ID + "/config";

  connectWiFi();
  configTime(GMT_OFFSET_SEC, DST_OFFSET_SEC, NTP_SERVER);
  connectMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_PIN, LOW);
    connectWiFi();
  }
  if (!mqtt.connected()) {
    connectMQTT();
  }
  mqtt.loop();

  if (millis() - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = millis();
    digitalWrite(LED_PIN, HIGH);
    publishTelemetry();
    delay(30);
    digitalWrite(LED_PIN, LOW);
  }
}
