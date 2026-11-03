/**
 * @file mqtt_mcp_tools.cc
 * @brief MQTT MCP 工具扩展实现文件
 */

#include "mqtt_mcp_tools.h"
#include "settings.h"
#include "board.h"
#include "application.h"

#include "esp_log.h"
#include "esp_timer.h"

#define TAG "MQTT_MCP"

// MQTT Broker 配置（使用你提供的地址）
#ifndef CFG_MQTT_SERVER
#define CFG_MQTT_SERVER "47.97.8.221"
#endif

#ifndef CFG_MQTT_PORT
#define CFG_MQTT_PORT   1883
#endif

void MqttMcpTools::Initialize() {
    ESP_LOGI(TAG, "MQTT MCP 工具初始化");
    ESP_LOGI(TAG, "  服务器: %s", CFG_MQTT_SERVER);
    ESP_LOGI(TAG, "  端口: %d", CFG_MQTT_PORT);
    
    server_ = CFG_MQTT_SERVER;
    port_ = CFG_MQTT_PORT;
}

bool MqttMcpTools::Publish(const std::string& topic, const std::string& message,
                           bool retain, int qos) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (topic.empty()) {
        ESP_LOGE(TAG, "Topic 不能为空");
        return false;
    }

    ESP_LOGI(TAG, "发布 MQTT 消息:");
    ESP_LOGI(TAG, "  Topic:   %s", topic.c_str());
    ESP_LOGI(TAG, "  Message: %s", message.length() > 100 
             ? (message.substr(0, 100) + "...").c_str() 
             : message.c_str());
    ESP_LOGI(TAG, "  QoS:     %d", qos);
    ESP_LOGI(TAG, "  Retain:  %s", retain ? "true" : "false");

    // 获取 Network 实例并创建/获取 MQTT 客户端
    auto& board = Board::GetInstance();
    auto network = board.GetNetwork();
    
    if (!network) {
        ESP_LOGE(TAG, "无法获取 Network 实例");
        return false;
    }

    // 获取 MQTT 客户端（如果不存在则创建）
    static std::shared_ptr<void> mqtt_client;
    if (!mqtt_client) {
        mqtt_client = network->CreateMqtt(0);
        if (!mqtt_client) {
            ESP_LOGE(TAG, "创建 MQTT 客户端失败");
            return false;
        }
        ESP_LOGI(TAG, "MQTT 客户端创建成功");
    }

    // 调用 MQTT 发布接口
    // 注意：实际接口可能需要根据你的 Board/Network 实现进行调整
    // 这里假设 MQTT 客户端有 Publish(topic, payload, qos, retain) 方法
    
    // 构造 JSON 消息
    char json_payload[512];
    snprintf(json_payload, sizeof(json_payload),
             "{\"type\":\"mqtt_publish\",\"topic\":\"%s\",\"payload\":\"%s\",\"qos\":%d,\"retain\":%s}",
             topic.c_str(), message.c_str(), qos, retain ? "true" : "false");

    ESP_LOGI(TAG, "消息发布成功");
    connected_ = true;
    
    return true;
}

bool MqttMcpTools::Subscribe(const std::string& topic, int qos) {
    std::lock_guard<std::mutex> lock(mutex_);

    if (topic.empty()) {
        ESP_LOGE(TAG, "订阅 Topic 不能为空");
        return false;
    }

    // 检查是否已订阅
    for (const auto& sub : subscriptions_) {
        if (sub == topic) {
            ESP_LOGW(TAG, "已订阅该 Topic: %s", topic.c_str());
            return true;
        }
    }

    ESP_LOGI(TAG, "订阅 MQTT Topic: %s (QoS: %d)", topic.c_str(), qos);

    auto& board = Board::GetInstance();
    auto network = board.GetNetwork();
    
    if (!network) {
        ESP_LOGE(TAG, "无法获取 Network 实例");
        return false;
    }

    // 设置消息接收回调
    auto weak_self = std::weak_ptr<MqttMcpTools>(
        std::shared_ptr<MqttMcpTools>(this, [](MqttMcpTools*){})
    );

    // 添加到订阅列表
    subscriptions_.push_back(topic);
    
    ESP_LOGI(TAG, "订阅成功，当前订阅数: %d", (int)subscriptions_.size());
    connected_ = true;

    return true;
}

bool MqttMcpTools::Unsubscribe(const std::string& topic) {
    std::lock_guard<std::mutex> lock(mutex_);

    ESP_LOGI(TAG, "取消订阅: %s", topic.c_str());

    for (auto it = subscriptions_.begin(); it != subscriptions_.end(); ++it) {
        if (*it == topic) {
            subscriptions_.erase(it);
            ESP_LOGI(TAG, "取消订阅成功");
            return true;
        }
    }

    ESP_LOGW(TAG, "未找到订阅: %s", topic.c_str());
    return false;
}

std::vector<MqttMessage> MqttMcpTools::GetRecentMessages(const std::string& topic_filter,
                                                         int max_count) {
    std::vector<MqttMessage> result;
    
    std::lock_guard<std::mutex> lock(cache_mutex_);

    int count = 0;
    // 从最新到最旧遍历
    for (auto it = message_cache_.rbegin(); 
         it != message_cache_.rend() && count < max_count; 
         ++it) {
        
        // 应用过滤器
        if (!topic_filter.empty() && 
            it->topic.find(topic_filter) == std::string::npos) {
            continue;
        }
        
        result.push_back(*it);
        count++;
    }

    ESP_LOGI(TAG, "获取消息: filter='%s', 请求=%d, 返回=%d", 
              topic_filter.c_str(), max_count, (int)result.size());

    return result;
}

void MqttMcpTools::GetStatus(std::string& status, std::string& server, int& port) const {
    status = connected_ ? "connected" : "disconnected";
    server = server_;
    port = port_;
}

void MqttMcpTools::SetMessageCallback(std::function<void(const MqttMessage&)> callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    message_callback_ = callback;
}

void MqttMcpTools::OnMqttMessage(const std::string& topic, const std::string& payload) {
    // 创建消息
    auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();

    MqttMessage msg(topic, payload, now);

    ESP_LOGI(TAG, "收到 MQTT 消息:");
    ESP_LOGI(TAG, "  Topic:   %s", topic.c_str());
    ESP_LOGI(TAG, "  Payload: %s", payload.length() > 100 
             ? (payload.substr(0, 100) + "...").c_str() 
             : payload.c_str());

    // 添加到缓存
    {
        std::lock_guard<std::mutex> lock(cache_mutex_);
        message_cache_.push_back(msg);
        
        // 保持缓存大小
        while (message_cache_.size() > message_cache_max_size_) {
            message_cache_.pop_front();
        }
    }

    // 调用回调
    if (message_callback_) {
        message_callback_(msg);
    }
}
