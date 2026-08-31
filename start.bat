@echo off
setlocal

REM ============================================================
REM  Admin Server - Start
REM  Double-click this to set up (first time only) and launch
REM  the admin server, then open the admin login in your browser.
REM ============================================================

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on this computer.
    echo Install it from https://www.python.org/downloads/
    echo During installation, check "Add Python to PATH", then run this again.
    pause
    exit /b 1
)

if not exist "venv" (
    echo Setting up for the first time - this only happens once...
    python -m venv venv
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip >nul
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo.
echo Starting the admin server...
start "Admin Server" cmd /k "cd /d "%~dp0" && call venv\Scripts\activate.bat && python app.py"

echo Waiting for it to be ready...
powershell -NoProfile -Command ^
  "$ready = $false; for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:5001/admin/login' -UseBasicParsing -TimeoutSec 1 | Out-Null; $ready = $true; break } catch { Start-Sleep -Milliseconds 250 } }; if (-not $ready) { exit 1 }"

if errorlevel 1 (
    echo The server is taking longer than usual to start.
    echo Opening the browser anyway - refresh the page if it doesn't load yet.
)

start "" http://127.0.0.1:5001/admin

exit /b 0
