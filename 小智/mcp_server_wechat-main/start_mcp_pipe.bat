@echo off
chcp 65001 >nul
title 微信MCP - 小智桥接服务

:: 加载环境变量
if exist ".env" for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

echo ============================================
echo     微信MCP 桥接到小智 WebSocket
echo ============================================
echo.
echo [接入点] %MCP_ENDPOINT%
echo [配置文件] mcp_config.json
echo.
echo 启动中...
echo.

python mcp_pipe.py

pause
