#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketMCP.h>
#include <PubSubClient.h>
#include <WiFiClient.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ArduinoJson.h>
#include <HardwareSerial.h>
#include <Preferences.h>  // ESP32 NVS 持久化存储
// 所有可配置参数集中在 config.h，烧录前在那里修改即可
#include "config.h"

/* ********* Configuration Items ************ */
// WiFi settings
// wifiSsid/wifiPass：当前已连接的 WiFi（连接成功后自动填入，不需要手动赋值）
String wifiSsid = "";
String wifiPass = "";
// nvsWifiSsid/nvsWifiPass：NVS 中保存的备用凭据（SmartConfig 或 set_config 写入）
String nvsWifiSsid = "";
String nvsWifiPass  = "";

// WebSocket MCP server address（来自 config.h，NVS 可远程覆盖暂不支持因 Token 过长）
const char* MCP_ENDPOINT = CFG_MCP_ENDPOINT;

// 仪器序号（默认值来自 config.h，NVS 可远程覆盖，掉电不丢失）
String instrumentId = CFG_INSTRUMENT_ID;
Preferences prefs;  // NVS 存储对象

// MQTT server configuration（默认值来自 config.h，NVS 可远程覆盖）
String mqttServerStr = CFG_MQTT_SERVER;
int    mqttPortVal   = CFG_MQTT_PORT;
const char* mqtt_client_id = CFG_MQTT_CLIENT_ID;

// MQTT Topics（来自 config.h）
const char* TOPIC_INSTRUMENT_DATA = CFG_TOPIC_INSTRUMENT_DATA;
const char* TOPIC_XIAOZHI_SPEAK   = CFG_TOPIC_XIAOZHI_SPEAK;
const char* TOPIC_UPLOAD_STATUS   = CFG_TOPIC_UPLOAD_STATUS;

// Serial configuration (606 protocol)
#define SERIAL_RX_PIN 16  // GPIO16 for RX
#define SERIAL_TX_PIN 17  // GPIO17 for TX
#define SERIAL_BAUDRATE 115200
HardwareSerial SerialPort(2); // Use Serial2

// 606协议常量（与 tests/test_serial.py / success.ino 一致）
#define FRAME_HEADER_SEND 0x5E  // 发送帧头
#define FRAME_HEADER_RESP 0x5F  // 应答帧头
#define FRAME_TAIL        0x0D  // 帧尾

// Debugging information
#define DEBUG_SERIAL Serial
#define DEBUG_BAUD_RATE 115200

// LED control pin definition
#define LED_PIN 2  // ESP32 onboard LED

// 主动进入 SoftAP 的按键（默认用 BOOT 键 GPIO0，低电平按下）
#define SOFTAP_TRIGGER_PIN 0
#define SOFTAP_TRIGGER_ACTIVE_LEVEL LOW

// 小智唤醒触发输出（接到小智 GPIO38，低电平触发）
#define XIAOZHI_WAKEUP_PIN 47

/* ******* Global variables ********** */
WebSocketMCP mcpClient;
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Connection status
bool wifiConnected = false;
bool mcpConnected = false;
bool mqttConnected = false;

// SoftAP 配网页面服务
bool softApActive = false;
WebServer configServer(80);
DNSServer dnsServer;
const byte DNS_PORT = 53;
IPAddress apIp(192, 168, 44, 1);
IPAddress apMask(255, 255, 255, 0);
unsigned long lastWifiScanTime = 0;
const unsigned long wifiScanIntervalMs = 15000;
String wifiScanOptionsHtml = "";
bool softApTriggerPressed = false;
unsigned long softApTriggerPressStart = 0;
const unsigned long softApTriggerHoldMs = 3000;

// 周期性状态输出（用于“看不到是否连上WiFi/MQTT/MCP”的问题）
unsigned long lastStatusPrintTime = 0;
const unsigned long statusPrintInterval = 30000; // 30秒输出一次（减少刷屏）
unsigned long lastMqttReconnectAttempt = 0;      // 避免 MQTT 断开时疯狂尝试重连刷屏

// LED blink control
unsigned long lastHeartbeatTime = 0;
const unsigned long heartbeatInterval = 120000;  // 120秒（2分钟）
unsigned long lastLedBlinkTime = 0;
const unsigned long ledBlinkInterval = 500;   // LED闪烁间隔500ms
bool ledState = false;

// Exam records storage (max 100 records)
struct ExamRecord {
  float height_cm;
  float weight_kg;
  float bmi;
  String advice;
  String timestamp;
  String record_id;
};

ExamRecord exam_records[100];
int exam_record_count = 0;
int exam_record_index = 0;

// Last person data
float last_height = 0;
float last_weight = 0;

// ---------- 串口(606二进制协议)接收缓冲与统计 ----------
unsigned long lastReceiveTime = 0;
unsigned long receiveCount = 0;
unsigned long sendCount = 0;

uint8_t rxBuffer[256];
int rxIndex = 0;

// 分开测身高/体重时的暂存（避免必须依赖0x47）
float pending_height_cm = 0;
float pending_weight_kg = 0;
unsigned long pending_ts = 0;

// MQTT 发布防抖：两次发布之间的最小间隔（单位毫秒，NVS 可远程修改）
unsigned long lastPublishTime = 0;
unsigned long MIN_PUBLISH_INTERVAL = 8000;  // 8秒内不重复发布同一条测量数据（可通过 set_config 修改）

// ⚠️  两板之间只需保留：测量板 GPIO47 → 小智 GPIO38，以及 GND → GND（共 2 根飞线）。
// 唤醒走 GPIO47→GPIO38 触发 WakeWordInvoke，由云端 AI 直接调 MCP 工具播报，无需 I2S。

/* ********* Function declaration *************** */
void setupWifi();
void startSmartConfig();
bool tryConnectWifi(const String& ssid, const String& pass, const String& tag);
void startSoftApConfigPortal();
void stopSoftApConfigPortal();
void setupConfigWebServer();
void handleRedirectToRoot();
void refreshWifiScanCache(bool force = false);
String htmlEscape(const String& input);
void handleConfigRoot();
void handleConfigSave();
void checkSoftApManualTrigger();
void onMcpConnectionChange(bool connected);
void registerMcpTools();
void reconnectMQTT();
void sendHeartbeat();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void processSerialData();
void handleConsoleCommand(char cmd);
void send606Command(uint8_t cmd, uint8_t* data = NULL, int dataLen = 0);
void printSerialHelp();
void printSerialStats();
void processPhysicalExam(float height_cm, float weight_kg, String record_id = "");
float calculateBMI(float height_cm, float weight_kg);
String generateAdvice(float bmi);
void publishToMQTT(const char* topic, String message);
void pushToXiaozhi(String text);
String getCurrentTimestamp();
String generateRecordId();

void setup() {
  // Initialize the serial port
  DEBUG_SERIAL.begin(DEBUG_BAUD_RATE);
#if defined(ARDUINO_USB_CDC_ON_BOOT) && (ARDUINO_USB_CDC_ON_BOOT == 1)
  // 对 ESP32-S3/C3 这类“原生USB CDC串口”，上电后需要一点时间完成枚举；
  // 不等待的话，开机最早几行日志可能会“看不到”。
  unsigned long _cdcStart = millis();
  while (!DEBUG_SERIAL && (millis() - _cdcStart < 2000)) {
    delay(10);
  }
#endif
  delay(200);
  DEBUG_SERIAL.println("\n\n[ESP32 Physical Exam Control] Initialization...");
  DEBUG_SERIAL.println("[System] Booting...");
  DEBUG_SERIAL.print("[System] CPU Frequency: ");
  DEBUG_SERIAL.print(getCpuFrequencyMhz());
  DEBUG_SERIAL.println(" MHz");
  DEBUG_SERIAL.print("[System] Free heap: ");
  DEBUG_SERIAL.println(ESP.getFreeHeap());
  DEBUG_SERIAL.print("[System] Sketch size: ");
  DEBUG_SERIAL.println(ESP.getSketchSize());
  DEBUG_SERIAL.print("[System] Chip model: ");
  DEBUG_SERIAL.println(ESP.getChipModel());
  DEBUG_SERIAL.print("[System] Chip revision: ");
  DEBUG_SERIAL.println(ESP.getChipRevision());
  DEBUG_SERIAL.print("[System] SDK: ");
  DEBUG_SERIAL.println(ESP.getSdkVersion());
  
  // 从 NVS 加载所有远程可配置参数（若从未写入则使用上方的默认值）
  prefs.begin("device", true);  // true = 只读模式
  instrumentId     = prefs.getString("instrument_id",  instrumentId);
  nvsWifiSsid      = prefs.getString("wifi_ssid",      "");
  nvsWifiPass      = prefs.getString("wifi_pass",      "");
  mqttServerStr    = prefs.getString("mqtt_server",    mqttServerStr);
  mqttPortVal      = prefs.getInt   ("mqtt_port",      mqttPortVal);
  MIN_PUBLISH_INTERVAL = prefs.getULong("pub_interval", MIN_PUBLISH_INTERVAL);
  prefs.end();
  DEBUG_SERIAL.println("[NVS] Config loaded:");
  DEBUG_SERIAL.println("  instrument_id = " + instrumentId);
  DEBUG_SERIAL.println("  nvs_wifi_ssid = " + (nvsWifiSsid.length() > 0 ? nvsWifiSsid : "(none, will use config.h list)"));
  DEBUG_SERIAL.println("  mqtt_server   = " + mqttServerStr + ":" + String(mqttPortVal));
  DEBUG_SERIAL.println("  pub_interval  = " + String(MIN_PUBLISH_INTERVAL) + " ms");

  // Initialize LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // 初始化 SoftAP 手动触发按键（长按 3 秒进入配网）
  pinMode(SOFTAP_TRIGGER_PIN, INPUT_PULLUP);
  DEBUG_SERIAL.println("[SoftAP] Manual trigger ready: hold BOOT(GPIO0) for 3s");

  // 初始化小智唤醒触发脚：默认高电平，触发时短暂拉低
  pinMode(XIAOZHI_WAKEUP_PIN, OUTPUT);
  digitalWrite(XIAOZHI_WAKEUP_PIN, HIGH);
  DEBUG_SERIAL.println("[Wakeup] Trigger pin initialized: GPIO47 (active LOW)");

  // Initialize Serial2 for instrument communication
  SerialPort.begin(SERIAL_BAUDRATE, SERIAL_8N1, SERIAL_RX_PIN, SERIAL_TX_PIN);
  DEBUG_SERIAL.println("[Serial] Serial2 initialized for instrument communication");

  // 打印606串口调试快捷指令（参考 success.ino）
  DEBUG_SERIAL.println("\n========================================");
  DEBUG_SERIAL.println("606 Body Measurement Tool (integrated)");
  DEBUG_SERIAL.println("========================================");
  DEBUG_SERIAL.println("Quick Commands (type in Serial Monitor):");
  DEBUG_SERIAL.println("  1 - Read Version (0x54)");
  DEBUG_SERIAL.println("  2 - Get Temperature & Humidity (0x41)");
  DEBUG_SERIAL.println("  3 - Height Measurement (0x42)");
  DEBUG_SERIAL.println("  4 - Weight Measurement (0x43)");
  DEBUG_SERIAL.println("  5 - Height & Weight Measurement (0x47)");
  DEBUG_SERIAL.println("  6 - Vision Test (0x45)");
  DEBUG_SERIAL.println("  w - Start SoftAP WiFi portal (192.168.44.1)");
  DEBUG_SERIAL.println("  h - Show Help");
  DEBUG_SERIAL.println("  s - Show Statistics");
  DEBUG_SERIAL.println("  c - Clear Statistics");
  DEBUG_SERIAL.println("========================================\n");
  
  // Connect to WiFi
  setupWifi();
  
  // Wait a little bit for AP or STA mode to stabilize
  delay(100);
  
  // Initialize MQTT client
  if (wifiConnected) {
    mqttClient.setServer(mqttServerStr.c_str(), mqttPortVal);
    mqttClient.setCallback(mqttCallback);
    reconnectMQTT();
  } else {
    DEBUG_SERIAL.println("[MQTT] Skip MQTT init because WiFi is not connected yet");
  }
  
  // Initialize the MCP client
  DEBUG_SERIAL.println("[MCP] Initializing MCP client...");
  if (mcpClient.begin(MCP_ENDPOINT, onMcpConnectionChange)) {
    DEBUG_SERIAL.println("[ESP32 MCP Client] Initialization was successful, trying to connect to the MCP server...");
  } else {
    DEBUG_SERIAL.println("[ESP32 MCP Client] Initialization failed!");
  }
  
  lastHeartbeatTime = millis();
  lastLedBlinkTime = millis();
  lastStatusPrintTime = millis();
  
  DEBUG_SERIAL.println("\n[System] Initialization completed!");
}

void loop() {
  checkSoftApManualTrigger();

  // 处理 SoftAP 配网页面请求
  if (softApActive) {
    dnsServer.processNextRequest();
    refreshWifiScanCache();
    configServer.handleClient();
  }

  // Handle MCP clients
  mcpClient.loop();
  
  // 周期性输出当前状态（即使 WiFi 没连上也会输出）
  unsigned long now = millis();
  if (now - lastStatusPrintTime >= statusPrintInterval) {
    lastStatusPrintTime = now;
    DEBUG_SERIAL.println("\n================ STATUS ================");
    DEBUG_SERIAL.print("[WiFi] status=");
    DEBUG_SERIAL.print((int)WiFi.status());
    DEBUG_SERIAL.print(" connected=");
    DEBUG_SERIAL.println(wifiConnected ? "true" : "false");
    DEBUG_SERIAL.print("[SoftAP] active=");
    DEBUG_SERIAL.println(softApActive ? "true" : "false");
    if (softApActive) {
      DEBUG_SERIAL.print("[SoftAP] config page: http://");
      DEBUG_SERIAL.println(WiFi.softAPIP());
    }
    if (WiFi.status() == WL_CONNECTED) {
      DEBUG_SERIAL.print("[WiFi] IP=");
      DEBUG_SERIAL.println(WiFi.localIP());
      DEBUG_SERIAL.print("[WiFi] RSSI=");
      DEBUG_SERIAL.print(WiFi.RSSI());
      DEBUG_SERIAL.println(" dBm");
    }
    DEBUG_SERIAL.print("[MQTT] connected=");
    DEBUG_SERIAL.print(mqttClient.connected() ? "true" : "false");
    DEBUG_SERIAL.print(" state=");
    DEBUG_SERIAL.println(mqttClient.state());
    DEBUG_SERIAL.print("[MCP] connected=");
    DEBUG_SERIAL.println(mcpConnected ? "true" : "false");
    DEBUG_SERIAL.println("========================================\n");
  }

  // Check WiFi connection status (当处于 SoftAP 时不要检查重连，避免 STA 和 AP 冲突崩溃)
  if (!softApActive) {
    bool currentWifiStatus = (WiFi.status() == WL_CONNECTED);
    if (currentWifiStatus != wifiConnected) {
      wifiConnected = currentWifiStatus;
      if (!wifiConnected) {
        DEBUG_SERIAL.println("[WiFi] Connection lost!");
        digitalWrite(LED_PIN, LOW);
      } else {
        DEBUG_SERIAL.println("[WiFi] Reconnected!");
        DEBUG_SERIAL.print("[WiFi] IP address: ");
        DEBUG_SERIAL.println(WiFi.localIP());
        DEBUG_SERIAL.print("[WiFi] RSSI: ");
        DEBUG_SERIAL.print(WiFi.RSSI());
        DEBUG_SERIAL.println(" dBm");
        reconnectMQTT();
      }
    }
  }
  
  // LED闪烁控制（仅在WiFi连接时闪烁）
  if (wifiConnected) {
    unsigned long currentTime = millis();
    if (currentTime - lastLedBlinkTime >= ledBlinkInterval) {
      lastLedBlinkTime = currentTime;
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState ? HIGH : LOW);
    }
  } else {
    digitalWrite(LED_PIN, LOW);
  }
  
  // MQTT心跳发送（每30秒）
  if (wifiConnected) {
    // 确保 MQTT loop 一直跑（不然订阅回调/保活不会工作）
    mqttClient.loop();

    // 若断开则尝试重连（每次状态打印也能看到 state 值）
    if (!mqttClient.connected()) {
      reconnectMQTT();
    }

    if (mqttClient.connected()) {
      unsigned long currentTime = millis();
      if (currentTime - lastHeartbeatTime >= heartbeatInterval) {
        lastHeartbeatTime = currentTime;
        sendHeartbeat();
      }
    }
  }
  
  // Process serial data from instrument
  processSerialData();

  delay(10);
}

/* *
 * Set up WiFi connection.
 * 若凭据为空或连接失败，自动进入 SoftAP 网页配网模式。 */
void setupWifi() {
  WiFi.mode(WIFI_STA);

  // 1) 逐个尝试 config.h 中配置的多组 WiFi
  for (int i = 0; i < CFG_WIFI_COUNT; i++) {
    String tag = String(i + 1) + "/" + String(CFG_WIFI_COUNT);
    if (tryConnectWifi(String(CFG_WIFI_SSIDS[i]), String(CFG_WIFI_PASSES[i]), tag)) return;
  }

  // 2) 尝试 NVS 中保存的备用凭据（SmartConfig 或 set_config 写入）
  if (tryConnectWifi(nvsWifiSsid, nvsWifiPass, "NVS")) return;

  // 3) 全部失败，进入 SoftAP 配网页面模式
  wifiConnected = false;
  DEBUG_SERIAL.print("[WiFi] All " + String(CFG_WIFI_COUNT) + " credential(s) + NVS failed! status=");
  DEBUG_SERIAL.println((int)WiFi.status());
  DEBUG_SERIAL.println("[WiFi] Entering SoftAP config portal mode...");
  startSmartConfig();
}

bool tryConnectWifi(const String& ssid, const String& pass, const String& tag) {
  if (ssid.length() == 0) return false;

  if (softApActive) {
    stopSoftApConfigPortal();
  }

  WiFi.mode(WIFI_STA);
  DEBUG_SERIAL.print("[WiFi] Trying [" + tag + "] ");
  DEBUG_SERIAL.println(ssid);
  WiFi.begin(ssid.c_str(), pass.c_str());

  for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    DEBUG_SERIAL.print(".");
  }
  DEBUG_SERIAL.println();

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    wifiSsid = ssid;
    wifiPass = pass;
    DEBUG_SERIAL.println("[WiFi] Connected to: " + wifiSsid);
    DEBUG_SERIAL.print("[WiFi] IP: ");
    DEBUG_SERIAL.println(WiFi.localIP());
    DEBUG_SERIAL.print("[WiFi] RSSI: ");
    DEBUG_SERIAL.print(WiFi.RSSI());
    DEBUG_SERIAL.println(" dBm");
    return true;
  }

  WiFi.disconnect(true);
  delay(300);
  return false;
}

void setupConfigWebServer() {
  configServer.on("/", HTTP_GET, handleConfigRoot);
  configServer.on("/save", HTTP_POST, handleConfigSave);
  configServer.on("/generate_204", HTTP_ANY, handleRedirectToRoot);
  configServer.on("/gen_204", HTTP_ANY, handleRedirectToRoot);
  configServer.on("/hotspot-detect.html", HTTP_ANY, handleRedirectToRoot);
  configServer.on("/ncsi.txt", HTTP_ANY, handleRedirectToRoot);
  configServer.on("/connecttest.txt", HTTP_ANY, handleRedirectToRoot);
  configServer.on("/redirect", HTTP_ANY, handleRedirectToRoot);
  configServer.onNotFound([]() {
    configServer.sendHeader("Location", "http://192.168.44.1/");
    configServer.send(302, "text/plain", "Redirecting...");
  });
  configServer.begin();
}

void stopSoftApConfigPortal() {
  dnsServer.stop();
  configServer.stop();
  WiFi.softAPdisconnect(true);
  delay(100);
  WiFi.mode(WIFI_STA); // 恢复为 STA 模式
  delay(100);
  softApActive = false;
}

void handleRedirectToRoot() {
  configServer.sendHeader("Location", "http://192.168.44.1/");
  configServer.send(302, "text/plain", "Redirecting to config portal...");
}

String htmlEscape(const String& input) {
  String out = input;
  out.replace("&", "&amp;");
  out.replace("<", "&lt;");
  out.replace(">", "&gt;");
  out.replace("\"", "&quot;");
  out.replace("'", "&#39;");
  return out;
}

void refreshWifiScanCache(bool force) {
  if (!softApActive) return;
  if (!force && (millis() - lastWifiScanTime < wifiScanIntervalMs)) return;

  // 在 AP 模式下安全地扫描
  WiFi.mode(WIFI_AP_STA); // 暂时开启 STA 模式用于扫描
  delay(50);
  int count = WiFi.scanNetworks(false, true);
  
  String options = "";

  if (count > 0) {
    for (int i = 0; i < count; i++) {
      String ssid = WiFi.SSID(i);
      if (ssid.length() == 0) continue;

      String safeSsid = htmlEscape(ssid);
      int rssi = WiFi.RSSI(i);
      wifi_auth_mode_t enc = WiFi.encryptionType(i);

      String sec = (enc == WIFI_AUTH_OPEN) ? "Open" : "Secured";
      options += "<option value='" + safeSsid + "'>" + safeSsid + " (" + String(rssi) + " dBm, " + sec + ")</option>";
    }
  }

  if (options.length() == 0) {
    options = "<option value=''>未扫描到可用热点，请手动输入</option>";
  }

  wifiScanOptionsHtml = options;
  lastWifiScanTime = millis();
  WiFi.scanDelete();
  
  // 扫完切回 AP 模式，避免与客户端连接发生频段冲突（ESP32单天线局限性）
  WiFi.mode(WIFI_AP);
}

void startSoftApConfigPortal() {
  const char* apSsid = CFG_SOFTAP_SSID;
  const char* apPass = CFG_SOFTAP_PASS;

  if (softApActive) {
    stopSoftApConfigPortal();
    delay(100);
  }

  // 避免之前 STA 模式残留导致开启失败
  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_AP); // 改为纯 AP 模式，避免扫描时崩溃
  delay(100);

  WiFi.softAPConfig(apIp, apIp, apMask);

  bool apOk = false;
  if (strlen(apPass) >= 8) {
    apOk = WiFi.softAP(apSsid, apPass);
  } else {
    apOk = WiFi.softAP(apSsid);
  }

  if (!apOk) {
    DEBUG_SERIAL.println("[SoftAP] Failed to start SoftAP");
    softApActive = false;
    return;
  }

  delay(100);
  softApActive = true;
  setupConfigWebServer();
  dnsServer.start(DNS_PORT, "*", WiFi.softAPIP());
  
  // 不要在这里强制刷新 WiFi，ESP32 在 AP 刚刚开启时立刻扫描周围网络（并发）极易引发 Cache error 或重启
  // refreshWifiScanCache(true);

  DEBUG_SERIAL.println("[SoftAP] Config portal started");
  DEBUG_SERIAL.print("[SoftAP] SSID: ");
  DEBUG_SERIAL.println(apSsid);
  DEBUG_SERIAL.print("[SoftAP] Password: ");
  DEBUG_SERIAL.println(strlen(apPass) >= 8 ? apPass : "(open network)");
  DEBUG_SERIAL.print("[SoftAP] Open in browser: http://");
  DEBUG_SERIAL.println(WiFi.softAPIP());
  DEBUG_SERIAL.println("[SoftAP] Captive portal DNS enabled");
}

void handleConfigRoot() {
  refreshWifiScanCache();

  String html =
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>ESP32 WiFi Config</title>"
    "<style>body{font-family:Arial,sans-serif;max-width:520px;margin:20px auto;padding:0 16px;}"
    "h2{margin-bottom:8px;}"
    ".card{border:1px solid #ddd;border-radius:10px;padding:16px;}"
    "label{display:block;margin-top:12px;font-weight:600;}"
    "select," 
    "input{width:100%;padding:10px;margin-top:6px;box-sizing:border-box;}"
    "button{margin-top:14px;width:100%;padding:12px;border:0;background:#0a7;color:#fff;border-radius:8px;font-size:16px;}"
    "small{color:#666;display:block;margin-top:8px;}</style></head><body>"
    "<h2>ESP32 WiFi 配置</h2><div class='card'>"
    "<form method='post' action='/save'>"
    "<label>扫描到的 WiFi</label><select id='ssid_select'>" + wifiScanOptionsHtml + "</select>"
    "<label>WiFi SSID</label><input id='ssid_input' name='ssid' maxlength='64' required value='" + htmlEscape(wifiSsid) + "'>"
    "<label>WiFi 密码</label><input type='password' name='pass' maxlength='64' value='" + wifiPass + "'>"
    "<button type='submit'>保存并连接</button></form>"
    "<small>设备 AP 地址: http://192.168.44.1（已启用 Captive Portal）</small>"
    "<small>当前连接状态: " + String(wifiConnected ? "已连接" : "未连接") + "</small>"
    "<small>热点列表每 15 秒自动刷新</small>"
    "<script>"
    "(function(){"
    "var s=document.getElementById('ssid_select');"
    "var i=document.getElementById('ssid_input');"
    "if(s&&i){s.addEventListener('change',function(){if(this.value){i.value=this.value;}});}"
    "})();"
    "</script>"
    "</div></body></html>";
  configServer.send(200, "text/html", html);
}

void handleConfigSave() {
  if (!configServer.hasArg("ssid")) {
    configServer.send(400, "text/plain", "missing ssid");
    return;
  }

  String newSsid = configServer.arg("ssid");
  String newPass = configServer.arg("pass");
  newSsid.trim();

  if (newSsid.length() == 0) {
    configServer.send(400, "text/plain", "ssid is empty");
    return;
  }

  nvsWifiSsid = newSsid;
  nvsWifiPass = newPass;

  prefs.begin("device", false);
  prefs.putString("wifi_ssid", nvsWifiSsid);
  prefs.putString("wifi_pass", nvsWifiPass);
  prefs.end();

  String result =
    "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Saved</title><style>body{font-family:Arial,sans-serif;max-width:520px;margin:20px auto;padding:0 16px;}"
    ".ok{border:1px solid #cde;padding:16px;border-radius:10px;background:#f6fffa;}</style></head><body>"
    "<div class='ok'><h3>配置已保存</h3>"
    "<p>正在尝试连接: <b>" + nvsWifiSsid + "</b></p>"
    "<p>若连接成功，设备将退出配网页面并恢复正常业务。</p>"
    "</div></body></html>";
  configServer.send(200, "text/html", result);

  DEBUG_SERIAL.println("[SoftAP] Received WiFi config from web page");
  if (tryConnectWifi(nvsWifiSsid, nvsWifiPass, "SoftAP-Web")) {
    mqttClient.setServer(mqttServerStr.c_str(), mqttPortVal);
    mqttClient.setCallback(mqttCallback);
    reconnectMQTT();
    DEBUG_SERIAL.println("[SoftAP] WiFi connected, config portal closed");
  } else {
    DEBUG_SERIAL.println("[SoftAP] WiFi connect failed, keep config portal running");
    startSoftApConfigPortal();
  }
}

void checkSoftApManualTrigger() {
  bool pressed = (digitalRead(SOFTAP_TRIGGER_PIN) == SOFTAP_TRIGGER_ACTIVE_LEVEL);
  unsigned long now = millis();

  if (pressed) {
    if (!softApTriggerPressed) {
      softApTriggerPressed = true;
      softApTriggerPressStart = now;
      return;
    }

    if (!softApActive && (now - softApTriggerPressStart >= softApTriggerHoldMs)) {
      DEBUG_SERIAL.println("[SoftAP] Manual trigger detected, starting config portal...");
      softApTriggerPressed = false;
      softApTriggerPressStart = 0;
      startSmartConfig();
    }
  } else {
    softApTriggerPressed = false;
    softApTriggerPressStart = 0;
  }
}

/* *
 * 兼容入口：原 SmartConfig 接口改为 SoftAP 网页配网。 */
void startSmartConfig() {
  // 为兼容已有串口/MCP 命令名，保留此函数名，内部改为启动 SoftAP 配网页面
  startSoftApConfigPortal();
}

/* *
 * MQTT reconnect function */
void reconnectMQTT() {
  if (!wifiConnected) return;
  if (mqttClient.connected()) return;

  // 防刷屏：每 10 秒才允许一次物理重连尝试，防止在没网时狂刷
  if (millis() - lastMqttReconnectAttempt < 10000) return;
  lastMqttReconnectAttempt = millis();

  // 每次重连时重新设置 server（允许 set_config 修改 mqtt_server 后重连生效）
  mqttClient.setServer(mqttServerStr.c_str(), mqttPortVal);

  DEBUG_SERIAL.print("[MQTT] Attempting MQTT connection to ");
  DEBUG_SERIAL.print(mqttServerStr);
  DEBUG_SERIAL.print(":");
  DEBUG_SERIAL.println(mqttPortVal);

  // 注意：PubSubClient 的 connect() 会阻塞一小会儿；这里不 while 死循环，避免卡住主循环
  if (mqttClient.connect(mqtt_client_id)) {
    DEBUG_SERIAL.println("[MQTT] connected");
    mqttConnected = true;

    // Subscribe to topics（以 physical_exam_control.py 为准）
    mqttClient.subscribe(TOPIC_INSTRUMENT_DATA, 2);
    DEBUG_SERIAL.println("[MQTT] Subscribed to: " + String(TOPIC_INSTRUMENT_DATA));

    mqttClient.subscribe(TOPIC_UPLOAD_STATUS, 2);
    DEBUG_SERIAL.println("[MQTT] Subscribed to: " + String(TOPIC_UPLOAD_STATUS));
  } else {
    mqttConnected = false;
    DEBUG_SERIAL.print("[MQTT] connect failed, state=");
    DEBUG_SERIAL.println(mqttClient.state());
  }
}

/* *
 * Send heartbeat to MQTT */
void sendHeartbeat() {
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  
  if (mqttClient.connected()) {
    // 以 physical_exam_control.py 为准：状态/心跳统一发到 upload_status 主题
    // Python 端会订阅该主题（TOPICS['upload_status']）
    String message = "{\"device\":\"ESP32_PhysicalExam\",\"status\":\"alive\",\"timestamp\":" + String(millis() / 1000) + "}";
    publishToMQTT(TOPIC_UPLOAD_STATUS, message);
    DEBUG_SERIAL.println("[MQTT] Heartbeat sent to upload_status: " + message);
  }
}

/* *
 * MQTT message callback */
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  DEBUG_SERIAL.println("[MQTT] Received message on topic: " + String(topic));
  DEBUG_SERIAL.println("[MQTT] Message: " + message);
  
  if (String(topic) == TOPIC_INSTRUMENT_DATA) {
    // Parse JSON message
    DynamicJsonDocument doc(512);
    DeserializationError error = deserializeJson(doc, message);
    
    if (!error) {
      float height = doc["height"] | doc["height_cm"] | 0.0;
      float weight = doc["weight"] | doc["weight_kg"] | 0.0;
      String record_id = doc["record_id"] | "";
      
      if (height > 0 && weight > 0) {
        processPhysicalExam(height, weight, record_id);
      }
    }
  } else if (String(topic) == TOPIC_UPLOAD_STATUS) {
    // 这里主要用于对齐 python 端订阅行为，方便你看到“确实收到了状态类消息”
    DEBUG_SERIAL.println("[MQTT] (upload_status) received");
  }
}

/* *
 * Process serial data from instrument */
void processSerialData() {
  // 1) 读取仪器串口：按 606 帧拼包（参考 success.ino）
  if (SerialPort.available()) {
    while (SerialPort.available()) {
      uint8_t inByte = (uint8_t)SerialPort.read();

      if (inByte == FRAME_HEADER_RESP || inByte == FRAME_HEADER_SEND) {
        rxIndex = 0;
        rxBuffer[rxIndex++] = inByte;
      } else if (rxIndex > 0 && rxIndex < (int)sizeof(rxBuffer)) {
        rxBuffer[rxIndex++] = inByte;

        // 帧尾到达：尝试解析
        if (inByte == FRAME_TAIL && rxIndex >= 4) {
          receiveCount++;
          lastReceiveTime = millis();

          // ---- 解析并处理 ----
          uint8_t header = rxBuffer[0];
          uint8_t length = rxBuffer[1];
          uint8_t cmd = rxBuffer[2];
          uint8_t tail = rxBuffer[rxIndex - 1];

          // DEBUG_SERIAL.print("\n[");
          // DEBUG_SERIAL.print(millis() / 1000.0, 3);
          // DEBUG_SERIAL.print("s] RX #");
          // DEBUG_SERIAL.print(receiveCount);
          // DEBUG_SERIAL.println(":");

          // RAW HEX (注释掉这段原始数据输出，以免体检仪狂发心跳时造成串口刷屏)
          /*
          DEBUG_SERIAL.print("  RAW: ");
          for (int i = 0; i < rxIndex; i++) {
            if (rxBuffer[i] < 0x10) DEBUG_SERIAL.print("0");
            DEBUG_SERIAL.print(rxBuffer[i], HEX);
            DEBUG_SERIAL.print(" ");
          }
          DEBUG_SERIAL.println();
          */

          bool ok = true;
          if (header != FRAME_HEADER_RESP && header != FRAME_HEADER_SEND) ok = false;
          if (tail != FRAME_TAIL) ok = false;
          // length 字段：命令+数据长度；最小为1（只有cmd）
          if (length < 1) ok = false;

          if (!ok) {
            // DEBUG_SERIAL.println("  [!] Invalid 606 frame");
          } else {
            // DEBUG_SERIAL.print("  Type: ");
            // DEBUG_SERIAL.println(header == FRAME_HEADER_RESP ? "Response" : "Command");
            // DEBUG_SERIAL.print("  CMD: 0x");
            // DEBUG_SERIAL.println(cmd, HEX);

            // 解码常用命令（与 tests/test_serial.py / success.ino 对齐）
            // 在正常运行中，屏蔽接收到报文时的自动打印输出，避免刷屏和内存崩溃
            switch (cmd) {
              case 0x54: { // Version: payload[0]=major payload[1]=minor
                if (rxIndex >= 5) {
                  // DEBUG_SERIAL.print("  >> Version: V");
                  // DEBUG_SERIAL.print(rxBuffer[3]);
                  // DEBUG_SERIAL.print(".");
                  // DEBUG_SERIAL.println(rxBuffer[4]);
                }
                break;
              }
              case 0x41: { // Temperature & Humidity
                if (rxIndex >= 7) {
                  float temp = ((rxBuffer[3] << 8) | rxBuffer[4]) / 10.0;
                  float humi = ((rxBuffer[5] << 8) | rxBuffer[6]) / 10.0;
                  // DEBUG_SERIAL.print("  >> Temperature: ");
                  // DEBUG_SERIAL.print(temp);
                  // DEBUG_SERIAL.println(" C");
                  // DEBUG_SERIAL.print("  >> Humidity: ");
                  // DEBUG_SERIAL.print(humi);
                  // DEBUG_SERIAL.println(" %");
                }
                break;
              }
              case 0x42: { // Height
                if (rxIndex >= 6) {
                  float height = ((rxBuffer[3] << 8) | rxBuffer[4]) / 10.0;
                  uint8_t status = rxBuffer[5];
                  
                  if (status == 0x01 && height > 0 && height < 300) {
                    pending_height_cm = height;
                    pending_ts = millis();
                  }
                }
                break;
              }
              case 0x43: { // Weight
                if (rxIndex >= 6) {
                  float weight = ((rxBuffer[3] << 8) | rxBuffer[4]) / 10.0;
                  uint8_t status = rxBuffer[5];
                  
                  if (status == 0x01 && weight > 0 && weight < 300) {
                    pending_weight_kg = weight;
                    pending_ts = millis();
                  }
                }
                break;
              }
              case 0x47: { // Height & Weight
                if (rxIndex >= 9) {
                  float height = ((rxBuffer[3] << 8) | rxBuffer[4]) / 100.0;
                  uint8_t heightStatus = rxBuffer[5];
                  float weight = ((rxBuffer[6] << 8) | rxBuffer[7]) / 100.0;
                  uint8_t weightStatus = rxBuffer[8];

                  // 若两项都完成，则走现有业务流程（MQTT发布 + 小智播报）
                  if (heightStatus == 0x01 && weightStatus == 0x01 &&
                      height > 0 && height < 300 && weight > 0 && weight < 300) {
                    processPhysicalExam(height, weight, generateRecordId());
                    pending_height_cm = 0;
                    pending_weight_kg = 0;
                    pending_ts = 0;
                  } else {
                    // 也更新暂存，方便后续组合
                    if (heightStatus == 0x01) pending_height_cm = height;
                    if (weightStatus == 0x01) pending_weight_kg = weight;
                    pending_ts = millis();
                  }
                }
                break;
              }
              case 0x45: { // Vision
                if (rxIndex >= 7) {
                  float leftEye = ((rxBuffer[3] << 8) | rxBuffer[4]) / 10.0;
                  float rightEye = ((rxBuffer[5] << 8) | rxBuffer[6]) / 10.0;
                  // DEBUG_SERIAL.print("  >> Left Eye: ");
                  // DEBUG_SERIAL.println(leftEye);
                  // DEBUG_SERIAL.print("  >> Right Eye: ");
                  // DEBUG_SERIAL.println(rightEye);
                }
                break;
              }
              default:
                // DEBUG_SERIAL.println("  [!] Unknown command");
                break;
            }
          }

          // DEBUG_SERIAL.println();
          rxIndex = 0;
        }
      }
      delay(2);
    }
  }

  // 2) 若分别测得身高/体重“完成”，在短时间内凑齐也触发一次业务流程
  if (pending_height_cm > 0 && pending_weight_kg > 0) {
    if (millis() - pending_ts < 5000) {
      processPhysicalExam(pending_height_cm, pending_weight_kg, generateRecordId());
    }
    pending_height_cm = 0;
    pending_weight_kg = 0;
    pending_ts = 0;
  }

  // 3) 处理串口监视器输入的快捷指令（参考 success.ino）
  if (DEBUG_SERIAL.available()) {
    char cmd = (char)DEBUG_SERIAL.read();
    handleConsoleCommand(cmd);
  }
}

// ---------- 606指令发送与串口交互（移植自 success.ino） ----------
void send606Command(uint8_t cmd, uint8_t* data, int dataLen) {
  uint8_t buffer[256];
  int index = 0;

  buffer[index++] = FRAME_HEADER_SEND;
  buffer[index++] = (uint8_t)(1 + dataLen); // length = cmd + payload
  buffer[index++] = cmd;
  for (int i = 0; i < dataLen; i++) buffer[index++] = data[i];
  buffer[index++] = FRAME_TAIL;

  SerialPort.write(buffer, index);
  SerialPort.flush();
  sendCount++;

  DEBUG_SERIAL.print("\n[TX] CMD 0x");
  DEBUG_SERIAL.print(cmd, HEX);
  DEBUG_SERIAL.print(": ");
  for (int i = 0; i < index; i++) {
    if (buffer[i] < 0x10) DEBUG_SERIAL.print("0");
    DEBUG_SERIAL.print(buffer[i], HEX);
    DEBUG_SERIAL.print(" ");
  }
  DEBUG_SERIAL.println("\n");
}

void printSerialHelp() {
  DEBUG_SERIAL.println("\n========================================");
  DEBUG_SERIAL.println("Command List:");
  DEBUG_SERIAL.println("  1 - Read Version (0x54)");
  DEBUG_SERIAL.println("  2 - Get Temperature & Humidity (0x41)");
  DEBUG_SERIAL.println("  3 - Height Measurement (0x42)");
  DEBUG_SERIAL.println("  4 - Weight Measurement (0x43)");
  DEBUG_SERIAL.println("  5 - Height & Weight Measurement (0x47)");
  DEBUG_SERIAL.println("  6 - Vision Test (0x45)");
  DEBUG_SERIAL.println("  w - Start SoftAP WiFi portal (192.168.44.1)");
  DEBUG_SERIAL.println("  h - Show Help");
  DEBUG_SERIAL.println("  s - Show Statistics");
  DEBUG_SERIAL.println("  c - Clear Statistics");
  DEBUG_SERIAL.println("========================================\n");
}

void printSerialStats() {
  DEBUG_SERIAL.println("\n========================================");
  DEBUG_SERIAL.println("Statistics:");
  DEBUG_SERIAL.print("  RX Count: ");
  DEBUG_SERIAL.println(receiveCount);
  DEBUG_SERIAL.print("  TX Count: ");
  DEBUG_SERIAL.println(sendCount);
  DEBUG_SERIAL.print("  Uptime: ");
  DEBUG_SERIAL.print(millis() / 1000.0, 1);
  DEBUG_SERIAL.println(" sec");
  if (lastReceiveTime > 0) {
    DEBUG_SERIAL.print("  Last RX: ");
    DEBUG_SERIAL.print((millis() - lastReceiveTime) / 1000.0, 1);
    DEBUG_SERIAL.println(" sec ago");
  }
  DEBUG_SERIAL.println("========================================\n");
}

void handleConsoleCommand(char cmd) {
  switch (cmd) {
    case '1':
      DEBUG_SERIAL.println("-> Read Version");
      send606Command(0x54);
      break;
    case '2':
      DEBUG_SERIAL.println("-> Get Temperature & Humidity");
      send606Command(0x41);
      break;
    case '3':
      DEBUG_SERIAL.println("-> Start Height Measurement");
      send606Command(0x42);
      break;
    case '4':
      DEBUG_SERIAL.println("-> Start Weight Measurement");
      send606Command(0x43);
      break;
    case '5':
      DEBUG_SERIAL.println("-> Start Height & Weight Measurement");
      send606Command(0x47);
      break;
    case '6':
      DEBUG_SERIAL.println("-> Start Vision Test");
      send606Command(0x45);
      break;
    case 'h':
    case 'H':
      printSerialHelp();
      break;
    case 's':
    case 'S':
      printSerialStats();
      break;
    case 'c':
    case 'C':
      receiveCount = 0;
      sendCount = 0;
      DEBUG_SERIAL.println("[OK] Statistics cleared\n");
      break;
    case 'w':
    case 'W':
      DEBUG_SERIAL.println("-> Starting SoftAP config portal...");
      startSmartConfig();
      break;
    case '\n':
    case '\r':
      break;
    default:
      // 忽略其他字符（避免串口监视器自动发送换行等造成刷屏）
      break;
  }
}

/* *
 * Process physical exam data */
void processPhysicalExam(float height_cm, float weight_kg, String record_id) {
  if (height_cm <= 0 || weight_kg <= 0) {
    DEBUG_SERIAL.println("[Error] Invalid height or weight");
    return;
  }
  if (height_cm > 300 || weight_kg > 300) {
    DEBUG_SERIAL.println("[Error] Height or weight value abnormal");
    return;
  }
  
  float bmi = calculateBMI(height_cm, weight_kg);
  String advice = generateAdvice(bmi);
  String timestamp = getCurrentTimestamp();
  
  if (record_id.length() == 0) {
    record_id = generateRecordId();
  }
  
  // Store record
  ExamRecord record;
  record.height_cm = height_cm;
  record.weight_kg = weight_kg;
  record.bmi = bmi;
  record.advice = advice;
  record.timestamp = timestamp;
  record.record_id = record_id;
  
  exam_records[exam_record_index] = record;
  exam_record_index = (exam_record_index + 1) % 100;
  if (exam_record_count < 100) {
    exam_record_count++;
  }
  
  // Update last person data
  last_height = height_cm;
  last_weight = weight_kg;

  // 触发小智唤醒：输出 100ms 低电平脉冲到 GPIO47（接小智 GPIO38）
  digitalWrite(XIAOZHI_WAKEUP_PIN, LOW);
  delay(100);
  digitalWrite(XIAOZHI_WAKEUP_PIN, HIGH);
  DEBUG_SERIAL.println("[Wakeup] Trigger pulse sent on GPIO47 (LOW 100ms)");

  // Publish to MQTT（带防抖：MIN_PUBLISH_INTERVAL 内不重复发布）
  unsigned long now = millis();
  if (now - lastPublishTime >= MIN_PUBLISH_INTERVAL) {
    lastPublishTime = now;
    String mqttMsg = "{\"instrument_id\":\"" + instrumentId + 
                     "\",\"height\":" + String(height_cm) + 
                     ",\"weight\":" + String(weight_kg) + 
                     ",\"bmi\":" + String(bmi) + 
                     ",\"record_id\":\"" + record_id + "\"}";  
    publishToMQTT(TOPIC_INSTRUMENT_DATA, mqttMsg);

    // Generate TTS text and push to Xiaozhi
    String ttsText = "您的身高是" + String((int)height_cm) + "厘米，体重是" + String((int)weight_kg) + 
                     "公斤。BMI指数是" + String(bmi, 1) + "。" + advice;
    pushToXiaozhi(ttsText);

    DEBUG_SERIAL.println("[Process] Physical exam processed: " + mqttMsg);
    DEBUG_SERIAL.println("[Process] TTS: " + ttsText);
  } else {
    DEBUG_SERIAL.println("[MQTT] Publish skipped (cooldown " + String((MIN_PUBLISH_INTERVAL - (now - lastPublishTime)) / 1000) + "s remaining)");
  }
}

/* *
 * Calculate BMI */
float calculateBMI(float height_cm, float weight_kg) {
  float height_m = height_cm / 100.0;
  return weight_kg / (height_m * height_m);
}

/* *
 * Generate medical advice based on BMI */
String generateAdvice(float bmi) {
  if (bmi < 18.5) {
    return "您的体重偏轻，建议适当增加营养，保持健康饮食。";
  } else if (bmi < 24) {
    return "您的体重正常，请继续保持良好的生活习惯。";
  } else if (bmi < 28) {
    return "您的体重偏重，建议适当控制饮食，增加运动量。";
  } else {
    return "您的体重超标，建议咨询医生，制定合理的减肥计划。";
  }
}

/* *
 * Publish message to MQTT */
void publishToMQTT(const char* topic, String message) {
  if (mqttClient.connected()) {
    mqttClient.publish(topic, message.c_str());
    DEBUG_SERIAL.println("[MQTT] Published to " + String(topic) + ": " + message);
  } else {
    DEBUG_SERIAL.println("[MQTT] Not connected, cannot publish");
  }
}

/* *
 * Push TTS to Xiaozhi */
void pushToXiaozhi(String text) {
  String speakMsg = "{\"text\":\"" + text + "\",\"type\":\"manual\",\"timestamp\":\"" + getCurrentTimestamp() + "\"}";
  publishToMQTT(TOPIC_XIAOZHI_SPEAK, speakMsg);
}

/* *
 * Get current timestamp */
String getCurrentTimestamp() {
  // Simple timestamp (millis since boot)
  unsigned long seconds = millis() / 1000;
  unsigned long minutes = seconds / 60;
  unsigned long hours = minutes / 60;
  return String(hours) + ":" + String(minutes % 60) + ":" + String(seconds % 60);
}

/* *
 * Generate record ID */
String generateRecordId() {
  return "REC_" + String(millis());
}

/* *
 * MCP connection status change callback function */
void onMcpConnectionChange(bool connected) {
  mcpConnected = connected;
  if (connected) {
    DEBUG_SERIAL.println("[MCP] Connected to the MCP server");
    registerMcpTools();
  } else {
    DEBUG_SERIAL.println("[MCP] Disconnect from the MCP server");
  }
}

/* *
 * Register MCP Tools */
void registerMcpTools() {
  DEBUG_SERIAL.println("[MCP] Registering tools...");
  
  // Tool 1: process_physical_exam
  mcpClient.registerTool(
    "process_physical_exam",
    "处理体检身高体重数据并触发小智播报医学建议",
    "{\"type\":\"object\",\"properties\":{\"height_cm\":{\"type\":\"number\",\"description\":\"身高，单位厘米\"},\"weight_kg\":{\"type\":\"number\",\"description\":\"体重，单位公斤\"},\"record_id\":{\"type\":\"string\",\"description\":\"可选，体检记录ID\"}},\"required\":[\"height_cm\",\"weight_kg\"]}",
    [](const String& args) {
      DynamicJsonDocument doc(256);
      DeserializationError error = deserializeJson(doc, args);
      
      if (error) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"Invalid parameter format\"}", true);
      }
      
      float height = doc["height_cm"] | 0.0;
      float weight = doc["weight_kg"] | 0.0;
      String record_id = doc["record_id"] | "";
      
      if (height <= 0 || weight <= 0) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"身高和体重必须大于0\"}", true);
      }
      
      processPhysicalExam(height, weight, record_id);
      
      float bmi = calculateBMI(height, weight);
      String advice = generateAdvice(bmi);
      
      String result = "{\"success\":true,\"message\":\"已生成医学建议并触发小智播报\",\"bmi\":" + 
                       String(bmi, 1) + ",\"advice\":\"" + advice + "\"}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'process_physical_exam' registered");
  
  // Tool 2: xiaozhi_speak
  mcpClient.registerTool(
    "xiaozhi_speak",
    "远程让小智主动说话（播报指定文字）",
    "{\"type\":\"object\",\"properties\":{\"text\":{\"type\":\"string\",\"description\":\"要让小智播报的文字内容\"}},\"required\":[\"text\"]}",
    [](const String& args) {
      DynamicJsonDocument doc(256);
      DeserializationError error = deserializeJson(doc, args);
      
      if (error) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"Invalid parameter format\"}", true);
      }
      
      String text = doc["text"] | "";
      if (text.length() == 0) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"播报内容不能为空\"}", true);
      }
      
      pushToXiaozhi(text);
      
      String result = "{\"success\":true,\"message\":\"已发送播报指令\",\"tts_text\":\"" + text + "\"}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'xiaozhi_speak' registered");
  
  // Tool 3: get_exam_records
  mcpClient.registerTool(
    "get_exam_records",
    "获取最近的体检记录",
    "{\"type\":\"object\",\"properties\":{\"limit\":{\"type\":\"integer\",\"description\":\"返回记录数量，默认10条\",\"default\":10}},\"required\":[]}",
    [](const String& args) {
      DynamicJsonDocument doc(256);
      DeserializationError error = deserializeJson(doc, args);
      
      int limit = doc["limit"] | 10;
      if (limit <= 0) limit = 10;
      if (limit > exam_record_count) limit = exam_record_count;
      
      if (exam_record_count == 0) {
        return WebSocketMCP::ToolResponse("{\"success\":true,\"records\":[],\"message\":\"【重要限制】当前机器暂无历史测量记录，你必须如实告诉用户『暂无数据』，严禁瞎编或捏造任何数据！\"}", true);
      }
      
      String result = "{\"success\":true,\"records\":[";
      int startIndex = exam_record_count - limit;
      if (startIndex < 0) startIndex = 0;
      
      for (int i = startIndex; i < exam_record_count; i++) {
        if (i > startIndex) result += ",";
        ExamRecord& rec = exam_records[i];
        result += "{\"height_cm\":" + String(rec.height_cm) + 
                 ",\"weight_kg\":" + String(rec.weight_kg) + 
                 ",\"bmi\":" + String(rec.bmi, 1) + 
                 ",\"advice\":\"" + rec.advice + 
                 "\",\"timestamp\":\"" + rec.timestamp + 
                 "\",\"record_id\":\"" + rec.record_id + "\"}";
      }
      result += "],\"total_count\":" + String(exam_record_count) + 
                ",\"returned_count\":" + String(limit) + "}";
      
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'get_exam_records' registered");
  
  // Tool 4: get_mqtt_status
  mcpClient.registerTool(
    "get_mqtt_status",
    "获取 MQTT 连接状态和主题配置",
    "{\"type\":\"object\",\"properties\":{}}",
    [](const String& args) {
      String result = "{\"success\":true,\"mqtt_connected\":" + String(mqttClient.connected() ? "true" : "false") + 
                     ",\"topics\":{\"instrument_data\":\"" + String(TOPIC_INSTRUMENT_DATA) + 
                     "\",\"xiaozhi_speak\":\"" + String(TOPIC_XIAOZHI_SPEAK) + 
                     "\",\"upload_status\":\"" + String(TOPIC_UPLOAD_STATUS) + 
                     "\"},\"serial_enabled\":true,\"serial_baudrate\":" + String(SERIAL_BAUDRATE) + "}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'get_mqtt_status' registered");
  
  // Tool 5: start_serial_measurement
  mcpClient.registerTool(
    "start_serial_measurement",
    "通过串口发送开始测量指令（606协议）",
    "{\"type\":\"object\",\"properties\":{}}",
    [](const String& args) {
      // 发送 606 协议“身高体重开始测量”指令：0x47
      // 该指令在 success.ino / tests/test_serial.py 中已验证
      send606Command(0x47);
      
      String result = "{\"success\":true,\"message\":\"已通过串口发送测量指令\"}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'start_serial_measurement' registered");
  
  // Tool 6: get_last_person_height_weight
  mcpClient.registerTool(
    "get_last_person_height_weight",
    "获取最后一个人的身高体重数据并推送到服务器",
    "{\"type\":\"object\",\"properties\":{}}",
    [](const String& args) {
      if (last_height <= 0 || last_weight <= 0) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"暂无体检数据\",\"message\":\"【重要限制】当前机器暂无历史测量记录，你必须如实告诉用户『暂无数据』，严禁瞎编或捏造任何数据！\"}", true);
      }
      
      float bmi = calculateBMI(last_height, last_weight);
      String mqttMsg = "{\"instrument_id\":\"" + instrumentId + 
                       "\",\"height\":" + String(last_height) + 
                       ",\"weight\":" + String(last_weight) + 
                       ",\"bmi\":" + String(bmi, 1) + "}";
      publishToMQTT(TOPIC_INSTRUMENT_DATA, mqttMsg);
      lastPublishTime = millis();
      
      String result = "{\"success\":true,\"height_cm\":" + String(last_height) + 
                     ",\"weight_kg\":" + String(last_weight) + 
                     ",\"bmi\":" + String(bmi, 1) + 
                     ",\"message\":\"数据已推送到MQTT服务器\"}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'get_last_person_height_weight' registered");
  
  // Tool 7: set_instrument_id
  mcpClient.registerTool(
    "set_instrument_id",
    "远程设置身高体重仪序号（掉电不丢失，立即生效）",
    "{\"type\":\"object\",\"properties\":{\"instrument_id\":{\"type\":\"string\",\"description\":\"仪器序号，如 HW-001\"}},\"required\":[\"instrument_id\"]}",
    [](const String& args) {
      DynamicJsonDocument doc(128);
      if (deserializeJson(doc, args)) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"参数解析失败\"}", true);
      }
      String newId = doc["instrument_id"] | "";
      if (newId.length() == 0) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"instrument_id 不能为空\"}", true);
      }
      String oldId = instrumentId;
      instrumentId = newId;
      // 写入 NVS
      prefs.begin("device", false);  // false = 读写模式
      prefs.putString("instrument_id", instrumentId);
      prefs.end();
      DEBUG_SERIAL.println("[NVS] Instrument ID updated: " + oldId + " -> " + instrumentId);
      String result = "{\"success\":true,\"old_id\":\"" + oldId + "\",\"new_id\":\"" + instrumentId + "\",\"message\":\"仪器序号已更新并持久化保存\"}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'set_instrument_id' registered");

  // Tool 8: get_instrument_id
  mcpClient.registerTool(
    "get_instrument_id",
    "查询当前身高体重仪序号",
    "{\"type\":\"object\",\"properties\":{}}",
    [](const String& args) {
      String result = "{\"success\":true,\"instrument_id\":\"" + instrumentId + "\"}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'get_instrument_id' registered");

  // Tool 9: get_config — 查询所有远程可配置参数（当前运行时值）
  mcpClient.registerTool(
    "get_config",
    "查询 ESP32 所有当前运行时配置参数（WiFi/MQTT/发布间隔/仪器序号等）",
    "{\"type\":\"object\",\"properties\":{}}",
    [](const String& args) {
      String result = "{"
        "\"success\":true,"
        "\"config\":{"
          "\"instrument_id\":\"" + instrumentId + "\","
          "\"wifi_ssid\":\""     + wifiSsid     + "\","
          "\"wifi_pass\":\"***\","   // 不回显密码
          "\"mqtt_server\":\""  + mqttServerStr + "\","
          "\"mqtt_port\":"      + String(mqttPortVal) + ","
          "\"pub_interval_ms\":" + String(MIN_PUBLISH_INTERVAL) +
        "},"
        "\"runtime\":{"
          "\"wifi_connected\":"  + String(wifiConnected  ? "true" : "false") + ","
          "\"mqtt_connected\":"  + String(mqttClient.connected() ? "true" : "false") + ","
          "\"mcp_connected\":"   + String(mcpConnected   ? "true" : "false") + ","
          "\"uptime_sec\":"      + String(millis() / 1000) + ","
          "\"free_heap\":"       + String(ESP.getFreeHeap()) + ","
          "\"chip_model\":\""    + String(ESP.getChipModel()) + "\","
          "\"sdk_version\":\""   + String(ESP.getSdkVersion()) + "\","
          "\"exam_records\":"    + String(exam_record_count) +
        "}"
      "}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'get_config' registered");

  // Tool 10: set_config — 远程修改运行时配置并持久化到 NVS
  // 支持的 key: instrument_id / wifi_ssid / wifi_pass / mqtt_server / mqtt_port / pub_interval_ms
  // wifi_* 类修改需重启后生效；mqtt_* 类修改会立即重连；pub_interval_ms 立即生效
  mcpClient.registerTool(
    "set_config",
    "远程修改并持久化 ESP32 配置参数。支持: instrument_id / wifi_ssid / wifi_pass / mqtt_server / mqtt_port / pub_interval_ms",
    "{"
      "\"type\":\"object\","
      "\"properties\":{"
        "\"key\":{\"type\":\"string\",\"description\":\"配置键名\"},"
        "\"value\":{\"type\":\"string\",\"description\":\"新值（统一用字符串传入）\"}"
      "},"
      "\"required\":[\"key\",\"value\"]"
    "}",
    [](const String& args) {
      DynamicJsonDocument doc(256);
      if (deserializeJson(doc, args)) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"参数解析失败\"}", true);
      }
      String key   = doc["key"]   | "";
      String value = doc["value"] | "";
      if (key.length() == 0) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"key 不能为空\"}", true);
      }

      String restartHint = "false";
      prefs.begin("device", false);  // 读写模式

      if (key == "instrument_id") {
        instrumentId = value;
        prefs.putString("instrument_id", instrumentId);
      } else if (key == "wifi_ssid") {
        nvsWifiSsid = value;  // 写入 NVS 备用凭据，重启后作为额外候选
        prefs.putString("wifi_ssid", nvsWifiSsid);
        restartHint = "true";
      } else if (key == "wifi_pass") {
        nvsWifiPass = value;
        prefs.putString("wifi_pass", nvsWifiPass);
        restartHint = "true";
      } else if (key == "mqtt_server") {
        mqttServerStr = value;
        prefs.putString("mqtt_server", mqttServerStr);
        // 立即重连到新服务器
        mqttClient.disconnect();
        mqttClient.setServer(mqttServerStr.c_str(), mqttPortVal);
        reconnectMQTT();
      } else if (key == "mqtt_port") {
        mqttPortVal = value.toInt();
        if (mqttPortVal <= 0 || mqttPortVal > 65535) {
          prefs.end();
          return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"mqtt_port 无效，范围 1-65535\"}", true);
        }
        prefs.putInt("mqtt_port", mqttPortVal);
        mqttClient.disconnect();
        mqttClient.setServer(mqttServerStr.c_str(), mqttPortVal);
        reconnectMQTT();
      } else if (key == "pub_interval_ms") {
        unsigned long newInterval = (unsigned long)value.toInt();
        if (newInterval < 1000 || newInterval > 3600000) {
          prefs.end();
          return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"pub_interval_ms 范围 1000~3600000\"}", true);
        }
        MIN_PUBLISH_INTERVAL = newInterval;
        prefs.putULong("pub_interval", MIN_PUBLISH_INTERVAL);
      } else {
        prefs.end();
        return WebSocketMCP::ToolResponse(
          "{\"success\":false,\"error\":\"未知 key: " + key + "，支持: instrument_id/wifi_ssid/wifi_pass/mqtt_server/mqtt_port/pub_interval_ms\"}", true);
      }

      prefs.end();
      DEBUG_SERIAL.println("[NVS] Config updated: " + key + " = " + (key == "wifi_pass" ? "***" : value));

      String result = "{\"success\":true,\"key\":\"" + key + "\",\"value\":\"" +
                      (key == "wifi_pass" ? "***" : value) + "\"," +
                      "\"need_restart\":" + restartHint + "," +
                      "\"message\":\"配置已保存" + (restartHint == "true" ? "，重启后生效" : "，立即生效") + "\"}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'set_config' registered");

  // Tool 11: restart_device — 远程重启 ESP32（wifi/ota 更改配置后使用）
  mcpClient.registerTool(
    "restart_device",
    "远程重启 ESP32 设备（更改 WiFi 配置后需重启生效）",
    "{\"type\":\"object\",\"properties\":{\"confirm\":{\"type\":\"boolean\",\"description\":\"必须传 true 才会执行重启\"}},\"required\":[\"confirm\"]}",
    [](const String& args) {
      DynamicJsonDocument doc(64);
      if (deserializeJson(doc, args)) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"参数解析失败\"}", true);
      }
      bool confirm = doc["confirm"] | false;
      if (!confirm) {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"请传入 confirm=true 确认重启\"}", true);
      }
      DEBUG_SERIAL.println("[MCP] Remote restart triggered!");
      delay(500);
      ESP.restart();
      // unreachable
      return WebSocketMCP::ToolResponse("{\"success\":true,\"message\":\"设备正在重启...\"}");
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'restart_device' registered");

  // Tool 12: start_smartconfig — 远程触发 SoftAP 网页配网（保留旧工具名兼容）
  mcpClient.registerTool(
    "start_smartconfig",
    "触发 ESP32 进入 SoftAP 网页配网模式，连接热点后访问 192.168.44.1 配置 WiFi",
    "{\"type\":\"object\",\"properties\":{\"timeout_s\":{\"type\":\"integer\",\"description\":\"等待超时秒数，默认120，0=不超时\"}},\"required\":[]}",
    [](const String& args) {
      DynamicJsonDocument doc(64);
      deserializeJson(doc, args);
      int t = doc["timeout_s"] | CFG_SMARTCONFIG_TIMEOUT_S;
      // 临时修改超时（仅本次生效，不写 NVS）
      // 由于 CFG_SMARTCONFIG_TIMEOUT_S 是宏，用局部变量传递给阻塞函数比较繁琐；
      // 此处直接调用 startSmartConfig()（使用 config.h 中的超时值）
      // 若需动态超时可将 startSmartConfig 改为带参版本
      (void)t;
      DEBUG_SERIAL.println("[MCP] Remote SoftAP config portal triggered!");
      String preResult = "{\"success\":true,\"message\":\"SoftAP 配网页面已启动，请连接热点后访问 http://192.168.44.1\"}";
      // 注意：startSmartConfig 是阻塞函数，会暂停 MCP 通信直到配网完成或超时
      startSmartConfig();
      return WebSocketMCP::ToolResponse(preResult);
    }
  );
  DEBUG_SERIAL.println("[MCP] Tool 'start_smartconfig' registered");

  DEBUG_SERIAL.println("[MCP] All tools registered, total: " + String(mcpClient.getToolCount()) + " tools");
}

