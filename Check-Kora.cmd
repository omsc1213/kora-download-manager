@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Kora.ps1" doctor
set "kora_exit=%errorlevel%"
pause
exit /b %kora_exit%
