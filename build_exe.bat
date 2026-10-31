@echo off
setlocal
cd /d "%~dp0"

set "BUILD_MODE=%~1"
if "%BUILD_MODE%"=="" set "BUILD_MODE=all"
if /I not "%BUILD_MODE%"=="all" if /I not "%BUILD_MODE%"=="onedir" if /I not "%BUILD_MODE%"=="onefile" (
    echo Usage: build_exe.bat [all^|onedir^|onefile]
    exit /b 2
)

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install 64-bit Python 3.11 from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

py -3.11 --version >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 was not found. Install it and enable the Python Launcher.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating isolated Python 3.11 build environment...
    py -3.11 -m venv .venv
    if errorlevel 1 goto failed
)

echo Installing application and packaging dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo Validating Python sources...
".venv\Scripts\python.exe" -m compileall -q main.py config.py jarvis
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import tkinter, pyttsx3, PyInstaller; print('Build imports validated.')"
if errorlevel 1 goto failed

set "ICON_ARGS="
set "BUILD_ROOT=%TEMP%\JARVIS-PyInstaller-%RANDOM%-%RANDOM%"
set "DIST_NAME=release-%RANDOM%-%RANDOM%"
set "DIST_ROOT=dist\%DIST_NAME%"
mkdir "%BUILD_ROOT%"
if errorlevel 1 goto failed
if not exist "%DIST_ROOT%" mkdir "%DIST_ROOT%"
if errorlevel 1 goto failed
echo Staging packaged assets outside the synchronized project folder...
xcopy /E /I /Y "assets" "%BUILD_ROOT%\assets" >nul
if errorlevel 1 goto failed
if exist "%BUILD_ROOT%\assets\jarvis.ico" (
    set ICON_ARGS=--icon "%BUILD_ROOT%\assets\jarvis.ico"
)
if not exist "%BUILD_ROOT%\assets\jarvis.ico" echo Icon not found; continuing with the Windows default icon.

if /I not "%BUILD_MODE%"=="onefile" (
    echo Building portable onedir application...
    ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onedir --name "JARVIS-AI" --distpath "%DIST_ROOT%" --workpath "%BUILD_ROOT%\onedir-work" %ICON_ARGS% --add-data "%BUILD_ROOT%\assets;assets" --add-data "dashboard.html;." --add-data "dashboard.css;." --add-data "dashboard.js;." --hidden-import "pyttsx3.drivers.sapi5" main.py
    if errorlevel 1 goto failed
    if not exist "%DIST_ROOT%\JARVIS-AI\JARVIS-AI.exe" (
        echo PyInstaller completed but the expected onedir executable was not produced.
        goto failed
    )
)

if /I not "%BUILD_MODE%"=="onedir" (
    echo Building optional single-file executable...
    ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onefile --name "JARVIS-AI" --distpath "%DIST_ROOT%" --workpath "%BUILD_ROOT%\onefile-work" %ICON_ARGS% --add-data "%BUILD_ROOT%\assets;assets" --add-data "dashboard.html;." --add-data "dashboard.css;." --add-data "dashboard.js;." --hidden-import "pyttsx3.drivers.sapi5" main.py
    if errorlevel 1 goto failed
    if not exist "%DIST_ROOT%\JARVIS-AI.exe" (
        echo PyInstaller completed but the expected single-file executable was not produced.
        goto failed
    )
)

rmdir /s /q "%BUILD_ROOT%"
> "dist\current_build.txt" echo %DIST_NAME%
if not exist "dist\current_build.txt" goto failed
echo.
echo Build completed successfully:
if /I not "%BUILD_MODE%"=="onefile" echo   Portable: %DIST_ROOT%\JARVIS-AI\JARVIS-AI.exe
if /I not "%BUILD_MODE%"=="onedir" echo   Single file: %DIST_ROOT%\JARVIS-AI.exe
echo.
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above. No success is reported unless both EXE paths exist.
echo Temporary PyInstaller work files were kept in "%BUILD_ROOT%" for diagnosis.
pause
exit /b 1
