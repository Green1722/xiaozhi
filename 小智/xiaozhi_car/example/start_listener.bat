@echo off
chcp 65001 >nul
echo 启动MQTT消息监听器...
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请先安装Python 3.7+
    pause
    exit /b 1
)

REM 设置编码环境
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo MQTT服务器: mqtt://47.97.8.221:1883
echo.
echo 使用方法:
echo   python mqtt_listener.py                    # 监听所有主题
echo   python mqtt_listener.py --topic fan        # 只监听风扇主题
echo   python mqtt_listener.py --topic light      # 只监听电灯主题
echo   python mqtt_listener.py --topic status     # 只监听状态主题
echo   python mqtt_listener.py --filter "action"  # 过滤包含特定关键词的消息
echo.
echo 按 Ctrl+C 停止监听
echo.

python mqtt_listener.py

pause
