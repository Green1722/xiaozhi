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
const int mqtt_port = 1883;                   // MQTT端口
const char* mqtt_client_id = "ESP32_SmartSwitch";   // MQTT客户端ID
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

// Smart switch pin definition
const int SWITCH_PINS[] = {1, 2, 3, 4, 5, 6};  // Switch input pins
const int RELAY_PINS[] = {21, 45, 46, 38, 39, 40};  // Relay output pin
bool relayStates[6] = {false, false, false, false, false, false};  // Relay status
unsigned long lastDebounceTime[6] = {0};  // Last anti-shake time
const unsigned long debounceDelay = 50;  // Anti-shake delay (milliseconds)

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
    String message = "{\"device\":\"ESP32_SmartSwitch\",\"status\":\"alive\",\"timestamp\":" + String(millis() / 1000) + "}";
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

// Relay control function
void controlRelay(int relayIndex, bool state) {
  if (relayIndex >= 0 && relayIndex < 6) {
    relayStates[relayIndex] = state;
    digitalWrite(RELAY_PINS[relayIndex], state ? HIGH : LOW);
    Serial.printf("[Relay] Control relay %d: %s\n", relayIndex + 1, state ? "open" : "close");
  }
}

// Check switch status
void checkSwitches() {
  for (int i = 0; i < 6; i++) {
    int switchState = digitalRead(SWITCH_PINS[i]);
    unsigned long currentTime = millis();

    // Anti-shake treatment
    if (switchState != relayStates[i] && (currentTime - lastDebounceTime[i] > debounceDelay)) {
      lastDebounceTime[i] = currentTime;
      // The switch is active low
      if (switchState == LOW) {
        controlRelay(i, !relayStates[i]);
      }
    }
  }
}

// Register MCP Tools
void registerMcpTools() {
  // Register Relay Control Tool
  mcpClient.registerTool(
    "relay_control",
    "Control six-channel relay",
    "{\"type\":\"object\",\"properties\":{\"relayIndex\":{\"type\":\"integer\",\"minimum\":1,\"maximum\":6},\"state\":{\"type\":\"boolean\"}},\"required\":[\"relayIndex\",\"state\"]}",
    [](const String& args) {
      DynamicJsonDocument doc(256);
      deserializeJson(doc, args);
      
      int relayIndex = doc["relayIndex"].as<int>() - 1;  // Convert to 0-based index
      bool state = doc["state"].as<bool>();
      
      if (relayIndex >= 0 && relayIndex < 6) {
        controlRelay(relayIndex, state);
        return WebSocketMCP::ToolResponse("{\"success\":true,\"relayIndex\":" + String(relayIndex + 1) + ",\"state\":" + (state ? "true" : "false") + "}");
      } else {
        return WebSocketMCP::ToolResponse("{\"success\":false,\"error\":\"Invalid relay index\"}", true);
      }
    }
  );
  Serial.println("[MCP] Relay Control Tool Registered");

  // Register relay status query tool
  mcpClient.registerTool(
    "relay_status",
    "Query the status of six relays",
    "{\"type\":\"object\",\"properties\":{}}",
    [](const String& args) {
      String result = "{\"success\":true,\"relays\":[";
      for (int i = 0; i < 6; i++) {
        if (i > 0) result += ",";
        result += "{\"index\":" + String(i + 1) + ",\"state\":" + (relayStates[i] ? "true" : "false") + "}";
      }
      result += "]}";
      return WebSocketMCP::ToolResponse(result);
    }
  );
  Serial.println("[MCP] Relay status query tool registered");
}

void setup() {
  Serial.begin(115200);

  // Initialize LED pin
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Initialize switch pin (input pull-up)
  for (int i = 0; i < 6; i++) {
    pinMode(SWITCH_PINS[i], INPUT_PULLUP);
  }

  // Initialize relay pin (output, initial shutdown)
  for (int i = 0; i < 6; i++) {
    pinMode(RELAY_PINS[i], OUTPUT);
    digitalWrite(RELAY_PINS[i], LOW);
    relayStates[i] = false;
  }

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
  
  // Check switch status
  checkSwitches();
  
  delay(10);
}

