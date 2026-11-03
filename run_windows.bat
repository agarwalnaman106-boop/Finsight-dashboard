@echo off
REM FinSight launcher for Windows. Double-click this file.
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 ( set PY=py -3.14 ) else ( set PY=python )

if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Could not create the environment. Check that Python 3.14 is installed and added to PATH.
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate.bat
echo Installing / checking packages (first run takes a few minutes)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo Package install failed. See the message above.
  pause
  exit /b 1
)

echo Starting FinSight at http://localhost:8501 ...
python -m streamlit run app.py
pause
