@echo off
setlocal
cd /d "%~dp0"
call build_exe.bat onedir
exit /b %errorlevel%
