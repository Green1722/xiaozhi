# 小智 ESP32 - 远端 LED 控制方案 (MQTT 版本)

## 系统架构

```
┌─────────────────┐      MCP (TCP)       ┌─────────────────┐     MQTT      ┌─────────────────┐
│   小智 ESP32-S3  │ ──────────────────> │   MCP Server    │ ───────────> │   MQTT Broker   │
│   (源代码不变)   │    JSON-RPC 2.0     │   (Python exe)  │   xiaozhi/    │  test.mosquitto│
└─────────────────┘                      └─────────────────┘    led/        │     .org       │
                                                                            └───────┬─────────┘
                                                                                    │ MQTT
                                                                                    │ Subscribe
                                                                                    ▼
                                                                            ┌─────────────────┐
                                                                            │   远端 ESP32    │
                                                                            │   (RGB LED)     │
                                                                            └─────────────────┘
```

## 目录结构

```
mcp_server/                          # MCP 中继服务器
├── mqtt_mcp_server.py              # MQTT 版本 Python 源代码
├── config.py                        # 配置文件
├── requirements.txt                 # Python 依赖
├── mqtt_mcp_server.spec            # PyInstaller 配置
├── build_mqtt_exe.bat              # 打包脚本 (MQTT版)
├── build_exe.bat                   # 打包脚本 (UDP版)
├── 启动MQTT服务器.bat               # 启动 MQTT 版本
└── 启动MCP服务器.bat               # 启动 UDP 版本

esp32_remote_led/                   # 远端 ESP32 代码
├── esp32_remote_led_mqtt.ino       # MQTT 版本 (使用此版本)
├── esp32_remote_led.ino            # UDP 版本
└── platformio.ini                   # PlatformIO 配置
```

## MQTT Topic 说明

| Topic | 方向 | 说明 |
|-------|------|------|
| `xiaozhi/led/command` | MCP Server → ESP32 | LED 控制指令 |
| `xiaozhi/led/status` | ESP32 → MCP Server | 状态上报 |
| `xiaozhi/led/heartbeat` | ESP32 → MCP Server | 心跳 (可选) |

## 快速开始

### 第一步：烧录远端 ESP32

1. **打开 MQTT 版本代码**
   
   使用 `esp32_remote_led_mqtt.ino`

2. **修改 MQTT Broker (如需要)**
   
   ```cpp
   const char* mqtt_broker = "test.mosquitto.org";  // 公共 broker
   // 或使用本地 broker:
   // const char* mqtt_broker = "192.168.1.100";     // 树莓派 IP
   ```

3. **烧录固件**

4. **查看串口监视器** (115200 baud)
   ```
   [MQTT] Connected!
   [MQTT] Subscribed to: xiaozhi/led/command
   Ready! Waiting for MQTT commands...
   ```

### 第二步：打包并运行 MCP Server

1. **双击 `build_mqtt_exe.bat`** 打包

2. **修改 `config.py`** (如果需要)
   ```python
   MQTT_BROKER = "test.mosquitto.org"  # 默认使用公共 broker
   # 如需认证:
   # MQTT_USERNAME = "your_username"
   # MQTT_PASSWORD = "REPLACE_ME"
   ```

3. **双击 `启动MQTT服务器.bat`**
   ```
   ====================================
     小智 MCP Server - MQTT LED 控制
   ====================================
     MQTT Broker: test.mosquitto.org:1883
     Command Topic: xiaozhi/led/command
     MCP Server: 0.0.0.0:8765
   ====================================
   [MQTT] Connected to broker: test.mosquitto.org:1883
   [MQTT] Server started on ('0.0.0.0', 8765)
   ```

### 第三步：配置小智连接 MCP Server

在 xiaozhi-esp32-server 的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "led_control": {
      "type": "stdio",
      "command": "dist\\xiaozhi_mqtt_server\\xiaozhi_mqtt_server.exe"
    }
  }
}
```

## MCP 工具列表

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `self.device.set_rgb_color` | r, g, b (0-255) | 设置 RGB 颜色 |
| `self.device.turn_off_rgb` | 无 | 关闭 LED |
| `self.device.set_rgb_brightness` | brightness (0-100) | 设置亮度 |
| `self.device.set_rgb_preset` | color | 预设颜色 |
| `self.device.set_led_effect` | effect, duration | LED 效果 |
| `self.device.get_remote_status` | 无 | 获取状态 |

## 使用示例

对小智说：
- "小智，把灯调成红色"
- "小智，开个蓝色灯"
- "小智，关灯"

## MQTT 消息格式

**控制指令 (JSON)**:
```json
{"type": "rgb", "r": 255, "g": 0, "b": 0}
{"type": "brightness", "value": 50}
{"type": "effect", "effect": "blink", "duration": 2000}
{"type": "off"}
```

**状态上报 (JSON)**:
```json
{"status": "ok", "ip": "192.168.1.100", "r": 255, "g": 0, "b": 0, "brightness": 100}
```

## 常见问题

### Q: MQTT 连接失败
- 检查网络是否正常
- 确认 MQTT Broker 地址正确
- 如果使用本地 broker，确保 broker 正在运行

### Q: LED 没有反应
- 检查 ESP32 是否订阅了正确的 topic
- 查看串口监视器是否有收到消息
- 使用 MQTT.fx 或 MQTT Explorer 调试

### Q: 使用公共 broker 不稳定
- 建议部署本地 MQTT Broker (如 Mosquitto on 树莓派)
- 或者使用 EMQ X Cloud 等云服务
