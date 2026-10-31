@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo JARVIS environment not found. Run setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\pythonw.exe" main.py
if errorlevel 1 (
    echo JARVIS exited with an error. Run ".venv\Scripts\python.exe main.py" to see diagnostics.
    pause
)
