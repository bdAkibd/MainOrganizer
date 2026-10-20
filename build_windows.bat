@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found.
    echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
    echo Enable the option to add Python to PATH, then run this file again.
    pause
    exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
    py -3 -m venv .venv-build
    if errorlevel 1 goto :error
)

call ".venv-build\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error
call ".venv-build\Scripts\python.exe" -m unittest discover -v
if errorlevel 1 goto :error
call ".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --onefile --name MainOrginizer main.py
if errorlevel 1 goto :error

echo.
echo Build complete: dist\MainOrginizer.exe
echo Python and application dependencies are included in the executable.
echo Share only dist\MainOrginizer.exe with testers.
pause
exit /b 0

:error
echo.
echo Build failed. Read the error messages above.
pause
exit /b 1
