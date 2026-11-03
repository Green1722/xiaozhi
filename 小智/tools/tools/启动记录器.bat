@echo off
chcp 65001 >nul 2>&1
title 小智 AI 对话记录器

cd /d "%~dp0"

REM 检查是否安装了 pyserial
python -c "import serial" 2>nul
if errorlevel 1 (
    echo [INFO] Installing pyserial...
    pip install pyserial >nul 2>&1
)

echo [INFO] Starting recorder...
echo [INFO] Press Ctrl+C to stop
echo.

python chat_recorder.py

pause >nul
