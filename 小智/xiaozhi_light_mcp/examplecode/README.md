# 教室控制MCP服务 | Classroom Control MCP Service

一个基于MCP (Model Context Protocol) 的教室设备控制服务，通过MQTT协议控制教室的风扇和电灯设备。

A classroom device control service based on MCP (Model Context Protocol) that controls classroom fans and lights through MQTT protocol.

## 功能特性 | Features

- **风扇控制**: 支持开关控制和0-3档速度调节 | Fan Control: Support on/off and 0-3 speed levels
- **电灯控制**: 支持开关控制和0-100%亮度调节 | Light Control: Support on/off and 0-100% brightness
- **MQTT通信**: 通过TCP协议与MQTT服务器通信 | MQTT Communication: Communicate with MQTT server via TCP protocol
- **批量控制**: 支持同时控制多个设备 | Batch Control: Support controlling multiple devices simultaneously
- **状态查询**: 实时获取设备状态信息 | Status Query: Real-time device status information
- **自动重连**: 具有指数退避的自动重连机制 | Auto Reconnection: Automatic reconnection with exponential backoff

## 快速开始 | Quick Start

### 1. 安装依赖 | Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. 设置环境变量 | Set Environment Variables

```bash
# Linux/Mac
export MCP_ENDPOINT=ws://124.222.47.162:8004/mcp_endpoint/mcp/?token=REPLACE_ME

# Windows (PowerShell)
$env:MCP_ENDPOINT = "REPLACE_ME"
```

### 3. 启动服务 | Start Service

#### 方式1: 使用批处理脚本（推荐）| Method 1: Using Batch Script (Recommended)

```bash
# Windows
start.bat
```

#### 方式2: 直接运行 | Method 2: Direct Run

```bash
# 运行所有配置的服务 | Run all configured servers
python mcp_pipe.py

# 运行单个服务 | Run single server
python mcp_pipe.py classroom_control.py
```

## MCP工具说明 | MCP Tools Description

### 1. control_fan - 风扇控制 | Fan Control

控制教室风扇的开关和速度 | Control classroom fan on/off and speed.

**参数 | Parameters:**
- `action` (必需 | Required): 操作类型 | Operation type
  - `"on"`: 开启风扇 | Turn on fan
  - `"off"`: 关闭风扇 | Turn off fan
  - `"speed"`: 调整速度 | Adjust speed
- `speed` (可选 | Optional): 速度档位 (0-3档) | Speed level (0-3 levels)

**示例 | Example:**
```json
{
  "action": "on",
  "speed": 2
}
```

### 2. control_light - 电灯控制 | Light Control

控制教室电灯的开关和亮度 | Control classroom light on/off and brightness.

**参数 | Parameters:**
- `action` (必需 | Required): 操作类型 | Operation type
  - `"on"`: 开启电灯 | Turn on light
  - `"off"`: 关闭电灯 | Turn off light
  - `"brightness"`: 调整亮度 | Adjust brightness
- `brightness` (可选 | Optional): 亮度百分比 (0-100%) | Brightness percentage (0-100%)

**示例 | Example:**
```json
{
  "action": "brightness",
  "brightness": 75
}
```

### 3. get_device_status - 获取设备状态 | Get Device Status

获取所有设备的当前状态信息 | Get current status of all devices.

**参数 | Parameters:** 无 | None

**返回示例 | Return Example:**
```json
{
  "success": true,
  "devices": {
    "fan": {
      "on": true,
      "speed": 2
    },
    "light": {
      "on": true,
      "brightness": 75
    }
  },
  "mqtt_connected": true,
  "timestamp": "2024-01-01 12:00:00"
}
```

### 4. control_multiple_devices - 批量控制 | Batch Control

同时控制多个设备 | Control multiple devices simultaneously.

**参数 | Parameters:**
- `commands` (必需 | Required): 命令列表 | Command list

**示例 | Example:**
```json
{
  "commands": [
    {
      "device": "fan",
      "action": "on",
      "value": 2
    },
    {
      "device": "light",
      "action": "brightness",
      "value": 50
    }
  ]
}
```

## 配置说明 | Configuration

### MQTT服务器配置 | MQTT Server Configuration

服务配置为连接到以下MQTT服务器 | Service configured to connect to the following MQTT server:
- **地址 | Address**: `mqtt://47.97.8.221:1883`
- **协议 | Protocol**: MQTT TCP (标准MQTT协议 | Standard MQTT protocol)
- **客户端ID | Client ID**: `classroom-control-mcp`

### MCP接入点 | MCP Endpoint

- **端点 | Endpoint**: `ws://124.222.47.162:8004/mcp_endpoint/mcp/?token=REPLACE_ME

### 主题配置 | Topic Configuration

- **风扇控制 | Fan Control**: `classroom/fan/control`
- **电灯控制 | Light Control**: `classroom/light/control`
- **状态订阅 | Status Subscription**: `classroom/status`

## 消息格式 | Message Format

### 风扇控制消息 | Fan Control Message

```json
{
  "action": "on|off|speed",
  "speed": 0-3,
  "timestamp": "2024-01-01T12:00:00"
}
```

### 电灯控制消息 | Light Control Message

```json
{
  "action": "on|off|brightness",
  "brightness": 0-100,
  "timestamp": "2024-01-01T12:00:00"
}
```

## 使用示例 | Usage Examples

### 开启风扇并设置为2档 | Turn on fan and set to level 2
```bash
# 通过MCP客户端调用 | Via MCP client call
control_fan({"action": "on", "speed": 2})
```

### 调整电灯亮度为50% | Adjust light brightness to 50%
```bash
# 通过MCP客户端调用 | Via MCP client call
control_light({"action": "brightness", "brightness": 50})
```

### 同时控制风扇和电灯 | Control fan and light simultaneously
```bash
# 通过MCP客户端调用 | Via MCP client call
control_multiple_devices({
  "commands": [
    {"device": "fan", "action": "off"},
    {"device": "light", "action": "on", "value": 80}
  ]
})
```

## 项目结构 | Project Structure

```
classroom-control-mcp/
├── classroom_control.py    # 主要的MCP服务文件 | Main MCP service file
├── mcp_pipe.py            # MCP通信管道 | MCP communication pipe
├── mcp_config.json        # MCP配置文件 | MCP configuration file
├── requirements.txt       # Python依赖 | Python dependencies
├── start.bat             # Windows启动脚本 | Windows startup script
└── README.md             # 使用说明文档 | Usage documentation
```

## 环境要求 | Requirements

- Python 3.7+
- paho-mqtt>=1.6.1
- websockets>=11.0.3
- python-dotenv>=1.0.0
- mcp>=1.8.1
- pydantic>=2.11.4
- mcp-proxy>=0.8.2

## 错误处理 | Error Handling

服务包含完整的错误处理机制 | Service includes comprehensive error handling:

- MQTT连接失败时会自动重连 | Automatic reconnection on MQTT connection failure
- 设备控制失败时会返回详细错误信息 | Detailed error information on device control failure
- 参数验证确保输入值的有效性 | Parameter validation ensures input value validity

## 日志输出 | Log Output

服务运行时会输出详细的日志信息 | Service outputs detailed log information during runtime:

- 成功操作 | Successful operations
- 错误信息 | Error messages
- 警告信息 | Warning messages
- 重连状态 | Reconnection status

## 许可证 | License

MIT License

## 致谢 | Acknowledgments

- 基于MCP计算器示例项目 | Based on MCP calculator example project
- 感谢所有贡献者 | Thanks to all contributors
