@echo off
setlocal
set "TUNER_PYTHON=%USERPROFILE%\miniconda3\envs\surgeryBox\python.exe"
if exist "%TUNER_PYTHON%" (
  "%TUNER_PYTHON%" "%~dp0motor_tuner.py"
) else (
  python "%~dp0motor_tuner.py"
)
if errorlevel 1 pause
