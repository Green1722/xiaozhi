#include <WiFi.h>
#include <WebSocketMCP.h>
#include <PubSubClient.h>
#include <WiFiClient.h>

#define LED_BUILTIN 2

// WiFi configuration
const char* ssid = "iot421_5G";
const char* password = "REPLACE_ME";

// MCP server configuration
const char* mcpEndpoint = "ws://your-mcp-server:port/path";

// MQTT server configuration
const char* mqtt_server = "47.97.8.221";      // MQTT服务器地址
const int mqtt_port = 1883;                    // MQTT端口
const char* mqtt_client_id = "ESP32_Client"; // MQTT客户端ID
const char* mqtt_heartbeat_topic = "esp32/heartbeat";  // 心跳主题

// Create instances
WebSocketMCP mcpClient;
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// LED blink control
bool wifiConnected = false;
unsigned long lastHeartbeatTime = 0;
const unsigned long heartbeatInterval = 30000;  // 30秒 = 30000毫秒
unsigned long lastLedBlinkTime = 0;
const unsigned long ledBlinkInterval = 500;   // LED闪烁间隔500ms
bool ledState = false;

// MQTT reconnect function
void reconnectMQTT() {
  // Loop until we're reconnected
  while (!mqttClient.connected()) {
    Serial.print("[MQTT] Attempting MQTT connection...");
    // Attempt to connect
    if (mqttClient.connect(mqtt_client_id)) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

// Send heartbeat to MQTT
void sendHeartbeat() {
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  
  if (mqttClient.connected()) {
    String message = "{\"device\":\"ESP32\",\"status\":\"alive\",\"timestamp\":" + String(millis() / 1000) + "}";
    mqttClient.publish(mqtt_heartbeat_topic, message.c_str());
    Serial.println("[MQTT] Heartbeat sent: " + message);
  }
}

// Connection status callback function
void onConnectionStatus(bool connected) {
  if (connected) {
    Serial.println("[MCP] Connected to the server");
    // Register tool after successful connection
    registerMcpTools();
  } else {
    Serial.println("[MCP] Disconnect from the server");
  }
}

// Register MCP Tools
void registerMcpTools() {
  // Register a simple LED control tool
  mcpClient.registerTool(
    "led_blink",
    "Control ESP32 onboard LEDs",
    "{\"type\":\"object\",\"properties\":{\"state\":{\"type\":\"string\",\"enum\":[\"on\",\"off\",\"blink\"]}},\"required\":[\"state\"]}",
    [](const String& args) {
      DynamicJsonDocument doc(256);
      deserializeJson(doc, args);
      String state = doc["state"].as<String>();
      
      if (state == "on") {
        digitalWrite(LED_BUILTIN, HIGH);
      } else if (state == "off") {
        digitalWrite(LED_BUILTIN, LOW);
      } else if (state == "blink") {
        for (int i = 0; i < 5; i++) {
          digitalWrite(LED_BUILTIN, HIGH);
          delay(200);
          digitalWrite(LED_BUILTIN, LOW);
          delay(200);
        }
      }
      
      return WebSocketMCP::ToolResponse("{\"success\":true,\"state\":\"" + state + "\"}");
    }
  );
  Serial.println("[MCP] LED Control Tool Registered");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Connect to WiFi
  Serial.print("Connect to WiFi:");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  wifiConnected = true;
  Serial.println("WiFi is connected");
  Serial.println("IP address:" + WiFi.localIP().toString());

  // Initialize MQTT client
  mqttClient.setServer(mqtt_server, mqtt_port);
  reconnectMQTT();

  // Initialize the MCP client
  mcpClient.begin(mcpEndpoint, onConnectionStatus);
  
  lastHeartbeatTime = millis();
  lastLedBlinkTime = millis();
}

void loop() {
  // Handle MCP client events
  mcpClient.loop();
  
  // Check WiFi connection status
  bool currentWifiStatus = (WiFi.status() == WL_CONNECTED);
  if (currentWifiStatus != wifiConnected) {
    wifiConnected = currentWifiStatus;
    if (!wifiConnected) {
      Serial.println("[WiFi] Connection lost!");
      digitalWrite(LED_BUILTIN, LOW);  // WiFi断开时关闭LED
    } else {
      Serial.println("[WiFi] Reconnected!");
      reconnectMQTT();
    }
  }
  
  // LED闪烁控制（仅在WiFi连接时闪烁）
  if (wifiConnected) {
    unsigned long currentTime = millis();
    if (currentTime - lastLedBlinkTime >= ledBlinkInterval) {
      lastLedBlinkTime = currentTime;
      ledState = !ledState;
      digitalWrite(LED_BUILTIN, ledState ? HIGH : LOW);
    }
  } else {
    // WiFi未连接时，LED不闪烁（保持关闭状态）
    digitalWrite(LED_BUILTIN, LOW);
  }
  
  // MQTT心跳发送（每30秒）
  if (wifiConnected && mqttClient.connected()) {
    unsigned long currentTime = millis();
    if (currentTime - lastHeartbeatTime >= heartbeatInterval) {
      lastHeartbeatTime = currentTime;
      sendHeartbeat();
    }
  }
  
  // Handle MQTT client
  if (wifiConnected) {
    mqttClient.loop();
  }
  
  delay(10);
}

