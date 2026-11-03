@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ====================================
echo   小智 MCP LED 控制连接器
echo ====================================
echo.

:: 设置 MCP Endpoint (小智云服务)
set MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=REPLACE_ME

echo [启动] 连接到小智 MCP 服务...
echo [Endpoint] %MCP_ENDPOINT%
echo.
echo 按 Ctrl+C 停止
echo.

:: 运行 MCP Pipe
python mcp_pipe.py

pause
