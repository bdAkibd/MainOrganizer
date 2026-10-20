@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found.
    echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

if not exist ".venv-dev\Scripts\python.exe" (
    py -3 -m venv .venv-dev
    if errorlevel 1 goto :error
)

call ".venv-dev\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
call ".venv-dev\Scripts\python.exe" main.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Startup failed. Read the error messages above.
pause
exit /b 1
