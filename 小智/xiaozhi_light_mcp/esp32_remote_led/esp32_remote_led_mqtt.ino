/*
 * 远端 ESP32 RGB LED 控制程序 (MQTT 版本)
 * 通过 MQTT 接收来自 MCP Server 的指令，控制 RGB LED
 * 
 * 接线说明:
 *   GPIO 10 -> 220Ω -> RGB LED R
 *   GPIO 11 -> 220Ω -> RGB LED G  
 *   GPIO 12 -> 220Ω -> RGB LED B
 *   3.3V -> RGB LED 共阳极
 *   GND -> RGB LED GND
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <driver/ledc.h>

// ============================================================================
// WiFi 配置 - 两个备选 WiFi，ESP32 会自动选择可用的连接
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
// MQTT Broker 地址 (修改为你使用的 broker)
const char* mqtt_broker = "47.97.8.221";
const int mqtt_port = 1883;
const char* mqtt_username = NULL;    // 如果需要认证
const char* mqtt_password = NULL;    // 如果需要认证

// MQTT Topic
const char* topic_command = "xiaozhi/led/command";   // 订阅指令
const char* topic_status = "xiaozhi/led/status";     // 上报状态
const char* topic_heartbeat = "xiaozhi/led/heartbeat"; // 心跳

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// ============================================================================
// RGB LED GPIO 配置
// ============================================================================
#define RGB_LED_R GPIO_NUM_14   // D14
#define RGB_LED_G GPIO_NUM_12  // D12
#define RGB_LED_B GPIO_NUM_13  // D13

// LEDC 配置
#define LEDC_TIMER        LEDC_TIMER_0
#define LEDC_MODE         LEDC_LOW_SPEED_MODE
#define LEDC_DUTY_RES    LEDC_TIMER_13_BIT
#define LEDC_FREQ_HZ     1000
#define LEDC_MAX_DUTY    8191

ledc_channel_config_t channel_r, channel_g, channel_b;

// 状态变量
uint8_t current_r = 0, current_g = 0, current_b = 0;
uint8_t brightness = 100;

// LED 效果
enum LedEffect {
    EFFECT_NONE,
    EFFECT_BLINK,
    EFFECT_BREATHE,
    EFFECT_RAINBOW,
    EFFECT_FLASH
};
LedEffect current_effect = EFFECT_NONE;
unsigned long effect_start_time = 0;
int effect_duration = 1000;

// ============================================================================
// 函数声明
// ============================================================================
void initRGBLed();
void setRGBColor(uint8_t r, uint8_t g, uint8_t b);
void turnOffLed();
void setBrightness(uint8_t bright);
void updateLedDuty();
void processMqttCommand(const char* payload, unsigned int len);
void runLedEffect();
void initWiFi();
void initMqtt();
void reconnectMqtt();
void publishStatus();
void publishHeartbeat();

// ============================================================================
// 初始化 RGB LED
// ============================================================================
void initRGBLed() {
    ledc_timer_config_t timer = {};
    timer.speed_mode = LEDC_MODE;
    timer.timer_num = LEDC_TIMER;
    timer.duty_resolution = LEDC_DUTY_RES;
    timer.freq_hz = LEDC_FREQ_HZ;
    timer.clk_cfg = LEDC_AUTO_CLK;
    ESP_ERROR_CHECK(ledc_timer_config(&timer));

    channel_r.channel = LEDC_CHANNEL_0;
    channel_r.duty = 0;
    channel_r.gpio_num = RGB_LED_R;
    channel_r.speed_mode = LEDC_MODE;
    channel_r.hpoint = 0;
    channel_r.timer_sel = LEDC_TIMER;
    ESP_ERROR_CHECK(ledc_channel_config(&channel_r));

    channel_g.channel = LEDC_CHANNEL_1;
    channel_g.duty = 0;
    channel_g.gpio_num = RGB_LED_G;
    channel_g.speed_mode = LEDC_MODE;
    channel_g.hpoint = 0;
    channel_g.timer_sel = LEDC_TIMER;
    ESP_ERROR_CHECK(ledc_channel_config(&channel_g));

    channel_b.channel = LEDC_CHANNEL_2;
    channel_b.duty = 0;
    channel_b.gpio_num = RGB_LED_B;
    channel_b.speed_mode = LEDC_MODE;
    channel_b.hpoint = 0;
    channel_b.timer_sel = LEDC_TIMER;
    ESP_ERROR_CHECK(ledc_channel_config(&channel_b));

    Serial.println("RGB LED initialized on GPIO 10, 11, 12");
}

// ============================================================================
// 更新 LED Duty (共阴极模式)
// ============================================================================
void updateLedDuty() {
    if (current_effect != EFFECT_NONE) return;
    
    float factor = brightness / 100.0f;
    
    // 共阴极: r=255 时 LED 最亮，Duty 越大 LED 越亮
    uint32_t duty_r = (uint32_t)(current_r * factor * 32.0f);
    uint32_t duty_g = (uint32_t)(current_g * factor * 32.0f);
    uint32_t duty_b = (uint32_t)(current_b * factor * 32.0f);
    
    if (duty_r > LEDC_MAX_DUTY) duty_r = LEDC_MAX_DUTY;
    if (duty_g > LEDC_MAX_DUTY) duty_g = LEDC_MAX_DUTY;
    if (duty_b > LEDC_MAX_DUTY) duty_b = LEDC_MAX_DUTY;
    
    ESP_ERROR_CHECK(ledc_set_duty(channel_r.speed_mode, channel_r.channel, duty_r));
    ESP_ERROR_CHECK(ledc_set_duty(channel_g.speed_mode, channel_g.channel, duty_g));
    ESP_ERROR_CHECK(ledc_set_duty(channel_b.speed_mode, channel_b.channel, duty_b));
    
    ESP_ERROR_CHECK(ledc_update_duty(channel_r.speed_mode, channel_r.channel));
    ESP_ERROR_CHECK(ledc_update_duty(channel_g.speed_mode, channel_g.channel));
    ESP_ERROR_CHECK(ledc_update_duty(channel_b.speed_mode, channel_b.channel));
}

// ============================================================================
// 设置 RGB 颜色
// ============================================================================
void setRGBColor(uint8_t r, uint8_t g, uint8_t b) {
    current_r = r;
    current_g = g;
    current_b = b;
    current_effect = EFFECT_NONE;
    
    Serial.printf("Set RGB: R=%d, G=%d, B=%d\n", r, g, b);
    updateLedDuty();
}

// ============================================================================
// 关闭 LED
// ============================================================================
void turnOffLed() {
    current_r = 0;
    current_g = 0;
    current_b = 0;
    current_effect = EFFECT_NONE;
    
    ESP_ERROR_CHECK(ledc_set_duty(channel_r.speed_mode, channel_r.channel, 0));
    ESP_ERROR_CHECK(ledc_set_duty(channel_g.speed_mode, channel_g.channel, 0));
    ESP_ERROR_CHECK(ledc_set_duty(channel_b.speed_mode, channel_b.channel, 0));
    
    ESP_ERROR_CHECK(ledc_update_duty(channel_r.speed_mode, channel_r.channel));
    ESP_ERROR_CHECK(ledc_update_duty(channel_g.speed_mode, channel_g.channel));
    ESP_ERROR_CHECK(ledc_update_duty(channel_b.speed_mode, channel_b.channel));
    
    Serial.println("LED turned off");
}

// ============================================================================
// 设置亮度
// ============================================================================
void setBrightness(uint8_t bright) {
    brightness = constrain(bright, 0, 100);
    Serial.printf("Brightness: %d%%\n", brightness);
    updateLedDuty();
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
        publishStatus();  // 上报状态
    }
    else if (type == "brightness") {
        uint8_t bright = doc["value"] | 100;
        setBrightness(bright);
        publishStatus();
    }
    else if (type == "effect") {
        String effect = doc["effect"].as<String>();
        effect_duration = doc["duration"] | 1000;
        
        if (effect == "blink") {
            current_effect = EFFECT_BLINK;
            effect_start_time = millis();
            Serial.println("Effect: BLINK");
        }
        else if (effect == "breathe") {
            current_effect = EFFECT_BREATHE;
            effect_start_time = millis();
            Serial.println("Effect: BREATHE");
        }
        else if (effect == "rainbow") {
            current_effect = EFFECT_RAINBOW;
            effect_start_time = millis();
            Serial.println("Effect: RAINBOW");
        }
        else if (effect == "flash") {
            current_effect = EFFECT_FLASH;
            effect_start_time = millis();
            Serial.println("Effect: FLASH");
        }
        publishStatus();
    }
    else if (type == "off") {
        turnOffLed();
        publishStatus();
    }
}

// ============================================================================
// 运行 LED 效果
// ============================================================================
void runLedEffect() {
    if (current_effect == EFFECT_NONE) return;
    
    unsigned long elapsed = millis() - effect_start_time;
    if (elapsed > effect_duration && effect_duration > 0) {
        turnOffLed();
        return;
    }
    
    float factor = brightness / 100.0f;
    uint32_t duty = 0;
    
    switch (current_effect) {
        case EFFECT_BLINK: {
            bool on = (millis() / 500) % 2 == 0;
            if (on) duty = (uint32_t)(LEDC_MAX_DUTY * factor);
            ESP_ERROR_CHECK(ledc_set_duty(channel_r.speed_mode, channel_r.channel, duty));
            ESP_ERROR_CHECK(ledc_set_duty(channel_g.speed_mode, channel_g.channel, duty));
            ESP_ERROR_CHECK(ledc_set_duty(channel_b.speed_mode, channel_b.channel, duty));
            break;
        }
        
        case EFFECT_BREATHE: {
            float t = millis() / 1000.0f;
            float sin_val = (sin(t * 3.14159 * 2) + 1) / 2;
            duty = (uint32_t)(LEDC_MAX_DUTY * factor * sin_val);
            ESP_ERROR_CHECK(ledc_set_duty(channel_r.speed_mode, channel_r.channel, duty));
            ESP_ERROR_CHECK(ledc_set_duty(channel_g.speed_mode, channel_g.channel, duty));
            ESP_ERROR_CHECK(ledc_set_duty(channel_b.speed_mode, channel_b.channel, duty));
            break;
        }
        
        case EFFECT_RAINBOW: {
            float t = millis() / 500.0f;
            uint8_t r = (sin(t) + 1) / 2 * 255;
            uint8_t g = (sin(t + 2.094) + 1) / 2 * 255;
            uint8_t b = (sin(t + 4.188) + 1) / 2 * 255;
            
            // 共阴极
            duty = (uint32_t)(r * 32.0f * factor);
            ESP_ERROR_CHECK(ledc_set_duty(channel_r.speed_mode, channel_r.channel, duty));
            duty = (uint32_t)(g * 32.0f * factor);
            ESP_ERROR_CHECK(ledc_set_duty(channel_g.speed_mode, channel_g.channel, duty));
            duty = (uint32_t)(b * 32.0f * factor);
            ESP_ERROR_CHECK(ledc_set_duty(channel_b.speed_mode, channel_b.channel, duty));
            break;
        }
        
        case EFFECT_FLASH: {
            bool on = (millis() / 100) % 2 == 0;
            if (on) duty = LEDC_MAX_DUTY;
            ESP_ERROR_CHECK(ledc_set_duty(channel_r.speed_mode, channel_r.channel, duty));
            ESP_ERROR_CHECK(ledc_set_duty(channel_g.speed_mode, channel_g.channel, duty));
            ESP_ERROR_CHECK(ledc_set_duty(channel_b.speed_mode, channel_b.channel, duty));
            break;
        }
        
        default:
            break;
    }
    
    ESP_ERROR_CHECK(ledc_update_duty(channel_r.speed_mode, channel_r.channel));
    ESP_ERROR_CHECK(ledc_update_duty(channel_g.speed_mode, channel_g.channel));
    ESP_ERROR_CHECK(ledc_update_duty(channel_b.speed_mode, channel_b.channel));
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
    
    // 生成唯一的 client ID
    String clientId = "ESP32_LED_";
    clientId += String(random(0xffff), HEX);
    
    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", 
                  mqtt_broker, mqtt_port, clientId.c_str());
    
    // 如果有用户名密码
    if (mqtt_username && mqtt_password) {
        mqttClient.connect(clientId.c_str(), mqtt_username, mqtt_password);
    } else {
        mqttClient.connect(clientId.c_str());
    }
    
    if (mqttClient.connected()) {
        Serial.println("[MQTT] Connected!");
        mqttClient.subscribe(topic_command);
        Serial.printf("[MQTT] Subscribed to: %s\n", topic_command);
        
        // 发布上线状态
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
    doc["r"] = current_r;
    doc["g"] = current_g;
    doc["b"] = current_b;
    doc["brightness"] = brightness;
    doc["effect"] = current_effect;
    doc["uptime"] = millis() / 1000;
    
    char buffer[256];
    serializeJson(doc, buffer);
    
    mqttClient.publish(topic_status, buffer);
    Serial.printf("[MQTT] Status published: %s\n", buffer);
}

// ============================================================================
// 发布心跳
// ============================================================================
void publishHeartbeat() {
    if (!mqttClient.connected()) return;
    
    StaticJsonDocument<128> doc;
    doc["status"] = "online";
    doc["ip"] = WiFi.localIP().toString();
    doc["rssi"] = WiFi.RSSI();
    doc["uptime"] = millis() / 1000;
    
    char buffer[128];
    serializeJson(doc, buffer);
    
    mqttClient.publish(topic_heartbeat, buffer);
}

// ============================================================================
// Arduino Setup
// ============================================================================
void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println();
    Serial.println("========================================");
    Serial.println("  Remote ESP32 RGB LED (MQTT)");
    Serial.println("========================================");
    
    // 初始化 LED
    initRGBLed();
    
    // 初始化 WiFi
    initWiFi();
    
    // 初始化 MQTT
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
    // 保持 MQTT 连接
    if (!mqttClient.connected()) {
        static unsigned long last_mqtt_reconnect = 0;
        if (millis() - last_mqtt_reconnect > 5000) {
            last_mqtt_reconnect = millis();
            Serial.println("[MQTT] Reconnecting...");
            reconnectMqtt();
        }
    }
    mqttClient.loop();
    
    // 运行 LED 效果
    runLedEffect();
    
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
    
    // 定期发送心跳 (每 60 秒)
    static unsigned long last_heartbeat = 0;
    if (millis() - last_heartbeat > 60000) {
        last_heartbeat = millis();
        publishHeartbeat();
    }
    
    delay(10);
}
