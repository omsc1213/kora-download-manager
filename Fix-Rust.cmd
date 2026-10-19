@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0Setup-Rust.ps1"
if errorlevel 1 pause
exit /b %errorlevel%
