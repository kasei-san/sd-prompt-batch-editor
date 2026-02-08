@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0"

REM Load .env
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "%%A=%%B"
    )
)

if not defined APP_PORT set APP_PORT=4644

REM Create venv if not exists
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install dependencies
pip install -r requirements.txt -q

REM Open browser
start "" http://localhost:%APP_PORT%

REM Start server
python app.py

pause
