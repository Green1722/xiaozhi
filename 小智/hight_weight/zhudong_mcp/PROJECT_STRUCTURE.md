# 项目结构说明

## 目录结构

```
zhudong_mcp/
├── README.md                    # 项目说明与运行指南
├── requirements.txt             # Python 依赖列表
├── mcp_config.json              # MCP 服务配置文件
├── .gitignore                   # Git 忽略文件配置
│
├── physical_exam_control.py     # 主程序：体检中心 MCP 服务
├── mcp_pipe.py                  # MCP 管道：连接小智 MCP 端点
├── serial_reader.py             # 串口读取模块（支持606协议）
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
└── tests/                       # 测试工具目录
    └── test_serial.py           # 串口通信测试脚本
```

## 文件说明

### 核心程序文件

- **physical_exam_control.py**: 主程序，实现体检数据处理、MQTT通信、MCP工具等功能
- **mcp_pipe.py**: MCP管道程序，连接小智MCP WebSocket端点
- **serial_reader.py**: 串口读取模块，支持606协议，从体检机读取身高体重数据

### 配置文件

- **mcp_config.json**: MCP服务配置，定义服务名称和启动参数
- **requirements.txt**: Python依赖包列表
- **.gitignore**: Git版本控制忽略文件配置

### 启动脚本

- **start.sh**: Linux/树莓派启动脚本，自动配置环境变量并启动服务
- **start.bat**: Windows启动脚本

### 文档目录 (docs/)

- **websocket.md**: WebSocket协议文档，说明小智设备通信方式
- **606.md**: 606通信协议详细文档，包含协议格式和命令说明
- **DATA_FLOW.md**: 数据流程说明，解释数据如何在系统中流转
- **SERIAL_COMMUNICATION.md**: 串口通信设置和故障排查指南
- **XIAOZHI_TROUBLESHOOTING.md**: 小智不发声问题排查指南
- **DEPLOY_RASPBERRY_PI.md**: 树莓派部署详细步骤

### 测试目录 (tests/)

- **test_serial.py**: 串口通信测试脚本，用于调试和测试串口功能

## 优化说明

1. **文档整理**: 将所有文档文件移动到 `docs/` 目录，使项目根目录更清晰
2. **测试分离**: 将测试脚本移动到 `tests/` 目录，便于管理
3. **版本控制**: 添加 `.gitignore` 文件，忽略不必要的文件
4. **结构清晰**: 更新 README.md 中的项目结构说明，反映实际目录结构

