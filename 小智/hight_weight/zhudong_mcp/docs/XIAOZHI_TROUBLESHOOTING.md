# 小智不发声排查指南

当体检中心已发布医学建议到 MQTT，但小智没有任何声音时，按以下步骤排查。

## 1. 确认 MQTT 消息已发出

使用 MQTT 客户端工具（如 MQTT.fx、mosquitto_sub 等）监听主题：

```bash
# 使用 mosquitto_sub 监听（Linux/树莓派）
mosquitto_sub -h 47.97.8.221 -p 1883 -t "体检中心/小智/播报"

# 或使用 MQTT 客户端工具订阅主题：体检中心/小智/播报
```

然后通过 MCP 工具 `process_physical_exam` 触发一次体检，或直接向 `体检中心/仪器/身高体重` 主题发布数据：

```json
{
  "height": 170,
  "weight": 65,
  "id": "test_001"
}
```

- **若监听端能收到消息**：说明 MQTT 发布正常，问题在小智端（未订阅或未处理）。
- **若监听端收不到**：检查 `physical_exam_control` 是否运行、MQTT 是否连接。

## 2. 确认小智监听的 MQTT 主题

小智默认**不一定**订阅 `体检中心/小智/播报`。需要查看您所用小智产品的文档，确认它监听的 MQTT 主题格式，例如：

- `device/{device_id}/tts`
- `xiaozhi/tts`
- 或项目自定义的主题

### 方案 A：配置备选主题（双主题发布）

若小智监听的的主题已知，可让 `physical_exam_control` 同时发布到该主题：

```bash
set XIAOZHI_SPEAK_TOPIC_ALT=device/你的小智设备ID/tts
```

然后重启 `physical_exam_control`。

### 方案 B：配置备选主题（推荐）

在启动服务前设置环境变量，让服务同时发布到小智实际监听的 MQTT 主题：

```bash
# Linux/树莓派
export XIAOZHI_SPEAK_TOPIC_ALT="device/你的小智设备ID/tts"

# Windows
set XIAOZHI_SPEAK_TOPIC_ALT=device/你的小智设备ID/tts
```

然后重启服务，服务会自动同时发布到两个主题。

### 方案 C：使用 MQTT 桥接工具

可以使用第三方 MQTT 桥接工具（如 Node-RED、MQTT Broker 的桥接功能等），将 `体检中心/小智/播报` 的消息转发到小智实际监听的 MQTT 主题。

### 方案 D：通过 HTTP TTS API

若小智提供 HTTP TTS 接口，可配置环境变量让服务直接调用：

```bash
export XIAOZHI_TTS_PUSH_URL="http://小智设备IP:端口/tts"
export XIAOZHI_TTS_PUSH_ENABLED=true
```

具体 URL、参数名以您的小智产品文档为准。

## 3. 小智产品相关说明

- **xiaozhi-esp32**：基于 ESP32，通常需要按项目文档配置 MQTT 主题和 TTS 流程。
- **小智 AI 音箱**：部分型号支持 MQTT 主动播报，需在设备或云端配置订阅主题。
- **自研小智**：需在固件/服务中增加：订阅指定 MQTT 主题 → 解析 JSON 取 `text` → 调用 TTS 播报。

## 4. 环境变量配置汇总

| 变量 | 说明 | 示例 |
|------|------|------|
| XIAOZHI_SPEAK_TOPIC_ALT | 小智备选播报主题（双主题发布） | device/xxx/tts |
| XIAOZHI_TTS_PUSH_URL | TTS HTTP API 地址 | http://192.168.1.100:8080/tts |
| XIAOZHI_TTS_PUSH_ENABLED | 是否启用 TTS 推送 | true |
