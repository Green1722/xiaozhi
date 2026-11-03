@echo off
chcp 65001 >nul
echo 正在启动教室控制MCP服务...
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请先安装Python 3.7+
    pause
    exit /b 1
)


REM 设置环境变量
echo 设置编码环境...
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo 设置MCP端点...
set MCP_ENDPOINT=ws://124.222.47.162:8004/mcp_endpoint/mcp/?token=REPLACE_ME

echo 启动MCP服务...
echo MQTT服务器: mqtt://47.97.8.221:1883
echo MCP接入点: %MCP_ENDPOINT%
echo.
echo 按 Ctrl+C 停止服务
echo.

python mcp_pipe.py

pause
