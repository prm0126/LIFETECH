@echo off
REM ===================================================================
REM  LIFETECH dashboard launcher for Windows
REM  Double-click this file, or run it from a command prompt.
REM  First run: creates a virtual env, installs deps, makes a .env.
REM ===================================================================
setlocal
cd /d "%~dp0"

REM --- 1. Check Python is available -----------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python is not installed or not on PATH.
  echo Install Python 3 from https://www.python.org/downloads/windows/
  echo During setup, TICK "Add python.exe to PATH", then re-run this file.
  pause
  exit /b 1
)

REM --- 2. Create a virtual environment on first run -------------------
if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)

REM --- 3. Install / update dependencies -------------------------------
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed. See messages above.
  pause
  exit /b 1
)

REM --- 4. Create .env from the template on first run ------------------
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo ============================================================
  echo  A new .env file was created.
  echo  Open it in Notepad and set:
  echo     ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
  echo  Then run this file again to start the dashboard.
  echo ============================================================
  notepad ".env"
  pause
  exit /b 0
)

REM --- 5. Start the dashboard -----------------------------------------
echo Starting LIFETECH dashboard...
python serve.py
pause
