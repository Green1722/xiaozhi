@echo off
chcp 65001 >nul
title 微信MCP - STDIO模式

:: 加载环境变量
if exist ".env" for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
if not defined MCP_FOLDER_PATH set MCP_FOLDER_PATH=C:\Users\Administrator\Documents\mcp_wechat_history

echo [启动] 微信MCP服务 - STDIO模式
python -m mcp_server_wechat --folder-path "%MCP_FOLDER_PATH%"
pause
