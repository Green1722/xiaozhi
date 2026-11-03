@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ====================================
echo   小智 MCP Server - UDP LED 控制
echo ====================================
echo.

:: 设置远端 ESP32 的 IP 地址
:: 请根据实际情况修改这个地址
set REMOTE_ESP32_IP=192.168.1.100

:: MCP 服务器端口
set MCP_PORT=8765

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 启动 MCP 服务器
echo [启动] 连接到远端 ESP32: %REMOTE_ESP32_IP%:8266
echo [启动] MCP 服务器端口: %MCP_PORT%
echo.
echo 按 Ctrl+C 停止服务器
echo.

python udp_mcp_server.py

pause
