@echo off
setlocal
if not defined KLM_PYTHON set "KLM_PYTHON=%USERPROFILE%\.platformio\penv\Scripts\python.exe"
if not exist "%KLM_PYTHON%" (
  echo Set KLM_PYTHON to a Python executable with pyserial installed.
  pause
  exit /b 1
)
"%KLM_PYTHON%" -X utf8 "%~dp0console.py" --say %*
if errorlevel 1 pause
