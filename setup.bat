@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install Python 3.11 from https://www.python.org/downloads/windows/
    echo Enable "Add python.exe to PATH" and "Install launcher for all users" during setup.
    pause
    exit /b 1
)

py -3.11 --version >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 is required but was not found.
    echo Install Python 3.11 from https://www.python.org/downloads/windows/ and run setup.bat again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 goto failed
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo JARVIS setup completed.
echo Start the application with start_jarvis.bat
pause
exit /b 0

:failed
echo.
echo Setup failed. Check your internet connection, then review the troubleshooting section in README.md.
pause
exit /b 1
