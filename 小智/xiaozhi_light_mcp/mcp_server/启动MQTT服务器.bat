@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================
echo   小智 MCP Server - MQTT LED 控制
echo ======================================
echo.
echo [配置信息]
echo   MQTT Broker: test.mosquitto.org:1883
echo   Command Topic: xiaozhi/led/command
echo   Status Topic: xiaozhi/led/status
echo   MCP Server Port: 8765
echo.
echo 按 Ctrl+C 停止服务器
echo.
echo 启动中...

:: 启动 MCP 服务器 (MQTT 版本)
"dist\xiaozhi_mqtt_server.exe"

pause
