/**
 * @file mqtt_mcp_tools.h
 * @brief MQTT MCP 工具扩展头文件
 * 
 * 功能：让小智通过 MCP 协议向 MQTT 服务器发送和接收消息
 */

#ifndef MQTT_MCP_TOOLS_H
#define MQTT_MCP_TOOLS_H

#include <string>
#include <vector>
#include <functional>
#include <mutex>
#include <deque>
#include <chrono>
#include <memory>

// 前向声明
class MqttClient;

/**
 * @brief MQTT 消息结构体
 */
struct MqttMessage {
    std::string topic;           // MQTT Topic
    std::string payload;         // 消息内容
    int64_t timestamp;           // 时间戳（毫秒）
    int qos = 0;                // 服务质量等级
    
    MqttMessage() : timestamp(0), qos(0) {}
    MqttMessage(const std::string& t, const std::string& p, int64_t ts, int q = 0)
        : topic(t), payload(p), timestamp(ts), qos(q) {}
};

/**
 * @brief MQTT MCP 工具类
 * 
 * 管理 MQTT 连接、订阅和消息缓存
 */
class MqttMcpTools {
public:
    static MqttMcpTools& GetInstance() {
        static MqttMcpTools instance;
        return instance;
    }

    /**
     * @brief 初始化 MQTT 工具
     */
    void Initialize();

    /**
     * @brief 检查是否已连接
     */
    bool IsConnected() const { return connected_; }

    /**
     * @brief 发布消息到 MQTT Topic
     * @param topic 主题
     * @param message 消息内容
     * @param retain 是否保留消息
     * @param qos 服务质量 (0, 1, 2)
     * @return 是否成功
     */
    bool Publish(const std::string& topic, const std::string& message, 
                 bool retain = false, int qos = 1);

    /**
     * @brief 订阅 MQTT Topic
     * @param topic 主题（支持通配符）
     * @param qos 服务质量
     * @return 是否成功
     */
    bool Subscribe(const std::string& topic, int qos = 1);

    /**
     * @brief 取消订阅
     * @param topic 主题
     * @return 是否成功
     */
    bool Unsubscribe(const std::string& topic);

    /**
     * @brief 获取最近收到的消息
     * @param topic_filter 主题过滤器（空则返回所有）
     * @param max_count 最大数量
     * @return 消息列表
     */
    std::vector<MqttMessage> GetRecentMessages(const std::string& topic_filter = "", 
                                                int max_count = 10);

    /**
     * @brief 获取连接状态信息
     */
    void GetStatus(std::string& status, std::string& server, int& port) const;

    /**
     * @brief 设置消息回调
     */
    void SetMessageCallback(std::function<void(const MqttMessage&)> callback);

    /**
     * @brief 处理收到的 MQTT 消息
     */
    void OnMqttMessage(const std::string& topic, const std::string& payload);

private:
    MqttMcpTools() 
        : connected_(false), 
          port_(1883),
          message_cache_max_size_(100) {}
    
    ~MqttMcpTools() = default;
    MqttMcpTools(const MqttMcpTools&) = delete;
    MqttMcpTools& operator=(const MqttMcpTools&) = delete;

    bool connected_;                              // 连接状态
    std::string server_;                          // MQTT 服务器
    int port_;                                    // 端口
    std::vector<std::string> subscriptions_;       // 当前订阅列表
    std::deque<MqttMessage> message_cache_;       // 消息缓存
    size_t message_cache_max_size_;               // 最大缓存数
    
    mutable std::mutex mutex_;                    // 互斥锁
    mutable std::mutex cache_mutex_;              // 缓存锁
    std::function<void(const MqttMessage&)> message_callback_;  // 回调函数
};

// 便捷别名
using MqttTools = MqttMcpTools;

#endif // MQTT_MCP_TOOLS_H
