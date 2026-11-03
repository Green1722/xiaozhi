@echo off
chcp 65001 >nul
echo Starting Car Control MCP Service...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python 3.7+ not found, please install Python first
    pause
    exit /b 1
)

REM Check if venv exists, create if not
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip and install dependencies
echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)

REM Set environment variables
echo Setting encoding environment...
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo Setting MCP endpoint...
set MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=REPLACE_ME

echo Starting Car Control MCP Service...
echo MQTT Server: mqtt://112.124.37.216:1883
echo Topic: yahboomcar/cmd
echo MCP Endpoint: %MCP_ENDPOINT%
echo.
echo Available tools:
echo - move_car: General movement control (linear_x, linear_y, angular_z, duration, rotate_deg, stop)
echo - move_forward_continuous: Continuous forward movement
echo - move_backward_continuous: Continuous backward movement
echo - strafe_left_continuous: Continuous left strafe
echo - strafe_right_continuous: Continuous right strafe
echo - rotate_left_continuous: Continuous left rotation
echo - rotate_right_continuous: Continuous right rotation
echo - move_forward_steps: Move forward specific steps then stop
echo - move_backward_steps: Move backward specific steps then stop
echo - rotate_left_90: Rotate left 90 degrees then stop
echo - rotate_right_90: Rotate right 90 degrees then stop
echo - move_forward_turn_left: Forward + left turn
echo - move_forward_turn_right: Forward + right turn
echo - move_backward_turn_left: Backward + left turn
echo - move_backward_turn_right: Backward + right turn
echo - send_string_command: Send simplified string command
echo - execute_instruction_sequence: Execute instruction sequence (natural language)
echo - get_car_status: Get car status
echo - send_custom_command: Send custom command
echo - get_response_messages: Get response messages
echo - clear_response_messages: Clear response messages
echo.
echo Press Ctrl+C to stop the service
echo.

python mcp_pipe.py

pause
