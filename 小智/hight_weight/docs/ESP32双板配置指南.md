# ESP32 双板配置指南

> 本项目由两块 ESP32 协同工作：**测量板**（运行 `PhysicalExamControl.ino`）负责读取身高体重并通过 MQTT 转发；**小智板**（运行 `xiaozhi-esp32-main` 固件）负责接收指令并通过 AI 语音播报医学建议。

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      体检中心系统架构                             │
│                                                                   │
│  ┌──────────────┐  GPIO47→GPIO38   ┌──────────────────────────┐  │
│  │   测量板      │ ──── 唤醒线 ──→ │       小智板              │  │
│  │ (仪器ESP32)  │                  │  (xiaozhi-esp32-main)    │  │
│  │              │                  │                           │  │
│  │ 串口(GPIO16) │                  │  WiFi → 小智云服务器      │  │
│  │    ↑          │                  │  WebSocket / MQTT        │  │
│  │  606协议     │                  │  AI 语音播报              │  │
│  │  身高体重仪  │                  └──────────────────────────┘  │
│  │              │       MQTT (TCP)                               │  │
│  │  WiFi → MQTT │ ──── 发布数据 ──→ MQTT Broker (47.97.8.221)   │  │
│  │  WebSocket   │                         ↑                      │  │
│  │  → MCP端点  │                   Python MCP 服务              │  │
│  └──────────────┘                  (physical_exam_control.py)   │  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 测量板（仪器 ESP32）

源码位置：`zhudong_mcp/c++ver/examples/PhysicalExamControl/`

### 2.1 烧录前配置

**所有参数集中在 [`config.h`](../zhudong_mcp/c++ver/examples/PhysicalExamControl/config.h) 中，烧录前只需修改此文件。**

```cpp
// ── WiFi（支持多组，逐个尝试）──────────────────────────────────
// ESP32 仅支持 2.4 GHz，5G/6G 热点请填写 2.4G 的 SSID
#define CFG_WIFI_COUNT 2
static const char* CFG_WIFI_SSIDS[]  = {
    "你的WiFi名称",     // 第 1 个（优先尝试）
    "备用热点SSID",     // 第 2 个（失败后尝试）
};
static const char* CFG_WIFI_PASSES[] = {
    "REPLACE_ME",
    "REPLACE_ME",
};

// ── MQTT ──────────────────────────────────────────────────────
#define CFG_MQTT_SERVER    "47.97.8.221"   // MQTT Broker 地址
#define CFG_MQTT_PORT      1883             // MQTT 端口
#define CFG_MQTT_CLIENT_ID "ESP32_PhysicalExam"

// ── 小智 MCP WebSocket 端点 ───────────────────────────────────
// 在 xiaozhi.me 控制台获取 Token，替换下方 URL 中的 token=... 部分
#define CFG_MCP_ENDPOINT "wss://api.xiaozhi.me/mcp/?token=<你的Token>"

// ── 仪器序号 ──────────────────────────────────────────────────
#define CFG_INSTRUMENT_ID "HW-001"
```

> **安全建议（强烈推荐）**：`config.h` 含 WiFi 密码与 MCP Token，**不要提交真实凭据到 Git 仓库**。建议仅在本地保留真实值，提交前恢复为占位符，或改为通过 NVS / 配网流程动态下发。

### 2.2 WiFi 连接流程

```
上电
 │
 ├─→ 依次尝试 CFG_WIFI_SSIDS[] 中的每个热点
 │     连接成功 → 继续启动
 │     全部失败 ↓
 └─→ 进入 SmartConfig（ESP-Touch 一键配网）
       超时时间：CFG_SMARTCONFIG_TIMEOUT_S 秒（默认 120s）
       使用手机 App "ESP-Touch" 发送 SSID + 密码
```

> **注意**：ESP32 只支持 2.4 GHz 频段，请确认热点不是纯 5G。

### 2.3 MQTT 连接与主题

连接成功后，测量板自动连接 MQTT Broker 并使用如下主题：

| 方向 | 主题 | 说明 |
|------|------|------|
| 发布 | `体检中心/仪器/身高体重` | 发布测量结果（JSON 格式） |
| 订阅 | `体检中心/小智/播报` | 接收播报指令（可选） |
| 发布 | `体检中心/数据/状态` | 上传确认状态 |

发布的数据格式示例：

```json
{
  "instrument_id": "HW-001",
  "height_cm": 172.5,
  "weight_kg": 65.3,
  "bmi": 21.95,
  "timestamp": "2026-03-02T10:30:00"
}
```

防抖配置：8 秒内相同数据不重复发布（可通过 `set_config` MCP 工具远程修改）。

### 2.4 MCP WebSocket 连接

测量板通过 `WebSocketMCP` 库连接小智云端 MCP 端点：

```
wss://api.xiaozhi.me/mcp/?token=<Token>
```

连接建立后，测量板作为 **MCP 客户端**，可调用小智板上注册的工具（如触发语音播报）。

### 2.5 完整飞线接线说明

本项目共涉及两组飞线连接，下表列出所有需要手工拉线的信号。

#### 2.5.1 身高体重仪 → 测量板（仪器 ESP32）

| 仪器端 | 测量板引脚 | 电气说明 |
|--------|-----------|---------|
| TXD（数据输出） | **GPIO16 (RX2)** | 单向，轻触即可；仪器 TX 接测量板 RX |
| GND | **GND** | 共地，必须接 |

> **注意**：仅需 2 根飞线（TXD + GND）。仪器侧 RXD 无需连接（测量板只接收数据）。  
> 波特率：115200，8N1，通信协议为 606 标准协议。

接线示意图：

```
  ┌──────────────────┐                ┌──────────────────────┐
  │   身高体重仪      │                │   测量板（ESP32）     │
  │                  │                │                      │
  │  TXD ────────────┼────────────→  │ GPIO16 (RX2)         │
  │  GND ────────────┼────────────→  │ GND                  │
  │                  │                │                      │
  └──────────────────┘                └──────────────────────┘
         2 根飞线（信号 + 地）
```

#### 2.5.2 测量板（仪器 ESP32）→ 小智板

测量板用一根 GPIO 线触发小智板开始对话：

| 测量板引脚 | 小智板引脚 | 电气说明 |
|-----------|-----------|---------|
| **GPIO47** | **GPIO38** | 低电平触发；平时拉高，测量完成后拉低 200 ms |
| **GND** | **GND** | 共地，必须接；两板不共地时电平不可靠 |

> **注意**：仅需 2 根飞线（唤醒信号 + 地）。两板均有独立电源，不可共 3.3 V / 5 V，只共 GND。  
> GPIO47（输出）在 `setup()` 初始化为 OUTPUT 并设为 HIGH；触发时拉低 200 ms 后恢复 HIGH。

接线示意图：

```
  ┌──────────────────────┐                ┌──────────────────────────┐
  │   测量板（仪器ESP32）  │                │   小智板（xiaozhi-esp32）  │
  │                      │                │                          │
  │  GPIO47 (WAKEUP OUT) ┼────────────→  │ GPIO38 (WAKEUP IN)       │
  │  GND                 ┼────────────→  │ GND                      │
  │                      │                │                          │
  └──────────────────────┘                └──────────────────────────┘
         2 根飞线（唤醒信号 + 地）
```

当检测到有效测量数据时：`GPIO47 拉低（200 ms）` → 小智板 GPIO38 收到低电平 → 触发 `WakeWordInvoke` → 云端 AI 调用 MCP 工具播报。

#### 2.5.3 全系统飞线汇总

```
身高体重仪
  │ TXD ──────────────────────────→ 测量板 GPIO16 (RX2)
  │ GND ──────────────────────────→ 测量板 GND
  │
测量板（仪器ESP32）
  │ GPIO47 ──────────────────────→ 小智板 GPIO38
  │ GND    ──────────────────────→ 小智板 GND

共 4 根飞线：TXD、GND（仪器侧）+ GPIO47、GND（板间）
```

> ⚠️ **常见错误**：将 5V/3.3V 电源线也连在一起——两块 ESP32 必须各自独立供电，只共 GND，否则可能烧毁引脚。

---

## 3. 小智板（xiaozhi-esp32-main）

源码位置：`xiaozhi-esp32-main/`，使用 ESP-IDF 编译。

### 3.1 WiFi 配网方式

小智板支持三种配网方式（在 `idf.py menuconfig` 中选择）：

热点配网

1. typec线插到右侧接口，同时按下右侧按钮（按钮可能在显示屏下面）
2. 设备启动后创建同名热点
3. 手机连接该热点，访问配网页面填入目标 WiFi 信息


### 3.2 连接小智云服务器

小智板通过 **WebSocket 或 MQTT** 连接小智云服务器（在控制台配置）：

**WebSocket 连接握手流程：**

```
设备上电 → 连接 WiFi → 触发语音会话
    │
    ├─→ 发送 Hello 消息
    │     {
    │       "type": "hello",
    │       "version": 3,
    │       "transport": "websocket",
    │       "features": { "mcp": true },
    │       "audio_params": {
    │         "format": "opus",
    │         "sample_rate": 16000,
    │         "channels": 1,
    │         "frame_duration": 60
    │       }
    │     }
    │
    ├─→ 等待服务器 Hello 响应（超时 10 秒）
    │     {
    │       "type": "hello",
    │       "transport": "websocket",
    │       "session_id": "xxx",
    │       "audio_params": { ... }
    │     }
    │
    └─→ 音频通道建立成功，开始双向音频 + JSON 消息通信
```

### 3.3 MCP 服务配置

小智板作为 **MCP 服务器**，向云端 AI 暴露可调用的工具。

在控制台（`xiaozhi.me`）创建 Agent 并配置 MCP 端点：
- 端点类型：选择 MCP over WebSocket
- 获得形如 `wss://api.xiaozhi.me/mcp/?token=REPLACE_ME 的 URL
- 将此 URL 填入**测量板** `config.h` 的 `CFG_MCP_ENDPOINT`

小智板固件侧通过 `McpServer::AddTool()` 注册工具，示例：

```cpp
mcp_server.AddTool(
    "health.speak_advice",
    "播报体检建议",
    PropertyList({
        Property("text", kPropertyTypeString)
    }),
    [this](const PropertyList& props) -> ReturnValue {
        auto text = props["text"].value<std::string>();
        // 触发 TTS 播报
        return true;
    }
);
```

---

## 4. Python MCP 服务（中间层，可选）

源码：`zhudong_mcp/physical_exam_control.py`

若需要在 PC / 树莓派上运行中间处理层：

```
小智 ←→ MCP WebSocket ←→ Python MCP 服务 ←→ MQTT Broker ←→ 测量板
```

### 4.1 环境配置

```bash
pip install -r requirements.txt

# 设置环境变量
set MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=<你的Token>   # Windows
export MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=<你的Token>  # Linux
```

> **安全建议**：不要把 Token 写入代码、README、截图或 IM 聊天记录；终端演示时建议使用临时 Token，并在演示后立即失效旧 Token。

### 4.2 MQTT 配置

在 `physical_exam_control.py` 顶部修改：

```python
MQTT_BROKER = "47.97.8.221"   # MQTT Broker IP
MQTT_PORT   = 1883             # 端口
```

生产环境建议启用 TLS（常见端口 8883）并配置账号密码与 ACL，避免匿名连接和明文传输。

### 4.3 启动

```bash
# Windows
start.bat

# Linux / 树莓派
chmod +x start.sh && ./start.sh
```

---

## 5. 安全加固（必做）

### 5.1 凭据与代码安全

- MCP Token、WiFi 密码、MQTT 账号密码视为敏感信息，禁止硬编码到可公开仓库。
- 新增或更新 `.gitignore`，确保本地凭据文件（如 `.env`、私有配置）不被提交。
- 发布日志、Issue、截图前先脱敏：隐藏 `token=`、密码、设备唯一标识。
- Token 泄露后立即在控制台吊销并重发新 Token。

### 5.2 传输与访问控制

- MQTT 优先使用 TLS（`mqtts`/8883），禁用匿名访问，启用账号密码认证。
- 为不同设备分配独立客户端 ID 与账号，避免共用同一凭据。
- 使用 ACL 限制主题访问：测量板只允许发布测量主题、订阅必要下行主题。
- MCP 端点必须使用 `wss://`，避免明文 WebSocket。

### 5.3 数据安全与隐私最小化

- MQTT 载荷仅保留业务必需字段（身高、体重、BMI、时间戳、仪器号），避免扩展采集身份证号/手机号等敏感身份信息。
- 如需长期留存，建议在服务端加密存储并设置数据保留周期与自动清理策略。
- 对外共享测试数据时使用脱敏样例，不直接导出真实体检记录。

### 5.4 设备与运维安全

- 关闭不必要调试接口，量产前关闭详细串口日志或降低日志级别。
- 对 OTA 包启用签名校验，拒绝未签名或篡改固件。
- 两块 ESP32 独立供电且仅共 GND，避免误接电源导致硬件损坏与异常行为。

---

## 6. 完整配置检查清单

### 测量板 `config.h`

- [ ] `CFG_WIFI_SSIDS` / `CFG_WIFI_PASSES` —— 填入正确的 **2.4 GHz** WiFi
- [ ] `CFG_MQTT_SERVER` —— MQTT Broker 地址（默认 `47.97.8.221`）
- [ ] `CFG_MQTT_PORT` —— 默认 `1883`
- [ ] `CFG_MCP_ENDPOINT` —— 替换为从小智控制台获取的完整 Token URL
- [ ] `CFG_INSTRUMENT_ID` —— 仪器编号，如 `HW-001`
- [ ] 提交代码前确认：`config.h` 中不包含真实密码/Token（或已加入本地忽略策略）

### 接线（共 4 根飞线）

**仪器 → 测量板**
- [ ] 身高体重仪 **TXD** → 测量板 **GPIO16 (RX2)**，协议 115200 8N1（606 标准协议）
- [ ] 身高体重仪 **GND** → 测量板 **GND**（共地）

**测量板 → 小智板**
- [ ] 测量板 **GPIO47** → 小智板 **GPIO38**（低电平触发唤醒，平时高电平，测量完成后拉低 200 ms）
- [ ] 测量板 **GND** → 小智板 **GND**（共地，两板禁止共 3.3V / 5V 电源）

### 小智板

- [ ] WiFi 已配网（BluFi / 热点任选其一）
- [ ] 控制台已创建 Agent 并获取 MCP Token
- [ ] 固件中 MCP 工具已注册（`mcp: true` 特性已编译进去）
- [ ] 生产环境已启用 MQTT 认证与 ACL（不使用匿名连接）

---

## 7. 常见问题

| 现象 | 排查方向 |
|------|---------|
| 测量板 WiFi 一直连不上 | 确认热点为 2.4 GHz；SmartConfig 超时后重新上电 |
| MQTT 发布失败 | 检查 Broker IP/端口、账号密码、ACL；确认设备证书/时间同步（TLS 场景） |
| MCP 连接失败（401） | Token 已过期，到小智控制台重新生成 |
| 小智不说话 | 检查 GPIO47→GPIO38 唤醒线；查看串口日志确认 MCP 工具被调用 |
| 两板 GND 未共地 | GPIO 电平不可靠，唤醒失效，务必接 GND |
| 小智 WiFi 掉线后不重连 | 确认固件开启了 `auto_reconnect`；BluFi 配网后凭据存 NVS 会自动重连 |
