/*
 * 远端 ESP32 RGB LED 控制程序 (共阴极版本)
 * 使用高低电平控制 LED 亮灭
 * 
 * 接线说明 (共阴极 RGB LED):
 *   GPIO 14 -> 220Ω -> RGB LED R (红色)
 *   GPIO 12 -> 220Ω -> RGB LED G (绿色)  
 *   GPIO 13 -> 220Ω -> RGB LED B (蓝色)
 *   GND -> RGB LED 共阴极 (最长脚)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============================================================================
// WiFi 配置 - 三个备选 WiFi，ESP32 会自动选择可用的连接
// ============================================================================
struct WiFiConfig {
    const char* ssid;
    const char* password;
};

WiFiConfig wifi_list[] = {
    {"iPhone", "REPLACE_ME"},           // 方案 1
    {"MIO_TAKAMIYA", "REPLACE_ME"},     // 方案 2
    {"iot421", "REPLACE_ME"}         // 方案 3
};
#define WIFI_COUNT (sizeof(wifi_list) / sizeof(wifi_list[0]))

String current_ssid = "";

// ============================================================================
// MQTT 配置
// ============================================================================
const char* mqtt_broker = "47.97.8.221";
const int mqtt_port = 1883;
const char* mqtt_username = NULL;
const char* mqtt_password = NULL;

// MQTT Topic
const char* topic_command = "xiaozhi/led/command";
const char* topic_status = "xiaozhi/led/status";

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// ============================================================================
// RGB LED GPIO 配置 (共阴极)
// ============================================================================
#define RGB_LED_R 14   // D14
#define RGB_LED_G 12   // D12
#define RGB_LED_B 13   // D13

// 预设颜色 RGB 值 (共阴极: HIGH=灭, LOW=亮)
struct RGB {
    uint8_t r, g, b;
};

RGB preset_colors[] = {
    {255, 255, 255},  // 0: 白色
    {255, 0, 0},      // 1: 红色
    {0, 255, 0},      // 2: 绿色
    {0, 0, 255},      // 3: 蓝色
    {255, 255, 0},    // 4: 黄色
    {255, 0, 255},    // 5: 紫色
    {0, 255, 255},    // 6: 青色
    {255, 165, 0}     // 7: 橙色
};

String current_color = "off";

// ============================================================================
// 初始化 RGB LED (数字输出模式)
// ============================================================================
void initRGBLed() {
    pinMode(RGB_LED_R, OUTPUT);
    pinMode(RGB_LED_G, OUTPUT);
    pinMode(RGB_LED_B, OUTPUT);
    
    // 共阴极: 初始为熄灭 (HIGH)
    digitalWrite(RGB_LED_R, HIGH);
    digitalWrite(RGB_LED_G, HIGH);
    digitalWrite(RGB_LED_B, HIGH);
    
    Serial.println("RGB LED initialized on GPIO 14, 12, 13 (共阴极)");
}

// ============================================================================
// 设置 RGB 颜色 (共阴极: HIGH=亮, LOW=灭)
// ============================================================================
void setRGBColor(uint8_t r, uint8_t g, uint8_t b) {
    // 共阴极: HIGH=亮, LOW=灭
    digitalWrite(RGB_LED_R, r > 127 ? HIGH : LOW);
    digitalWrite(RGB_LED_G, g > 127 ? HIGH : LOW);
    digitalWrite(RGB_LED_B, b > 127 ? HIGH : LOW);
    
    Serial.printf("Set RGB: R=%d, G=%d, B=%d\n", r, g, b);
}

// ============================================================================
// 关闭 LED
// ============================================================================
void turnOffLed() {
    digitalWrite(RGB_LED_R, HIGH);
    digitalWrite(RGB_LED_G, HIGH);
    digitalWrite(RGB_LED_B, HIGH);
    current_color = "off";
    Serial.println("LED turned off");
}

// ============================================================================
// 处理 MQTT 命令
// ============================================================================
void processMqttCommand(const char* payload, unsigned int len) {
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, payload);
    
    if (error) {
        Serial.printf("JSON parse error: %s\n", error.c_str());
        return;
    }
    
    String type = doc["type"].as<String>();
    
    if (type == "rgb") {
        uint8_t r = doc["r"] | 0;
        uint8_t g = doc["g"] | 0;
        uint8_t b = doc["b"] | 0;
        setRGBColor(r, g, b);
        
        // 更新颜色名称
        if (r == 0 && g == 0 && b == 0) {
            current_color = "off";
        } else if (r > 200 && g > 200 && b > 200) {
            current_color = "white";
        } else if (r > 200 && g < 50 && b < 50) {
            current_color = "red";
        } else if (r < 50 && g > 200 && b < 50) {
            current_color = "green";
        } else if (r < 50 && g < 50 && b > 200) {
            current_color = "blue";
        } else if (r > 200 && g > 200 && b < 50) {
            current_color = "yellow";
        } else if (r > 200 && g < 50 && b > 200) {
            current_color = "purple";
        } else if (r < 50 && g > 200 && b > 200) {
            current_color = "cyan";
        } else if (r > 200 && g > 100 && b < 50) {
            current_color = "orange";
        } else {
            current_color = "custom";
        }
        
        publishStatus();
    }
    else if (type == "off") {
        turnOffLed();
        publishStatus();
    }
}

// ============================================================================
// 初始化 WiFi
// ============================================================================
void initWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(false);
    
    Serial.println("========================================");
    Serial.println("  Searching for available WiFi...");
    Serial.println("========================================");
    
    for (int i = 0; i < WIFI_COUNT; i++) {
        Serial.printf("\n[Trying %d/%d] %s\n", i + 1, WIFI_COUNT, wifi_list[i].ssid);
        
        WiFi.begin(wifi_list[i].ssid, wifi_list[i].password);
        
        int attempts = 0;
        while (WiFi.status() != WL_CONNECTED && attempts < 30) {
            delay(500);
            Serial.print(".");
            attempts++;
        }
        
        if (WiFi.status() == WL_CONNECTED) {
            current_ssid = wifi_list[i].ssid;
            Serial.println("\n");
            Serial.println("========================================");
            Serial.println("  WiFi Connected!");
            Serial.println("========================================");
            Serial.printf("  SSID: %s\n", WiFi.SSID().c_str());
            Serial.printf("  IP:   %s\n", WiFi.localIP().toString().c_str());
            Serial.printf("  RSSI: %d dBm\n", WiFi.RSSI());
            Serial.println("========================================");
            return;
        } else {
            Serial.println(" [Failed]");
            WiFi.disconnect();
            delay(100);
        }
    }
    
    Serial.println("\n!!! All WiFi connections failed !!!");
}

// ============================================================================
// MQTT 回调函数
// ============================================================================
void mqttCallback(char* topic, byte* payload, unsigned int len) {
    Serial.printf("[MQTT] Message on %s: ", topic);
    for (unsigned int i = 0; i < len; i++) {
        Serial.print((char)payload[i]);
    }
    Serial.println();
    
    if (strcmp(topic, topic_command) == 0) {
        processMqttCommand((const char*)payload, len);
    }
}

// ============================================================================
// 初始化 MQTT
// ============================================================================
void initMqtt() {
    mqttClient.setServer(mqtt_broker, mqtt_port);
    mqttClient.setCallback(mqttCallback);
    
    reconnectMqtt();
}

// ============================================================================
// 重连 MQTT
// ============================================================================
void reconnectMqtt() {
    if (WiFi.status() != WL_CONNECTED) return;
    
    String clientId = "ESP32_LED_";
    clientId += String(random(0xffff), HEX);
    
    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", 
                  mqtt_broker, mqtt_port, clientId.c_str());
    
    if (mqtt_username && mqtt_password) {
        mqttClient.connect(clientId.c_str(), mqtt_username, mqtt_password);
    } else {
        mqttClient.connect(clientId.c_str());
    }
    
    if (mqttClient.connected()) {
        Serial.println("[MQTT] Connected!");
        mqttClient.subscribe(topic_command);
        Serial.printf("[MQTT] Subscribed to: %s\n", topic_command);
        
        publishStatus();
    } else {
        Serial.printf("[MQTT] Connection failed, rc=%d\n", mqttClient.state());
    }
}

// ============================================================================
// 发布状态
// ============================================================================
void publishStatus() {
    if (!mqttClient.connected()) return;
    
    StaticJsonDocument<256> doc;
    doc["status"] = "ok";
    doc["ip"] = WiFi.localIP().toString();
    doc["color"] = current_color;
    doc["uptime"] = millis() / 1000;
    
    char buffer[256];
    serializeJson(doc, buffer);
    
    mqttClient.publish(topic_status, buffer);
    Serial.printf("[MQTT] Status published: %s\n", buffer);
}

// ============================================================================
// Arduino Setup
// ============================================================================
void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println();
    Serial.println("========================================");
    Serial.println("  Remote ESP32 RGB LED (共阴极)");
    Serial.println("========================================");
    
    initRGBLed();
    initWiFi();
    initMqtt();
    
    Serial.println();
    Serial.println("Ready! Waiting for MQTT commands...");
    Serial.printf("Broker: %s:%d\n", mqtt_broker, mqtt_port);
    Serial.printf("Topic:  %s\n", topic_command);
}

// ============================================================================
// Arduino Loop
// ============================================================================
void loop() {
    if (!mqttClient.connected()) {
        static unsigned long last_mqtt_reconnect = 0;
        if (millis() - last_mqtt_reconnect > 5000) {
            last_mqtt_reconnect = millis();
            Serial.println("[MQTT] Reconnecting...");
            reconnectMqtt();
        }
    }
    mqttClient.loop();
    
    // WiFi 重连逻辑
    static unsigned long last_wifi_check = 0;
    if (millis() - last_wifi_check > 5000) {
        last_wifi_check = millis();
        
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("WiFi disconnected!");
            
            for (int i = 0; i < WIFI_COUNT; i++) {
                if (current_ssid.length() > 0 && 
                    String(wifi_list[i].ssid) == current_ssid) {
                    continue;
                }
                
                Serial.printf("Trying: %s\n", wifi_list[i].ssid);
                WiFi.disconnect();
                delay(100);
                WiFi.begin(wifi_list[i].ssid, wifi_list[i].password);
                
                for (int j = 0; j < 20; j++) {
                    delay(500);
                    if (WiFi.status() == WL_CONNECTED) {
                        current_ssid = wifi_list[i].ssid;
                        Serial.printf("Connected to: %s\n", current_ssid.c_str());
                        Serial.printf("New IP: %s\n", WiFi.localIP().toString());
                        reconnectMqtt();
                        break;
                    }
                }
                if (WiFi.status() == WL_CONNECTED) break;
            }
        }
    }
    
    delay(10);
}
