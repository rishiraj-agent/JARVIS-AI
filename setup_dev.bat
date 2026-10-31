@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Development environment not found. Run setup.bat once to prepare Python 3.11.
    exit /b 1
)

echo Running local JARVIS checks. No hosted AI or pretrained model is used.
".venv\Scripts\python.exe" -m compileall -q main.py config.py jarvis
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 exit /b 1

echo Development checks completed.
