@echo off
setlocal
cd /d "%~dp0"
call build_exe.bat onefile
exit /b %errorlevel%
