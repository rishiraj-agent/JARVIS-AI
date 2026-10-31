@echo off
setlocal
cd /d "%~dp0"

rem Run the edited source so an older packaged EXE cannot bring back removed cloud APIs.
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py"
    exit /b 0
)

where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pythonw.exe "main.py"
    exit /b 0
)

where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" pyw.exe -3 "main.py"
    exit /b 0
)

echo Python with Tkinter was not found. Run setup.bat or install Python 3.11+ with Tkinter.
pause
exit /b 1
