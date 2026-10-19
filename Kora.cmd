@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" if exist "%~dp0runtime\pythonw.exe" (
  start "" /D "%~dp0" "%~dp0runtime\pythonw.exe" "%~dp0kora.py"
  exit /b 0
)
if exist "%~dp0kora.exe" (
  "%~dp0kora.exe" %*
) else (
  powershell.exe -NoProfile -File "%~dp0Launch-Kora.ps1" %*
)
if errorlevel 1 pause
