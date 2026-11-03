@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ====================================
echo   MCP Server (MQTT) 打包工具
echo ====================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 安装依赖
echo [1/4] 安装 Python 依赖 (paho-mqtt)...
pip install -q paho-mqtt

:: 清理旧文件
echo [2/4] 清理旧构建...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

:: 打包
echo [3/4] 开始打包...
pyinstaller mqtt_mcp_server.spec --noconfirm

:: 复制配置文件
echo [4/4] 复制配置文件到 dist...
if exist "config.py" copy /y "config.py" "dist\xiaozhi_mqtt_server\"

echo.
echo ====================================
echo   打包完成！
echo ====================================
echo.
echo 可执行文件位于: dist\xiaozhi_mqtt_server\
echo.
echo 使用前请先修改 config.py 中的 MQTT Broker 地址
echo.
pause
