@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Launch-Kora.ps1" %*
set "kora_exit=%errorlevel%"
if not "%kora_exit%"=="0" pause
exit /b %kora_exit%