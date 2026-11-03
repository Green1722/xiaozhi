#!/bin/bash
# 体检中心小智 MCP 服务 - 树莓派启动脚本

echo "正在启动体检中心小智 MCP 服务..."
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装 Python 3.7+"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 激活虚拟环境
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "激活虚拟环境..."
    source "$SCRIPT_DIR/venv/bin/activate"
else
    echo "警告: 未找到虚拟环境 venv/bin/activate，将使用系统 Python"
fi

# 安装依赖
echo "安装依赖..."
python3 -m pip install -r requirements.txt -q
if [ $? -ne 0 ]; then
    echo "错误: 依赖安装失败"
    exit 1
fi

# 环境变量
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export MCP_ENDPOINT="REPLACE_ME"
export MCP_CONFIG="$SCRIPT_DIR/mcp_config.json"

# 串口配置（树莓派通过RS232转USB连接体检机）
export SERIAL_ENABLED=true
export SERIAL_PORT=/dev/ttyUSB0
export SERIAL_BAUDRATE=115200

echo "MQTT: mqtt://47.97.8.221:1883"
echo "MCP: $MCP_ENDPOINT"
if [ "$SERIAL_ENABLED" = "true" ]; then
    echo "串口: $SERIAL_PORT (波特率: $SERIAL_BAUDRATE)"
else
    echo "串口: 未启用"
fi
echo "按 Ctrl+C 停止"
echo ""

# 启动服务
python3 "$SCRIPT_DIR/mcp_pipe.py" health-exam-service


