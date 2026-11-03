@echo off
chcp 65001 >nul
title 微信MCP - SSE模式

:: 加载环境变量
if exist ".env" for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
if not defined MCP_HOST set MCP_HOST=0.0.0.0
if not defined MCP_PORT set MCP_PORT=3000
if not defined MCP_FOLDER_PATH set MCP_FOLDER_PATH=C:\Users\Administrator\Documents\mcp_wechat_history

echo [启动] 微信MCP服务 - SSE模式
echo [地址] http://%MCP_HOST%:%MCP_PORT%/sse
python -m mcp_server_wechat_sse --host %MCP_HOST% --port %MCP_PORT% --folder-path "%MCP_FOLDER_PATH%"
pause
