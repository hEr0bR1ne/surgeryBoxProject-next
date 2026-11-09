@echo off
setlocal
set "HARDWARE_PYTHON=%USERPROFILE%\miniconda3\envs\surgeryBox\python.exe"
if exist "%HARDWARE_PYTHON%" (
  "%HARDWARE_PYTHON%" "%~dp0v3_test_client.py" --port COM4
) else (
  python "%~dp0v3_test_client.py" --port COM4
)
if errorlevel 1 pause
