@echo off
setlocal

set "SPEAK_PORT=%~1"
if "%SPEAK_PORT%"=="" set "SPEAK_PORT=COM4"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\speak.ps1" -Port "%SPEAK_PORT%"
if errorlevel 1 (
  echo.
  echo Failed. Make sure no serial monitor is using %SPEAK_PORT%, then try again.
)
echo.
pause
