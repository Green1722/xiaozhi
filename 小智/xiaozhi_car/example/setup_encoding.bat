@echo off
REM 设置控制台编码为UTF-8
chcp 65001 >nul

REM 设置Python环境变量
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo 编码设置完成
echo 控制台编码: UTF-8
echo Python编码: UTF-8
echo.

REM 启动服务
call start_simple.bat
