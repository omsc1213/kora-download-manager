@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -File "%~dp0Build-Rust.ps1"
exit /b %errorlevel%
