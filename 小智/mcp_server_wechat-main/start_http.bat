@echo off
chcp 65001 >nul
title 微信MCP - Streamable HTTP模式

:: 加载环境变量
if exist ".env" for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
if not defined MCP_HOST set MCP_HOST=0.0.0.0
if not defined MCP_PORT set MCP_PORT=3000
if not defined MCP_FOLDER_PATH set MCP_FOLDER_PATH=C:\Users\Administrator\Documents\mcp_wechat_history
if not defined MCP_LOG_LEVEL set MCP_LOG_LEVEL=INFO

echo [启动] 微信MCP服务 - Streamable HTTP模式
echo [地址] http://%MCP_HOST%:%MCP_PORT%/mcp
python -m mcp_server_wechat_Streamable_HTTP --host %MCP_HOST% --port %MCP_PORT% --folder-path "%MCP_FOLDER_PATH%" --log-level %MCP_LOG_LEVEL%
pause
