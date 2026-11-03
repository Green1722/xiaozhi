/**
 * @file mqtt_mcp_tools_register.cc
 * @brief 注册 MQTT MCP 工具到 MCP Server
 * 
 * 将 MQTT 功能作为 MCP 工具暴露给云端大模型
 */

#include "mqtt_mcp_tools.h"
#include "mcp_server.h"

#include "esp_log.h"
#include "cJSON.h"

#define TAG "MCP_MQTT"

// 获取全局 MQTT 工具实例
static MqttMcpTools& GetMqttTools() {
    return MqttMcpTools::GetInstance();
}

/**
 * @brief 注册所有 MQTT MCP 工具
 */
void RegisterMqttMcpTools() {
    auto& mcp_server = McpServer::GetInstance();
    auto& mqtt_tools = GetMqttTools();

    // 初始化 MQTT 工具
    mqtt_tools.Initialize();

    ESP_LOGI(TAG, "开始注册 MQTT MCP 工具...");

    // ============================================
    // 工具1: 发布 MQTT 消息
    // self.mqtt.publish
    // ============================================
    mcp_server.AddTool(
        "self.mqtt.publish",
        
        // 工具描述 - 告诉 AI 这个工具的作用
        "Publish a message to a specified MQTT topic. "
        "Use this tool to send commands, status updates, or data to other IoT devices, "
        "home automation systems (like HomeAssistant), sensors, or servers. "
        "Parameters: "
        "  - topic: The MQTT topic to publish to (e.g., 'home/lights/bedroom'). "
        "  - message: The message content (can be plain text or JSON). "
        "  - retain (optional): Whether to retain the message on broker (default: false). "
        "  - qos (optional): Quality of Service 0-2 (default: 1). "
        "Example: Publish '{\"state\":\"on\"}' to 'home/lights/bedroom'.",

        // 参数定义
        PropertyList({
            Property("topic", kPropertyTypeString, 
                     "The MQTT topic to publish to (e.g., 'home/lights/bedroom')"),
            Property("message", kPropertyTypeString, 
                     "The message content to send (plain text or JSON)"),
            Property("retain", kPropertyTypeBoolean, 
                     "Whether to retain the message on the MQTT broker", false),
            Property("qos", kPropertyTypeInteger, 0, 2, 
                     "Quality of Service level: 0=at most once, 1=at least once, 2=exactly once", 1)
        }),

        // 工具执行回调
        [&mqtt_tools](const PropertyList& properties) -> ReturnValue {
            // 获取参数
            std::string topic = properties["topic"].value<std::string>();
            std::string message = properties["message"].value<std::string>();
            bool retain = properties["retain"].value<bool>();
            int qos = properties["qos"].value<int>();

            ESP_LOGI(TAG, "MCP调用: self.mqtt.publish");
            ESP_LOGI(TAG, "  Topic:   %s", topic.c_str());
            ESP_LOGI(TAG, "  Message: %s", message.c_str());
            ESP_LOGI(TAG, "  QoS:     %d, Retain: %s", qos, retain ? "true" : "false");

            // 执行发布
            bool success = mqtt_tools.Publish(topic, message, retain, qos);

            if (success) {
                // 返回成功结果
                cJSON* result = cJSON_CreateObject();
                cJSON_AddStringToObject(result, "status", "published");
                cJSON_AddStringToObject(result, "topic", topic.c_str());
                cJSON_AddNumberToObject(result, "qos", qos);
                cJSON_AddBoolToObject(result, "retain", retain);
                cJSON_AddNumberToObject(result, "message_length", (double)message.length());
                return result;
            } else {
                throw std::runtime_error("Failed to publish MQTT message. "
                                         "Check network connection and MQTT broker.");
            }
        }
    );

    // ============================================
    // 工具2: 订阅 MQTT Topic
    // self.mqtt.subscribe
    // ============================================
    mcp_server.AddTool(
        "self.mqtt.subscribe",
        
        "Subscribe to an MQTT topic to receive messages from other devices or servers. "
        "Use this to listen for commands from home automation systems (HomeAssistant, Node-RED), "
        "or to receive data from sensors. "
        "Supports MQTT wildcards: '+' for single level, '#' for multi-level. "
        "Example: Subscribe to 'home/+/lights/#' to receive all light-related messages. "
        "Parameters: "
        "  - topic: The topic pattern to subscribe to. "
        "  - qos (optional): Quality of Service 0-2 (default: 1).",

        PropertyList({
            Property("topic", kPropertyTypeString, 
                     "The MQTT topic pattern to subscribe to (supports wildcards: + for single level, # for multi-level)"),
            Property("qos", kPropertyTypeInteger, 0, 2, 
                     "Quality of Service level (default: 1)", 1)
        }),

        [&mqtt_tools](const PropertyList& properties) -> ReturnValue {
            std::string topic = properties["topic"].value<std::string>();
            int qos = properties["qos"].value<int>();

            ESP_LOGI(TAG, "MCP调用: self.mqtt.subscribe - Topic: %s, QoS: %d", 
                      topic.c_str(), qos);

            bool success = mqtt_tools.Subscribe(topic, qos);

            if (success) {
                cJSON* result = cJSON_CreateObject();
                cJSON_AddStringToObject(result, "status", "subscribed");
                cJSON_AddStringToObject(result, "topic", topic.c_str());
                cJSON_AddNumberToObject(result, "qos", qos);
                cJSON_AddStringToObject(result, "message", 
                    "Successfully subscribed. Use self.mqtt.get_messages to retrieve received messages.");
                return result;
            } else {
                throw std::runtime_error("Failed to subscribe. Check MQTT connection.");
            }
        }
    );

    // ============================================
    // 工具3: 取消订阅
    // self.mqtt.unsubscribe
    // ============================================
    mcp_server.AddTool(
        "self.mqtt.unsubscribe",
        
        "Unsubscribe from a previously subscribed MQTT topic. "
        "Use this to stop receiving messages from a topic. "
        "Parameters: "
        "  - topic: The topic pattern to unsubscribe from.",

        PropertyList({
            Property("topic", kPropertyTypeString, 
                     "The MQTT topic pattern to unsubscribe from")
        }),

        [&mqtt_tools](const PropertyList& properties) -> ReturnValue {
            std::string topic = properties["topic"].value<std::string>();

            ESP_LOGI(TAG, "MCP调用: self.mqtt.unsubscribe - Topic: %s", topic.c_str());

            bool success = mqtt_tools.Unsubscribe(topic);

            if (success) {
                cJSON* result = cJSON_CreateObject();
                cJSON_AddStringToObject(result, "status", "unsubscribed");
                cJSON_AddStringToObject(result, "topic", topic.c_str());
                return result;
            } else {
                throw std::runtime_error("Topic was not subscribed.");
            }
        }
    );

    // ============================================
    // 工具4: 获取消息历史
    // self.mqtt.get_messages
    // ============================================
    mcp_server.AddTool(
        "self.mqtt.get_messages",
        
        "Get recent messages received from subscribed MQTT topics. "
        "Use this to check what messages have been received recently, "
        "retrieve specific messages for processing, or check sensor data. "
        "Messages are stored in a local cache (max 100 messages). "
        "Parameters: "
        "  - topic (optional): Filter messages by topic pattern (partial match). "
        "  - count (optional): Maximum messages to return (default: 10, max: 100).",

        PropertyList({
            Property("topic", kPropertyTypeString, 
                     "Optional: filter messages by topic pattern (partial match)", ""),
            Property("count", kPropertyTypeInteger, 1, 100, 
                     "Maximum number of messages to return (default: 10)", 10)
        }),

        [&mqtt_tools](const PropertyList& properties) -> ReturnValue {
            std::string topic_filter = "";
            int count = 10;

            if (properties["topic"].has_value()) {
                topic_filter = properties["topic"].value<std::string>();
            }
            if (properties["count"].has_value()) {
                count = properties["count"].value<int>();
            }

            ESP_LOGI(TAG, "MCP调用: self.mqtt.get_messages - Filter: '%s', Count: %d",
                      topic_filter.c_str(), count);

            auto messages = mqtt_tools.GetRecentMessages(topic_filter, count);

            cJSON* result = cJSON_CreateObject();
            cJSON_AddNumberToObject(result, "total", (double)messages.size());
            cJSON_AddNumberToObject(result, "returned", (double)std::min((int)messages.size(), count));

            cJSON* messages_array = cJSON_CreateArray();
            for (const auto& msg : messages) {
                cJSON* msg_obj = cJSON_CreateObject();
                cJSON_AddStringToObject(msg_obj, "topic", msg.topic.c_str());
                cJSON_AddStringToObject(msg_obj, "payload", msg.payload.c_str());
                cJSON_AddNumberToObject(msg_obj, "timestamp", (double)msg.timestamp);
                cJSON_AddNumberToObject(msg_obj, "qos", msg.qos);
                cJSON_AddItemToArray(messages_array, msg_obj);
            }
            cJSON_AddItemToObject(result, "messages", messages_array);

            return result;
        }
    );

    // ============================================
    // 工具5: 获取连接状态
    // self.mqtt.get_status
    // ============================================
    mcp_server.AddTool(
        "self.mqtt.get_status",
        
        "Get the current MQTT connection status and configuration. "
        "Use this to check if the MQTT client is connected to the broker "
        "and view connection details. "
        "No parameters required.",

        PropertyList(),

        [&mqtt_tools](const PropertyList& properties) -> ReturnValue {
            std::string status, server;
            int port;
            mqtt_tools.GetStatus(status, server, port);

            cJSON* result = cJSON_CreateObject();
            cJSON_AddStringToObject(result, "status", status.c_str());
            cJSON_AddBoolToObject(result, "connected", mqtt_tools.IsConnected());
            cJSON_AddStringToObject(result, "server", server.c_str());
            cJSON_AddNumberToObject(result, "port", port);
            
            return result;
        }
    );

    // ============================================
    // 工具6: 直接发送原始 MQTT 消息（高级）
    // self.mqtt.send_raw
    // ============================================
    mcp_server.AddTool(
        "self.mqtt.send_raw",
        
        "Send a raw MQTT message with full control. "
        "Use this when you need to send specially formatted messages "
        "or messages that don't fit the standard publish pattern. "
        "Parameters: "
        "  - topic: The MQTT topic. "
        "  - payload: The complete message payload (will be sent as-is). "
        "  - qos (optional): Quality of Service 0-2 (default: 1). "
        "  - retain (optional): Whether to retain (default: false).",

        PropertyList({
            Property("topic", kPropertyTypeString, "The MQTT topic"),
            Property("payload", kPropertyTypeString, "The raw message payload to send"),
            Property("qos", kPropertyTypeInteger, 0, 2, "Quality of Service", 1),
            Property("retain", kPropertyTypeBoolean, "Retain message", false)
        }),

        [&mqtt_tools](const PropertyList& properties) -> ReturnValue {
            std::string topic = properties["topic"].value<std::string>();
            std::string payload = properties["payload"].value<std::string>();
            int qos = properties["qos"].value<int>();
            bool retain = properties["retain"].value<bool>();

            bool success = mqtt_tools.Publish(topic, payload, retain, qos);

            if (success) {
                cJSON* result = cJSON_CreateObject();
                cJSON_AddStringToObject(result, "status", "sent");
                cJSON_AddStringToObject(result, "topic", topic.c_str());
                cJSON_AddNumberToObject(result, "bytes", (double)payload.length());
                return result;
            } else {
                throw std::runtime_error("Failed to send raw MQTT message.");
            }
        }
    );

    ESP_LOGI(TAG, "MQTT MCP 工具注册完成！已注册 6 个工具:");
    ESP_LOGI(TAG, "  1. self.mqtt.publish      - 发布消息");
    ESP_LOGI(TAG, "  2. self.mqtt.subscribe    - 订阅主题");
    ESP_LOGI(TAG, "  3. self.mqtt.unsubscribe  - 取消订阅");
    ESP_LOGI(TAG, "  4. self.mqtt.get_messages - 获取消息历史");
    ESP_LOGI(TAG, "  5. self.mqtt.get_status   - 获取连接状态");
    ESP_LOGI(TAG, "  6. self.mqtt.send_raw     - 发送原始消息");
}
