@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ======================================
echo   小智 MCP Server - UDP LED 控制
echo ======================================
echo.
echo [配置信息]
echo   远端 ESP32 IP: %REMOTE_ESP32_IP%
echo   远端 ESP32 端口: 8266
echo   MCP 服务器端口: 8765
echo.
echo 按 Ctrl+C 停止服务器
echo.
echo 启动中...

:: 启动 MCP 服务器
"dist\xiaozhi_mcp_server.exe"

pause
