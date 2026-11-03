@echo off
chcp 65001 >nul
title 微信MCP服务启动器

echo ============================================
echo        微信MCP服务一键启动脚本
echo ============================================
echo.

:: 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python并添加到PATH
    pause
    exit /b 1
)

:: 加载环境变量配置（如果存在）
if exist ".env" (
    echo [信息] 加载 .env 配置文件...
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
)

:: 默认配置
if not defined MCP_HOST set MCP_HOST=0.0.0.0
if not defined MCP_PORT set MCP_PORT=3000
if not defined MCP_FOLDER_PATH set MCP_FOLDER_PATH=C:\Users\Administrator\Documents\mcp_wechat_history
if not defined MCP_LOG_LEVEL set MCP_LOG_LEVEL=INFO

echo.
echo [配置信息]
echo   监听地址: %MCP_HOST%
echo   监听端口: %MCP_PORT%
echo   聊天记录路径: %MCP_FOLDER_PATH%
echo   日志级别: %MCP_LOG_LEVEL%
echo.

:: 选择启动模式
echo 请选择启动模式:
echo   1. STDIO模式 (标准输入输出，用于本地MCP客户端)
echo   2. SSE模式 (Server-Sent Events，用于Web客户端)
echo   3. Streamable HTTP模式 (HTTP流式传输，推荐)
echo.
set /p mode="请输入选项 (1/2/3): "

if "%mode%"=="1" (
    echo.
    echo [启动] STDIO模式...
    python -m mcp_server_wechat --folder-path "%MCP_FOLDER_PATH%"
) else if "%mode%"=="2" (
    echo.
    echo [启动] SSE模式 - http://%MCP_HOST%:%MCP_PORT%/sse
    python -m mcp_server_wechat_sse --host %MCP_HOST% --port %MCP_PORT% --folder-path "%MCP_FOLDER_PATH%"
) else if "%mode%"=="3" (
    echo.
    echo [启动] Streamable HTTP模式 - http://%MCP_HOST%:%MCP_PORT%/mcp
    python -m mcp_server_wechat_Streamable_HTTP --host %MCP_HOST% --port %MCP_PORT% --folder-path "%MCP_FOLDER_PATH%" --log-level %MCP_LOG_LEVEL%
) else (
    echo [错误] 无效选项，请输入 1、2 或 3
    pause
    exit /b 1
)

pause
