@echo off
setlocal
title Bili Songdesk - GUI Test
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python 3.12 and project dependencies.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Starting Bili Songdesk GUI...
python main_gui.py
set "result=%errorlevel%"
if not "%result%"=="0" (
    echo [ERROR] GUI exited with code %result%.
    pause
)
exit /b %result%
