# 智能体检播报系统

> **GitHub 仓库**：[https://github.com/31901026sxc/xiaozhi_height-weight](https://github.com/31901026sxc/xiaozhi_height-weight)

基于 ESP32 双板 + 小智 AI + MCP 协议的智能体检播报系统。  
人站上仪器 → 测量板自动读取身高体重 → 触发小智 AI 语音播报医学建议。

---

## 系统架构

```
身高体重仪
  │ (606协议, 115200bps)
  ↓ TXD → GPIO16(RX2)
┌──────────────────────────────┐          ┌──────────────────────────────┐
│        测量板（仪器ESP32）      │          │       小智板（xiaozhi-esp32）   │
│                              │          │                              │
│  读取606协议 → 解析身高体重    │  GPIO47  │  GPIO38 收到低电平            │
│  → 发布 MQTT                 │ ──────→  │  → 触发语音会话              │
│  → 拉低 GPIO47 (200ms唤醒)   │  GND     │  → 云端 AI 调 MCP 工具       │
│                              │ ──────→  │  → TTS 语音播报              │
└──────────────────────────────┘          └──────────────────────────────┘
          │ MQTT (TCP)                               ↑
          ↓ 发布至 47.97.8.221:1883           MCP WebSocket
    MQTT Broker                         (wss://api.xiaozhi.me/mcp/)
          ↑                                          ↑
          └──────── Python MCP 服务 ────────────────┘
                  (zhudong_mcp/physical_exam_control.py)
```

---

## 硬件接线

全系统共 **4 根飞线**，分两组：

### 组一：身高体重仪 → 测量板

| 仪器端 | 测量板引脚 | 说明 |
|--------|-----------|------|
| TXD | **GPIO16 (RX2)** | 606 协议数据，115200 8N1 |
| GND | **GND** | 共地（必须） |

### 组二：测量板 → 小智板

| 测量板引脚 | 小智板引脚 | 说明 |
|-----------|-----------|------|
| **GPIO47** | **GPIO38** | 低电平触发唤醒（平时高，测量后拉低 200 ms） |
| **GND** | **GND** | 共地（必须，禁止共 3.3V/5V 电源） |

---

## 目录结构

```
xiaozhi_height-weight/
├── README.md                        # 本文件
├── docs/
│   └── ESP32双板配置指南.md          # 详细配置与接线指南
│
├── zhudong_mcp/                     # Python MCP 服务（中间层）
│   ├── physical_exam_control.py     # 主程序（MCP 工具 + MQTT 监听）
│   ├── mcp_pipe.py                  # MCP WebSocket 管道
│   ├── serial_reader.py             # 串口读取（606 协议）
│   ├── requirements.txt             # Python 依赖
│   ├── mcp_config.json              # MCP 配置
│   ├── start.bat                    # Windows 启动脚本
│   ├── start.sh                     # Linux/树莓派启动脚本
│   ├── c++ver/                      # 测量板 Arduino 固件
│   │   └── examples/PhysicalExamControl/
│   │       ├── PhysicalExamControl.ino   # 主程序
│   │       └── config.h                 # 烧录前唯一需要修改的配置文件
│   └── docs/                        # 补充文档
│
└── xiaozhi-esp32-main/              # 小智板固件（ESP-IDF 工程）
    ├── main/                        # 固件主程序
    └── sdkconfig.defaults.*         # 各型号默认配置
```

---

## 快速上手

### 第一步：配置并烧录测量板

编辑 [`zhudong_mcp/c++ver/examples/PhysicalExamControl/config.h`](zhudong_mcp/c++ver/examples/PhysicalExamControl/config.h)，只需改这一个文件：

```cpp
// WiFi（支持多组）
#define CFG_WIFI_COUNT 2
static const char* CFG_WIFI_SSIDS[]  = { "你的WiFi", "备用WiFi" };
static const char* CFG_WIFI_PASSES[] = { "REPLACE_ME", "REPLACE_ME" };

// 小智 MCP 端点（在 xiaozhi.me 控制台获取 Token）
#define CFG_MCP_ENDPOINT "wss://api.xiaozhi.me/mcp/?token=<你的Token>"

// 仪器编号
#define CFG_INSTRUMENT_ID "HW-001"

// MQTT Broker（默认不改）
#define CFG_MQTT_SERVER "47.97.8.221"
#define CFG_MQTT_PORT   1883
```

> ⚠️ ESP32 只支持 **2.4 GHz** WiFi，请确认热点频段。

用 Arduino IDE 打开 `PhysicalExamControl.ino` → 选择 ESP32S3 开发板 → 烧录。

---

### 第二步：配网并烧录小智板

1. TypeC 线接右侧接口，同时按住右侧按钮上电
2. 设备创建同名热点，手机连接该热点
3. 访问配网页面填入目标 WiFi 信息
4. 在 [xiaozhi.me](https://xiaozhi.me) 控制台创建 Agent，选择 **MCP over WebSocket** 端点，获取 Token URL

详见 [docs/ESP32双板配置指南.md](docs/ESP32双板配置指南.md)。

---

### 第三步：启动 Python MCP 服务（可选，PC/树莓派运行）

```bash
# 安装依赖
pip install -r zhudong_mcp/requirements.txt

# Windows
set MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=<你的Token>
cd zhudong_mcp
start.bat

# Linux / 树莓派
export MCP_ENDPOINT="REPLACE_ME"
cd zhudong_mcp
chmod +x start.sh && ./start.sh
```

---

## MCP 工具说明

Python MCP 服务向小智云端 AI 暴露以下工具：

| 工具 | 参数 | 说明 |
|------|------|------|
| `process_physical_exam` | height_cm, weight_kg | 处理身高体重，生成医学建议并触发播报 |
| `xiaozhi_speak` | text | 让小智播报指定文字 |
| `get_exam_records` | limit=10, **instrument_id=""** | 获取最近体检记录（可按仪器编号筛选） |
| `get_last_person_height_weight` | **instrument_id=""** | 获取最后一条记录（可按仪器编号筛选）并推送 |
| `get_mqtt_status` | — | 查看 MQTT 连接状态 |
| `start_serial_measurement` | — | 通过串口发送 606 开始测量指令 |

`instrument_id` 参数示例：
```
get_exam_records(limit=5, instrument_id="HW-001")   # 只查 HW-001 的记录
get_last_person_height_weight(instrument_id="HW-002") # 取 HW-002 的最后一次测量
```

---

## MQTT 主题

| 方向 | 主题 | 说明 |
|------|------|------|
| 仪器发布 | `体检中心/仪器/身高体重` | 发布测量结果（JSON） |
| 服务接收 | `体检中心/小智/播报` | 接收播报指令 |
| 状态上报 | `体检中心/数据/状态` | 数据确认状态 |

发布数据格式：
```json
{
  "instrument_id": "HW-001",
  "height_cm": 172.5,
  "weight_kg": 65.3,
  "bmi": 21.95,
  "timestamp": "2026-03-03T10:30:00"
}
```

---

## 常见问题

| 现象 | 排查方向 |
|------|---------|
| 测量板 WiFi 连不上 | 确认热点为 2.4 GHz；重新上电进入 SmartConfig |
| MQTT 发布失败 | 检查 Broker IP/端口；确认允许匿名连接 |
| MCP 连接失败（401） | Token 过期，到控制台重新生成 |
| 小智不说话 | 检查 GPIO47→GPIO38 接线；查看串口日志确认 MCP 工具被调用 |
| GPIO 电平不可靠 | 测量板与小智板 GND 未共地，务必接 GND |

---

## 相关文档

- [ESP32 双板完整配置指南](docs/ESP32双板配置指南.md) — 详细接线图、配网流程、MCP 配置
- [zhudong_mcp/README.md](zhudong_mcp/README.md) — Python MCP 服务详细说明
- [xiaozhi-esp32-main/README.md](xiaozhi-esp32-main/README.md) — 小智固件说明

---

## License

本项目固件部分（`xiaozhi-esp32-main/`）遵循原项目 License，其余代码采用 MIT License。
