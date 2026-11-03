@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ====================================
echo   小智 MCP LED 控制 - 打包工具
echo ====================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 检查 pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 pip，请检查 Python 安装
    pause
    exit /b 1
)

:: 安装依赖
echo [1/5] 安装 Python 依赖...
pip install -q paho-mqtt websockets python-dotenv
pip install -q mcp
echo [完成] 依赖安装完成

:: 检查 pyinstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [2/5] 安装 pyinstaller...
    pip install -q pyinstaller
)

:: 清理旧文件
echo [3/5] 清理旧构建...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

:: 打包
echo [4/5] 开始打包...
pyinstaller mqtt_mcp_server.spec --noconfirm

:: 复制配置文件
echo [5/5] 复制配置文件到 dist...
if exist "mcp_config.json" copy /y "mcp_config.json" "dist\xiaozhi_mqtt_server\"

echo.
echo ====================================
echo   打包完成！
echo ====================================
echo.
echo 可执行文件位于: dist\xiaozhi_mqtt_server\xiaozhi_mqtt_server.exe
echo.
echo 双击 "启动小智MCP.exe" 运行
echo.
pause
