# 体检中心小智 MCP 服务

基于 MCP (Model Context Protocol) 的体检中心服务：人站上仪器 → 测出身高体重 → 小智主动播报医学建议。

---

## 项目结构

```
zhudong_mcp/
├── README.md                    # 本文件：项目说明与运行指南
├── requirements.txt             # Python 依赖
├── mcp_config.json              # MCP 服务配置
│
├── physical_exam_control.py     # 体检中心 MCP 服务（主程序）
├── mcp_pipe.py                  # MCP 管道（连接小智 MCP 端点）
├── serial_reader.py              # 串口读取模块（支持606协议）
│
├── start.bat                    # Windows 启动脚本
├── start.sh                     # Linux/树莓派启动脚本
│
├── docs/                        # 文档目录
│   ├── websocket.md            # WebSocket 协议文档
│   ├── 606.md                  # 606通信协议文档
│   ├── DATA_FLOW.md            # 数据流程说明
│   ├── SERIAL_COMMUNICATION.md # 串口通信文档
│   ├── XIAOZHI_TROUBLESHOOTING.md # 小智不发声排查指南
│   └── DEPLOY_RASPBERRY_PI.md  # 树莓派部署指南
│
└── tests/                       # 测试工具（可选）
    └── test_serial.py           # 串口通信测试脚本
```

---

## 运行方式

### 1. 安装依赖

```bash
# Windows
cd c:\Users\sxc\Desktop\zhudong_mcp
pip install -r requirements.txt

# Linux/树莓派
cd /path/to/zhudong_mcp
pip3 install -r requirements.txt
```

### 2. 启动体检中心 MCP 服务

#### Windows 系统

使用 `start.bat` 启动：
```cmd
start.bat
```

#### Linux/树莓派系统

使用 `start.sh` 启动：
```bash
# 赋予执行权限（首次运行）
chmod +x start.sh

# 启动服务
./start.sh
```

或者手动启动：

#### 方式 A：通过 MCP 管道连接小智（推荐）

需先设置 MCP 端点环境变量，再启动：

```powershell
# Windows PowerShell
$env:MCP_ENDPOINT = "REPLACE_ME"
$env:MCP_CONFIG = "c:\Users\sxc\Desktop\zhudong_mcp\mcp_config.json"
cd c:\Users\sxc\Desktop\zhudong_mcp
python mcp_pipe.py health-exam-service
```

```bash
# Linux/树莓派
export MCP_ENDPOINT="REPLACE_ME"
export MCP_CONFIG="/path/to/zhudong_mcp/mcp_config.json"
cd /path/to/zhudong_mcp
python3 mcp_pipe.py health-exam-service
```

#### 方式 B：直接运行（仅本地调试）

```bash
# Windows
cd c:\Users\sxc\Desktop\zhudong_mcp
python physical_exam_control.py

# Linux/树莓派
cd /path/to/zhudong_mcp
python3 physical_exam_control.py
```

### 3. 测试

可以通过 MCP 工具进行测试，或使用 MQTT 客户端工具直接向 `体检中心/仪器/身高体重` 主题发布数据。

详见 `docs/XIAOZHI_TROUBLESHOOTING.md` 了解故障排查方法。

---

## 小智主动说话（TTS）

据 `websocket.md`，小智设备通过 **WebSocket** 从服务器接收 TTS（type: "tts" + 音频），不是 MQTT。本服务已做：

- MCP 工具返回中增加 **tts_text**，供小智服务器收到后向设备下发 TTS。
- 可选 **HTTP TTS 推送**：配置 `XIAOZHI_TTS_PUSH_URL`、`XIAOZHI_TTS_PUSH_ENABLED=true`，由平台接口再转发到设备。

详见 `docs/websocket.md`。

## 环境变量（可选）

| 变量 | 说明 | 示例 |
|------|------|------|
| MCP_ENDPOINT | 小智 MCP WebSocket 地址 | wss://api.xiaozhi.me/mcp/?token=REPLACE_ME |
| MCP_CONFIG | mcp_config.json 路径 | c:\...\zhudong_mcp\mcp_config.json |
| XIAOZHI_SPEAK_TOPIC_ALT | 小智备选播报主题 | device/xxx/tts |
| PHYSICAL_EXAM_UPLOAD_URL | 体检数据上传接口 | https://api.example.com/upload/exam |
| PHYSICAL_EXAM_UPLOAD_ENABLED | 是否启用上传 | true |
| XIAOZHI_TTS_PUSH_URL | 小智 TTS 推送接口（POST JSON `{"text":"..."}`） | https://api.example.com/tts/push |
| XIAOZHI_TTS_PUSH_ENABLED | 是否启用 TTS 推送 | true |
| SERIAL_ENABLED | 是否启用串口功能 | true |
| SERIAL_PORT | 串口设备路径 | /dev/ttyUSB0 |
| SERIAL_BAUDRATE | 串口波特率 | 115200 |

---

---

## MCP 工具一览

| 工具 | 说明 |
|------|------|
| process_physical_exam | 处理身高体重，生成医学建议并触发播报 |
| xiaozhi_speak | 远程让小智播报指定文字 |
| get_exam_records | 获取最近体检记录 |
| get_mqtt_status | 获取 MQTT 状态和配置信息 |
| get_last_person_height_weight | 获取最后一个人的身高体重数据并推送到服务器 |
| start_serial_measurement | 通过串口发送开始测量指令（606协议） |

## MQTT 配置

- **Broker**：47.97.8.221:1883  
- **主题**：`体检中心/仪器/身高体重`（仪器上报）、`体检中心/小智/播报`（小智播报）

## 数据流程

小智服务器获取身高体重数据的方式：

1. **通过 MCP 工具主动获取**（推荐）
   - 调用 `get_last_person_height_weight()` 获取最后一个人的身高体重
   - 调用 `get_exam_records(limit)` 获取多条记录
   - 如果没有记录，`get_last_person_height_weight()` 会自动生成正常范围内的数据

2. **通过 HTTP 接口推送**（可选）
   - 配置 `PHYSICAL_EXAM_UPLOAD_URL` 后，MCP服务会自动推送数据

3. **通过 MCP 工具直接处理**
   - 调用 `process_physical_exam()` 实时处理身高体重数据

详细流程说明请参考 [docs/DATA_FLOW.md](docs/DATA_FLOW.md)。
