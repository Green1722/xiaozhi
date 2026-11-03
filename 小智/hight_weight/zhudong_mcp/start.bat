@echo off
chcp 65001 >nul
echo 正在启动体检中心小智 MCP 服务...
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到 Python，请先安装 Python 3.7+
    pause
    exit /b 1
)

REM 安装依赖
echo 安装依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo 错误: 依赖安装失败
    pause
    exit /b 1
)

REM 环境变量
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=REPLACE_ME
set MCP_CONFIG=%~dp0mcp_config.json

echo MQTT: mqtt://47.97.8.221:1883
echo MCP: %MCP_ENDPOINT%
echo 按 Ctrl+C 停止
echo.

python "%~dp0mcp_pipe.py" health-exam-service

pause
