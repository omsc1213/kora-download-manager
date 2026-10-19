@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0Launch-Kora.ps1" setup-video-tools
if errorlevel 1 pause
exit /b %errorlevel%
