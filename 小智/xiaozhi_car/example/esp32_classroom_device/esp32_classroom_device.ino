/*
 * ESP32-WROOM-32 MQTT消息接收器
 * 监听MQTT消息并通过RGB LED灯光回应
 * 
 * 功能：
 * - 连接WiFi和MQTT服务器
 * - 监听MQTT消息
 * - RGB LED灯光回应
 * - 发送状态反馈
 * 
 * 硬件连接：
 * - RGB LED红色：GPIO 25
 * - RGB LED绿色：GPIO 26
 * - RGB LED蓝色：GPIO 27
 * - 按钮：GPIO 5 (可选)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi配置
const char* ssid = "iot421";        // 修改为你的WiFi名称
const char* password = "REPLACE_ME"; // 修改为你的WiFi密码

// MQTT配置
const char* mqtt_server = "47.97.8.221";
const int mqtt_port = 1883;
const char* mqtt_client_id = "esp32-classroom-device";

// MQTT主题
const char* fan_topic = "classroom/fan/control";
const char* light_topic = "classroom/light/control";
const char* status_topic = "classroom/status";
const char* response_topic = "classroom/response";

// GPIO引脚定义
const int RGB_RED_PIN = 25;   // RGB LED红色引脚
const int RGB_GREEN_PIN = 26; // RGB LED绿色引脚
const int RGB_BLUE_PIN = 27;  // RGB LED蓝色引脚
const int BUTTON_PIN = 5;     // 按钮引脚（可选）

// 设备状态
struct DeviceState {
  bool mqtt_connected;
  unsigned long last_message_time;
  int message_count;
} device_state;

// 全局对象
WiFiClient espClient;
PubSubClient client(espClient);

// 函数声明
void setup_wifi();
void setup_mqtt();
void reconnect_mqtt();
void callback(char* topic, byte* payload, unsigned int length);
void publish_status();
void send_received_response();
void setup_rgb_led();
void rgb_led_off();
void rgb_led_flash();
void rgb_led_rainbow();

void setup() {
  Serial.begin(115200);
  Serial.println("\n=== ESP32-WROOM-32 MQTT消息接收器 ===");
  
  // 初始化GPIO
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  setup_rgb_led();
  
  // 初始化设备状态
  device_state.mqtt_connected = false;
  device_state.last_message_time = 0;
  device_state.message_count = 0;
  
  // 初始化完成
  
  // 设置WiFi和MQTT
  setup_wifi();
  setup_mqtt();
  
  Serial.println("设备初始化完成！");
}

void loop() {
  // 检查MQTT连接
  if (!client.connected()) {
    reconnect_mqtt();
  }
  client.loop();
  
  // 检查按钮（可选功能）
  static unsigned long last_button_check = 0;
  if (millis() - last_button_check > 100) {
    if (digitalRead(BUTTON_PIN) == LOW) {
      // 按钮按下，触发RGB LED测试
      Serial.println("🔘 按钮被按下，触发RGB LED测试");
      rgb_led_rainbow();
      delay(200); // 防抖
    }
    last_button_check = millis();
  }
  
  // 定期发送状态（每30秒）
  static unsigned long last_status_send = 0;
  if (millis() - last_status_send > 30000) {
    publish_status();
    last_status_send = millis();
  }
  
  delay(10);
}

void setup_wifi() {
  Serial.print("正在连接WiFi: ");
  Serial.println(ssid);
  
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi连接成功！");
    Serial.print("IP地址: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n❌ WiFi连接失败！");
  }
}

void setup_mqtt() {
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void reconnect_mqtt() {
  while (!client.connected()) {
    Serial.print("正在连接MQTT服务器...");
    
    if (client.connect(mqtt_client_id)) {
      Serial.println("\n✅ MQTT连接成功！");
      device_state.mqtt_connected = true;
      
      // 订阅主题
      client.subscribe(fan_topic);
      client.subscribe(light_topic);
      Serial.println("✅ 已订阅风扇和电灯控制主题");
      
      // 发送初始状态
      publish_status();
      
    } else {
      Serial.print("❌ MQTT连接失败，错误代码: ");
      Serial.print(client.state());
      Serial.println(" 5秒后重试...");
      device_state.mqtt_connected = false;
      delay(5000);
    }
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  // 将payload转换为字符串
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  Serial.print("📥 收到MQTT消息 - 主题: ");
  Serial.print(topic);
  Serial.print(", 内容: ");
  Serial.println(message);
  
  // 处理消息主题
  if (strcmp(topic, fan_topic) == 0) {
    // 处理风扇控制消息
    device_state.message_count++;
    device_state.last_message_time = millis();
    
    // 消息已收到，触发RGB LED闪烁
    rgb_led_flash();
    
    // 发送收到确认
    send_received_response();
    
    Serial.print("✅ 已处理风扇控制消息 #");
    Serial.println(device_state.message_count);
    
  } else if (strcmp(topic, light_topic) == 0) {
    // 处理电灯控制消息
    device_state.message_count++;
    device_state.last_message_time = millis();
    
    // 消息已收到，触发RGB LED闪烁
    rgb_led_flash();
    
    // 发送收到确认
    send_received_response();
    
    Serial.print("✅ 已处理电灯控制消息 #");
    Serial.println(device_state.message_count);
  }
  
  // 发送状态更新
  publish_status();
}


void publish_status() {
  if (!client.connected()) {
    Serial.println("❌ MQTT未连接，无法发送状态");
    return;
  }
  
  Serial.println("🔍 开始发送设备状态...");
  
  // 创建状态JSON
  DynamicJsonDocument doc(512);
  doc["device_id"] = mqtt_client_id;
  doc["timestamp"] = millis();
  doc["message_count"] = device_state.message_count;
  doc["last_message_time"] = device_state.last_message_time;
  doc["mqtt_connected"] = device_state.mqtt_connected;
  doc["wifi_connected"] = (WiFi.status() == WL_CONNECTED);
  doc["uptime"] = millis();
  
  String status_message;
  serializeJson(doc, status_message);
  
  Serial.print("📝 状态消息内容: ");
  Serial.println(status_message);
  
  // 发布状态
  bool result = client.publish(status_topic, status_message.c_str());
  if (result) {
    Serial.println("📤 ✅ 已发送状态到 classroom/status");
  } else {
    Serial.println("❌ 状态发送失败");
    Serial.print("MQTT状态: ");
    Serial.println(client.state());
  }
}

void send_received_response() {
  Serial.println("🔍 开始发送收到确认...");
  
  if (!client.connected()) {
    Serial.println("❌ MQTT未连接，无法发送确认");
    return;
  }
  
  Serial.print("✅ MQTT已连接，准备发送到主题: ");
  Serial.println(response_topic);
  
  // 创建收到确认消息
  DynamicJsonDocument doc(256);
  doc["device_id"] = mqtt_client_id;
  doc["status"] = "received";
  doc["message"] = "收到";
  doc["timestamp"] = millis();
  doc["message_count"] = device_state.message_count;
  
  String response_message;
  serializeJson(doc, response_message);
  
  Serial.print("📝 确认消息内容: ");
  Serial.println(response_message);
  
  // 发布收到确认
  bool result = client.publish(response_topic, response_message.c_str());
  if (result) {
    Serial.println("📤 ✅ 已发送收到确认到 classroom/response");
  } else {
    Serial.println("❌ 收到确认发送失败");
    Serial.print("MQTT状态: ");
    Serial.println(client.state());
  }
}

void setup_rgb_led() {
  // 初始化RGB LED引脚
  pinMode(RGB_RED_PIN, OUTPUT);
  pinMode(RGB_GREEN_PIN, OUTPUT);
  pinMode(RGB_BLUE_PIN, OUTPUT);
  
  // 关闭所有LED
  rgb_led_off();
  
  Serial.println("✅ RGB LED初始化完成");
}

void rgb_led_off() {
  // 关闭所有RGB LED
  digitalWrite(RGB_RED_PIN, LOW);
  digitalWrite(RGB_GREEN_PIN, LOW);
  digitalWrite(RGB_BLUE_PIN, LOW);
}

void rgb_led_flash() {
  Serial.println("🌈 RGB LED闪烁提示");
  
  // 闪烁3次，每次显示不同颜色
  for (int i = 0; i < 3; i++) {
    // 红色闪烁
    digitalWrite(RGB_RED_PIN, HIGH);
    delay(200);
    rgb_led_off();
    delay(100);
    
    // 绿色闪烁
    digitalWrite(RGB_GREEN_PIN, HIGH);
    delay(200);
    rgb_led_off();
    delay(100);
    
    // 蓝色闪烁
    digitalWrite(RGB_BLUE_PIN, HIGH);
    delay(200);
    rgb_led_off();
    delay(100);
  }
  
  Serial.println("✅ RGB LED闪烁完成");
}

void rgb_led_rainbow() {
  Serial.println("🌈 RGB LED彩虹效果");
  
  // 彩虹效果：红->绿->蓝->白->关闭
  for (int cycle = 0; cycle < 2; cycle++) {
    // 红色
    digitalWrite(RGB_RED_PIN, HIGH);
    delay(300);
    rgb_led_off();
    delay(100);
    
    // 绿色
    digitalWrite(RGB_GREEN_PIN, HIGH);
    delay(300);
    rgb_led_off();
    delay(100);
    
    // 蓝色
    digitalWrite(RGB_BLUE_PIN, HIGH);
    delay(300);
    rgb_led_off();
    delay(100);
    
    // 白色（三色同时亮）
    digitalWrite(RGB_RED_PIN, HIGH);
    digitalWrite(RGB_GREEN_PIN, HIGH);
    digitalWrite(RGB_BLUE_PIN, HIGH);
    delay(300);
    rgb_led_off();
    delay(100);
  }
  
  Serial.println("✅ RGB LED彩虹效果完成");
}
