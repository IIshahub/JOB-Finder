@echo off
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist .venv\Scripts\python.exe goto ready
if exist "%PY%" (
  "%PY%" -m venv .venv
  goto ready
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m venv .venv
  goto ready
)
where python >nul 2>&1
if errorlevel 1 (
  echo Install Python 3 from https://www.python.org/downloads/ and check "Add Python to PATH".
  pause
  exit /b 1
)
python -m venv .venv
:ready
call .venv\Scripts\activate
python -m pip install -r requirements.txt
echo Open http://127.0.0.1:5050 in your browser
python app.py
pause
