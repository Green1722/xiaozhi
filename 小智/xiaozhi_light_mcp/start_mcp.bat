@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title MCP MQTT Server

:: ============================================
:: MCP MQTT Server Launcher (重构版)
:: 使用 mcp_pipe.py 通过 WebSocket 连接到 MCP 端点
:: ============================================

cd /d "%~dp0"

:: 检查并激活虚拟环境
if exist "venv\Scripts\activate.bat" (
    goto activate_venv
)

echo [INFO] 正在创建虚拟环境...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] 创建虚拟环境失败
    pause
    exit /b 1
)

:activate_venv
call venv\Scripts\activate.bat
pip install -q -r requirements.txt

:: 设置 MCP_ENDPOINT 环境变量（如果未设置）
if not defined MCP_ENDPOINT (
    set "MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=REPLACE_ME"
    echo [INFO] MCP_ENDPOINT 已设置为默认值
)

:: 获取本地 IP
set "LOCAL_IP=localhost"
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4"') do (
    set "ip=%%i"
    set "ip=!ip: =!"
    echo !ip! | findstr "169.254" >nul
    if errorlevel 1 (
        echo !ip! | findstr "127.0.0.1" >nul
        if errorlevel 1 (
            set "LOCAL_IP=!ip!"
        )
    )
)

echo.
echo ==============================================================
echo.
echo               MCP MQTT Server (重构版)
echo.
echo   MCP Endpoint: %MCP_ENDPOINT%
echo   本地 IP:       %LOCAL_IP%
echo.
echo ==============================================================
echo.

:: 使用 mcp_pipe.py 启动服务
python mcp_pipe.py

if errorlevel 1 (
    echo.
    echo [ERROR] 服务异常退出
)

pause
