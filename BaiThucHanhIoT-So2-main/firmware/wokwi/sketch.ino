/*
 * ============================================================================
 *  BTH2 — Firmware Wokwi, kế thừa mạch của Bài 1 (DHT22 + HC-SR04 + LED).
 *
 *  Mạch (giữ nguyên của Bài 1):
 *      DHT22       : DATA = GPIO15, VCC 3V3
 *      HC-SR04     : TRIG = GPIO5, ECHO = GPIO18, VCC 5V/VIN
 *      LED (báo)   : GPIO12 qua điện trở 220Ω
 *
 *  Mới cho Bài 2:
 *    - Publish SONG SONG hai hướng:
 *        (a) ThingsBoard: topic v1/devices/me/telemetry — giữ dashboard Bài 1.
 *        (b) Broker PUBLIC (broker.hivemq.com): JSON có đầy đủ schema của
 *            Bài 2 (device_id, timestamp ISO-8601, seq, nested data) để
 *            collector local nhận và ghi vào InfluxDB.
 *    - LWT online/offline ở topic trạng thái.
 *    - NTP đồng bộ giờ để timestamp đúng múi GMT+7.
 *    - Nhận lệnh thay đổi chu kỳ qua topic config.
 *
 *  Thư viện cần cài (Library Manager của Wokwi):
 *      PubSubClient, DHT ESP (DHTesp của beegee_tokyo), ArduinoJson
 * ============================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHTesp.h>
#include <ArduinoJson.h>
#include <time.h>

// --------- Bật/tắt publish sang ThingsBoard (giữ luồng Bài 1) --------------
#define ENABLE_THINGSBOARD 1

// --------- WiFi (Wokwi) ----------------------------------------------------
const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// --------- ThingsBoard (giữ nguyên từ Bài 1) -------------------------------
const char* TB_HOST   = "thingsboard.cloud";
const int   TB_PORT   = 1883;
const char* TB_TOKEN  = "1yCs5THZFtEhfTrDkZpM";
const char* TB_TOPIC  = "v1/devices/me/telemetry";

// --------- Broker PUBLIC cho pipeline Bài 2 --------------------------------
const char* MQTT_HOST  = "broker.hivemq.com";
const int   MQTT_PORT  = 1883;
// Prefix duy nhất để không đụng người khác dùng broker public — ĐỔI theo bạn
const char* TOPIC_PREFIX = "anhanh/ptit/iot";
const char* DEVICE_ID    = "esp32-wokwi-01";
const char* LOCATION     = "wokwi-lab";

String TELEMETRY_TOPIC;   // <prefix>/<device_id>/telemetry
String STATUS_TOPIC;      // <prefix>/<device_id>/status (retained + LWT)
String CONFIG_TOPIC;      // <prefix>/<device_id>/config (subscribe)

// --------- Thời gian -------------------------------------------------------
const char* NTP_SERVER       = "pool.ntp.org";
const long  GMT_OFFSET_SEC   = 7 * 3600;    // GMT+7
const int   DST_OFFSET_SEC   = 0;
unsigned long SEND_INTERVAL_MS = 5000;

// --------- Chân ------------------------------------------------------------
const int DHT_PIN   = 15;
const int TRIG_PIN  = 5;
const int ECHO_PIN  = 18;
const int LED_PIN   = 12;

// --------- Khách MQTT: 2 kết nối song song --------------------------------
WiFiClient   wifiTB,  wifiPub;
PubSubClient tbClient(wifiTB);
PubSubClient pubClient(wifiPub);
DHTesp       dht;

unsigned long lastSend   = 0;
unsigned long sequenceNo = 0;

// =========================================================================
//                                HELPERS
// =========================================================================
String isoTimestamp() {
  struct tm t;
  if (!getLocalTime(&t)) return String("1970-01-01T00:00:00+07:00");
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S+07:00", &t);
  return String(buf);
}

void connectWiFi() {
  Serial.print("[WiFi] connecting");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.printf(" OK  IP=%s\n", WiFi.localIP().toString().c_str());
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return NAN;
  return duration * 0.0343f / 2.0f;
}

// --------- Callback cho pubClient (chỉnh chu kỳ qua MQTT) -----------------
void onConfig(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<96> doc;
  if (deserializeJson(doc, payload, len)) return;
  if (doc.containsKey("interval_ms")) {
    unsigned long v = doc["interval_ms"].as<unsigned long>();
    if (v >= 1000 && v <= 60000) {
      SEND_INTERVAL_MS = v;
      Serial.printf("[CFG] interval=%lu ms\n", v);
    }
  }
}

// --------- Kết nối ThingsBoard --------------------------------------------
void connectTB() {
#if ENABLE_THINGSBOARD
  tbClient.setServer(TB_HOST, TB_PORT);
  tbClient.setBufferSize(256);
  while (!tbClient.connected()) {
    String cid = "esp32-tb-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.printf("[TB] connect %s:%d ... ", TB_HOST, TB_PORT);
    if (tbClient.connect(cid.c_str(), TB_TOKEN, NULL)) {
      Serial.println("OK");
    } else {
      Serial.printf("FAIL rc=%d\n", tbClient.state());
      delay(2000);
    }
  }
#endif
}

// --------- Kết nối broker public (BTH2 pipeline) --------------------------
void connectPub() {
  pubClient.setServer(MQTT_HOST, MQTT_PORT);
  pubClient.setBufferSize(512);
  pubClient.setKeepAlive(30);
  pubClient.setCallback(onConfig);
  while (!pubClient.connected()) {
    String cid = String(DEVICE_ID) + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.printf("[PUB] connect %s:%d ... ", MQTT_HOST, MQTT_PORT);
    bool ok = pubClient.connect(cid.c_str(), nullptr, nullptr,
                                STATUS_TOPIC.c_str(), 1, true,
                                "{\"status\":\"offline\"}");
    if (ok) {
      Serial.println("OK");
      pubClient.publish(STATUS_TOPIC.c_str(), "{\"status\":\"online\"}", true);
      pubClient.subscribe(CONFIG_TOPIC.c_str(), 1);
    } else {
      Serial.printf("FAIL rc=%d\n", pubClient.state());
      delay(2000);
    }
  }
}

// =========================================================================
//                              SETUP / LOOP
// =========================================================================
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n======  ESP32 BTH2 — Wokwi  ======");

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN,  OUTPUT);
  dht.setup(DHT_PIN, DHTesp::DHT22);

  TELEMETRY_TOPIC = String(TOPIC_PREFIX) + "/" + DEVICE_ID + "/telemetry";
  STATUS_TOPIC    = String(TOPIC_PREFIX) + "/" + DEVICE_ID + "/status";
  CONFIG_TOPIC    = String(TOPIC_PREFIX) + "/" + DEVICE_ID + "/config";
  Serial.printf("[BOOT] telemetry = %s\n", TELEMETRY_TOPIC.c_str());

  connectWiFi();
  configTime(GMT_OFFSET_SEC, DST_OFFSET_SEC, NTP_SERVER);
  connectTB();
  connectPub();
}

void publishAll(float t, float h, float dist) {
  sequenceNo++;

  // (A) ThingsBoard — flat JSON như Bài 1
#if ENABLE_THINGSBOARD
  if (tbClient.connected()) {
    char tb[256];
    snprintf(tb, sizeof(tb),
      "{\"temperature\":%.2f,\"humidity\":%.2f,\"distance_cm\":%.2f,"
      "\"rssi\":%d,\"sequence\":%lu,\"uptime_s\":%lu}",
      t, h, dist, WiFi.RSSI(), sequenceNo, millis() / 1000);
    bool ok = tbClient.publish(TB_TOPIC, tb);
    Serial.printf("[TB PUB %s] %s\n", ok ? "OK" : "FAIL", tb);
  }
#endif

  // (B) Broker public — JSON đầy đủ schema của Bài 2
  if (pubClient.connected()) {
    StaticJsonDocument<384> doc;
    doc["device_id"] = DEVICE_ID;
    doc["location"]  = LOCATION;
    doc["timestamp"] = isoTimestamp();
    doc["seq"]       = sequenceNo;
    doc["uptime_s"]  = millis() / 1000;
    doc["rssi"]      = WiFi.RSSI();
    JsonObject d = doc.createNestedObject("data");
    d["temperature"] = round(t * 100) / 100.0;
    d["humidity"]    = round(h * 100) / 100.0;
    d["distance_cm"] = round(dist * 100) / 100.0;
    doc["unit_temperature"] = "C";
    doc["unit_humidity"]    = "%";
    doc["unit_distance"]    = "cm";

    char buf[384];
    size_t n = serializeJson(doc, buf, sizeof(buf));
    bool ok = pubClient.publish(TELEMETRY_TOPIC.c_str(),
                                (const uint8_t*)buf, n, false);
    Serial.printf("[BTH2 PUB %s] seq=%lu\n", ok ? "OK" : "FAIL", sequenceNo);
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
#if ENABLE_THINGSBOARD
  if (!tbClient.connected())  connectTB();
  tbClient.loop();
#endif
  if (!pubClient.connected()) connectPub();
  pubClient.loop();

  unsigned long now = millis();
  if (now - lastSend < SEND_INTERVAL_MS) return;
  lastSend = now;

  TempAndHumidity th = dht.getTempAndHumidity();
  float dist = readDistanceCm();

  if (!isfinite(th.temperature) || !isfinite(th.humidity) || !isfinite(dist)) {
    Serial.println("[WARN] invalid sensor — skip publish");
    return;
  }

  publishAll(th.temperature, th.humidity, dist);

  digitalWrite(LED_PIN, HIGH); delay(80); digitalWrite(LED_PIN, LOW);
}
