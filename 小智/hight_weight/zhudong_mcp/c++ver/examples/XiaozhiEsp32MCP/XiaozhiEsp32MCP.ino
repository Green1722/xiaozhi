
#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketMCP.h>
#include <PubSubClient.h>
#include <WiFiClient.h>

/* ********* Configuration Items ************ */
// WiFi settings
const char* WIFI_SSID = "iot421_5G";
const char* WIFI_PASS = "REPLACE_ME";

// WebSocket MCP server address
const char* MCP_ENDPOINT = "REPLACE_ME";

// MQTT server configuration
const char* mqtt_server = "47.97.8.221";      // MQTT服务器地址
const int mqtt_port = 1883;                   // MQTT端口
const char* mqtt_client_id = "ESP32_Xiaozhi"; // MQTT客户端ID
const char* mqtt_heartbeat_topic = "esp32/heartbeat";  // 心跳主题

// Debugging information
#define DEBUG_SERIAL Serial
#define DEBUG_BAUD_RATE 115200

// LED control pin definition (for status indicators and tool control)
#define LED_PIN 2  // ESP32 onboard LED

/* ******* Global variables ********** */
WebSocketMCP mcpClient;
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Buffer Management
#define MAX_INPUT_LENGTH 1024
char inputBuffer[MAX_INPUT_LENGTH];
int inputBufferIndex = 0;
bool newCommandAvailable = false;

// Connection status
bool wifiConnected = false;
bool mcpConnected = false;

// LED blink control
unsigned long lastHeartbeatTime = 0;
const unsigned long heartbeatInterval = 30000;  // 30秒 = 30000毫秒
unsigned long lastLedBlinkTime = 0;
const unsigned long ledBlinkInterval = 500;   // LED闪烁间隔500ms
bool ledState = false;

/* ********* Function declaration *************** */
void setupWifi();
void onMcpOutput(const String &message);
void onMcpError(const String &error);
void onMcpConnectionChange(bool connected);
void processSerialCommands();
void blinkLed(int times, int delayMs);
void registerMcpTools();
void reconnectMQTT();
void sendHeartbeat();
void printHelp();
void printStatus();

void setup() {
  // Initialize the serial port
  DEBUG_SERIAL.begin(DEBUG_BAUD_RATE);
  DEBUG_SERIAL.println("\n\n[ESP32 MCP Client] Initialization...");
  
  // Initialize LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  // Connect to WiFi
  setupWifi();
  
  // Initialize MQTT client
  if (wifiConnected) {
    mqttClient.setServer(mqtt_server, mqtt_port);
    reconnectMQTT();
  }
  
  // Initialize the MCP client
  if (mcpClient.begin(MCP_ENDPOINT, onMcpConnectionChange)) {
    DEBUG_SERIAL.println("[ESP32 MCP Client] Initialization was successful, trying to connect to the MCP server...");
  } else {
    DEBUG_SERIAL.println("[ESP32 MCP Client] Initialization failed!");
  }
  
  lastHeartbeatTime = millis();
  lastLedBlinkTime = millis();
  
  // Show help information
  DEBUG_SERIAL.println("\nInstructions for use:");
  DEBUG_SERIAL.println("- Enter the command through the serial console and enter the carriage to send");
  DEBUG_SERIAL.println("- Messages received from the MCP server will be displayed on the serial console");
  DEBUG_SERIAL.println("- Input");
  DEBUG_SERIAL.println();
}

void loop() {
  // Handle MCP clients
  mcpClient.loop();
  
  // Process commands from the serial port
  processSerialCommands();
  
  // Check WiFi connection status
  bool currentWifiStatus = (WiFi.status() == WL_CONNECTED);
  if (currentWifiStatus != wifiConnected) {
    wifiConnected = currentWifiStatus;
    if (!wifiConnected) {
      DEBUG_SERIAL.println("[WiFi] Connection lost!");
      digitalWrite(LED_PIN, LOW);  // WiFi断开时关闭LED
    } else {
      DEBUG_SERIAL.println("[WiFi] Reconnected!");
      reconnectMQTT();
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
    // WiFi未连接时，LED不闪烁（保持关闭状态）
    digitalWrite(LED_PIN, LOW);
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
}

/* *
 * MQTT reconnect function */
void reconnectMQTT() {
  // Loop until we're reconnected
  while (!mqttClient.connected() && wifiConnected) {
    DEBUG_SERIAL.print("[MQTT] Attempting MQTT connection...");
    // Attempt to connect
    if (mqttClient.connect(mqtt_client_id)) {
      DEBUG_SERIAL.println("connected");
    } else {
      DEBUG_SERIAL.print("failed, rc=");
      DEBUG_SERIAL.print(mqttClient.state());
      DEBUG_SERIAL.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

/* *
 * Send heartbeat to MQTT */
void sendHeartbeat() {
  if (!mqttClient.connected()) {
    reconnectMQTT();
  }
  
  if (mqttClient.connected()) {
    String message = "{\"device\":\"ESP32_Xiaozhi\",\"status\":\"alive\",\"timestamp\":" + String(millis() / 1000) + "}";
    mqttClient.publish(mqtt_heartbeat_topic, message.c_str());
    DEBUG_SERIAL.println("[MQTT] Heartbeat sent: " + message);
  }
}

/* *
 * Set up WiFi connection */
void setupWifi() {
  DEBUG_SERIAL.print("[WiFi] Connect to");
  DEBUG_SERIAL.println(WIFI_SSID);
  
  // Start Connecting
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  
  // Waiting for connection
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    DEBUG_SERIAL.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    DEBUG_SERIAL.println();
    DEBUG_SERIAL.println("[WiFi] Connection is successful!");
    DEBUG_SERIAL.print("[WiFi] IP address:");
    DEBUG_SERIAL.println(WiFi.localIP());
  } else {
    wifiConnected = false;
    DEBUG_SERIAL.println();
    DEBUG_SERIAL.println("[WiFi] Connection failed! Will continue to try...");
  }
}

/* *
 * MCP output callback function (stdout substitution) */
void onMcpOutput(const String &message) {
  DEBUG_SERIAL.print("[MCP output]");
  DEBUG_SERIAL.println(message);
}

/* *
 * MCP error callback function (stderr substitute) */
void onMcpError(const String &error) {
  DEBUG_SERIAL.print("[MCP Error]");
  DEBUG_SERIAL.println(error);
}

/* *
 * Register MCP Tool
 * Register the tool after the connection is successful */
void registerMcpTools() {
  DEBUG_SERIAL.println("[MCP] Registration Tool...");
  
  // Register LED Control Tool
  mcpClient.registerTool(
    "led_blink",  // Tool name
    "Control the status of ESP32 LEDs", // Tool Description
    "{\"properties\":{\"state\":{\"title\":\"LED状态\",\"type\":\"string\",\"enum\":[\"on\",\"off\",\"blink\"]}},\"required\":[\"state\"],\"title\":\"ledControlArguments\",\"type\":\"object\"}",  // Enter schema
    [](const String& args) {
      // Analyze parameters
      DEBUG_SERIAL.println("[Tools] LED control:" + args);
      DynamicJsonDocument doc(256);
      DeserializationError error = deserializeJson(doc, args);
      
      if (error) {
        // Return an error response
        WebSocketMCP::ToolResponse response("{\"success\":false,\"error\":\"Invalid parameter format\"}", true);
        return response;
      }
      
      String state = doc["state"].as<String>();
      DEBUG_SERIAL.println("[Tools] LED control:" + state);
      
      // Control LED
      if (state == "on") {
        digitalWrite(LED_PIN, HIGH);
      } else if (state == "off") {
        digitalWrite(LED_PIN, LOW);
      } else if (state == "blink") {
        // Here you can trigger the flashing mode
        // For simplicity, we just switched the LED state a few times
        for (int i = 0; i < 5; i++) {
          digitalWrite(LED_PIN, HIGH);
          delay(200);
          digitalWrite(LED_PIN, LOW);
          delay(200);
        }
      }
      
      // Return a successful response
      String resultJson = "{\"success\":true,\"state\":\"" + state + "\"}";
      return WebSocketMCP::ToolResponse(resultJson);
    }
  );
  DEBUG_SERIAL.println("[MCP] LED Control Tool Registered");
  
  // Register system information tool
  mcpClient.registerTool(
    "system-info",
    "Obtain ESP32 system information",
    "{\"properties\":{},\"title\":\"systemInfoArguments\",\"type\":\"object\"}",
    [](const String& args) {
      DEBUG_SERIAL.println("[Get ESP32 system information:" + args);
      // Collect system information
      String chipModel = ESP.getChipModel();
      uint32_t chipId = ESP.getEfuseMac() & 0xFFFFFFFF;
      uint32_t flashSize = ESP.getFlashChipSize() / 1024;
      uint32_t freeHeap = ESP.getFreeHeap() / 1024;
      
      // Constructing JSON response
      String resultJson = "{\"success\":true,\"model\":\"" + chipModel + "\",\"chipId\":\"" + String(chipId, HEX) + 
                         "\",\"flashSize\":" + String(flashSize) + ",\"freeHeap\":" + String(freeHeap) + 
                         ",\"wifiStatus\":\"" + (WiFi.status() == WL_CONNECTED ? "connected" : "disconnected") + 
                         "\",\"ipAddress\":\"" + WiFi.localIP().toString() + "\"}";
      
      return WebSocketMCP::ToolResponse(resultJson);
    }
  );
  DEBUG_SERIAL.println("[MCP] System Information Tool Registered");
  
  // Register Calculator Tool (Simple Example)
  mcpClient.registerTool(
    "calculator",
    "Simple calculator",
    "{\"properties\":{\"expression\":{\"title\":\"表达式\",\"type\":\"string\"}},\"required\":[\"expression\"],\"title\":\"calculatorArguments\",\"type\":\"object\"}",
    [](const String& args) {
       DEBUG_SERIAL.println("[Simple calculator:" + args);
      DynamicJsonDocument doc(256);
      deserializeJson(doc, args);
      
      String expr = doc["expression"].as<String>();
      DEBUG_SERIAL.println("[Tools] Calculator:" + expr);
      
      // This is just a demonstration, and expression calculations need to be implemented in actual applications
      // We only deal with simple addition and subtraction
      int result = 0;
      if (expr.indexOf("+") > 0) {
        int plusPos = expr.indexOf("+");
        int a = expr.substring(0, plusPos).toInt();
        int b = expr.substring(plusPos + 1).toInt();
        result = a + b;
      } else if (expr.indexOf("-") > 0) {
        int minusPos = expr.indexOf("-");
        int a = expr.substring(0, minusPos).toInt();
        int b = expr.substring(minusPos + 1).toInt();
        result = a - b;
      }
      
      String resultJson = "{\"success\":true,\"expression\":\"" + expr + "\",\"result\":" + String(result) + "}";
      return WebSocketMCP::ToolResponse(resultJson);
    }
  );
  DEBUG_SERIAL.println("[MCP] Calculator Tool Registered");
  
  DEBUG_SERIAL.println("[MCP] Tool registration is completed, total" + String(mcpClient.getToolCount()) + "A tool");
}

/* *
 * MCP connection status change callback function */
void onMcpConnectionChange(bool connected) {
  mcpConnected = connected;
  if (connected) {
    DEBUG_SERIAL.println("[MCP] Connected to the MCP server");
    // Register tool after successful connection
    registerMcpTools();
  } else {
    DEBUG_SERIAL.println("[MCP] Disconnect from the MCP server");
  }
}

/* *
 * Process commands from the serial port */
void processSerialCommands() {
  // Check whether there is serial port data
  while (DEBUG_SERIAL.available() > 0) {
    char inChar = (char)DEBUG_SERIAL.read();
    
    // Handle carriage return or line break
    if (inChar == '\n' || inChar == '\r') {
      if (inputBufferIndex > 0) {
        // Add string ending character
        inputBuffer[inputBufferIndex] = '\0';
        
        // Processing commands
        String command = String(inputBuffer);
        command.trim();
        
        if (command.length() > 0) {
          if (command == "help") {
            printHelp();
          } else if (command == "status") {
            printStatus();
          } else if (command == "reconnect") {
            DEBUG_SERIAL.println("Reconnecting...");
            mcpClient.disconnect();
          } else if (command == "tools") {
            // Show registered tools
            DEBUG_SERIAL.println("Number of registered tools:" + String(mcpClient.getToolCount()));
          } else {
            // Send commands to MCP server (stdin instead)
            if (mcpClient.isConnected()) {
              mcpClient.sendMessage(command);
              DEBUG_SERIAL.println("[Send]" + command);
            } else {
              DEBUG_SERIAL.println("Not connected to the MCP server, unable to send commands");
            }
          }
        }
        
        // Reset the buffer
        inputBufferIndex = 0;
      }
    } 
    // Process backspace key
    else if (inChar == '\b' || inChar == 127) {
      if (inputBufferIndex > 0) {
        inputBufferIndex--;
        DEBUG_SERIAL.print("\b \b"); // Backspace, space, backspace
      }
    }
    // Handle ordinary characters
    else if (inputBufferIndex < MAX_INPUT_LENGTH - 1) {
      inputBuffer[inputBufferIndex++] = inChar;
      DEBUG_SERIAL.print(inChar); // Echo
    }
  }
}

/* *
 * Print help information */
void printHelp() {
  DEBUG_SERIAL.println("Available commands:");
  DEBUG_SERIAL.println("help - Show this help information");
  DEBUG_SERIAL.println("status - display the current connection status");
  DEBUG_SERIAL.println("reconnect - Reconnect to the MCP server");
  DEBUG_SERIAL.println("tools - View registered tools");
  DEBUG_SERIAL.println("Any other text will be sent directly to the MCP server");
}

/* *
 * Print the current status */
void printStatus() {
  DEBUG_SERIAL.println("Current status:");
  DEBUG_SERIAL.print("  WiFi: ");
  DEBUG_SERIAL.println(wifiConnected ? "Connected" : "Not connected");
  if (wifiConnected) {
    DEBUG_SERIAL.print("  IP address: ");
    DEBUG_SERIAL.println(WiFi.localIP());
    DEBUG_SERIAL.print("  Signal strength: ");
    DEBUG_SERIAL.println(WiFi.RSSI());
  }
  DEBUG_SERIAL.print("  MCP Server: ");
  DEBUG_SERIAL.println(mcpConnected ? "Connected" : "Not connected");
  DEBUG_SERIAL.print("  MQTT Server: ");
  DEBUG_SERIAL.print(mqtt_server);
  DEBUG_SERIAL.print(":");
  DEBUG_SERIAL.print(mqtt_port);
  DEBUG_SERIAL.print(" - ");
  DEBUG_SERIAL.println(mqttClient.connected() ? "Connected" : "Not connected");
}

/* *
 * LED flashing function */
void blinkLed(int times, int delayMs) {
  static int blinkCount = 0;
  static unsigned long lastBlinkTime = 0;
  static bool ledState = false;
  static int lastTimes = 0;

  if (times == 0) {
    digitalWrite(LED_PIN, LOW);
    blinkCount = 0;
    lastTimes = 0;
    return;
  }
  if (lastTimes != times) {
    blinkCount = 0;
    lastTimes = times;
    ledState = false;
    lastBlinkTime = millis();
  }
  unsigned long now = millis();
  if (blinkCount < times * 2) {
    if (now - lastBlinkTime > delayMs) {
      lastBlinkTime = now;
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState ? HIGH : LOW);
      blinkCount++;
    }
  } else {
    digitalWrite(LED_PIN, LOW);
    blinkCount = 0;
    lastTimes = 0;
  }
}

