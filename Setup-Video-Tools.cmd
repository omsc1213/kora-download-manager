@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Kora.ps1" setup-video-tools
set "kora_exit=%errorlevel%"
if errorlevel 1 pause
exit /b %kora_exit%

