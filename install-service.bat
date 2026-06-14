@echo off
REM ===================================================================
REM  Install the LIFETECH dashboard as an auto-start background task
REM  using Windows Task Scheduler (no extra software needed).
REM  It runs at every boot, as SYSTEM, even with nobody logged in.
REM  RIGHT-CLICK this file -> "Run as administrator".
REM ===================================================================
setlocal
net session >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Please RIGHT-CLICK this file and choose "Run as administrator".
  pause
  exit /b 1
)

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "PY=%DIR%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] Virtual environment not found at:
  echo        %PY%
  echo Run run.bat once first to create it, then re-run this file.
  pause
  exit /b 1
)

echo Installing scheduled task "LIFETECH Dashboard"...
schtasks /Create /TN "LIFETECH Dashboard" /SC ONSTART /RU SYSTEM /RL HIGHEST /F ^
  /TR "cmd /c cd /d \"%DIR%\" && \"%PY%\" serve.py"

if errorlevel 1 ( echo [ERROR] Could not create the task. & pause & exit /b 1 )

echo Starting it now...
schtasks /Run /TN "LIFETECH Dashboard"

echo.
echo ============================================================
echo  Done. The dashboard is running and will auto-start on boot.
echo  Open the firewall once (open-firewall.bat as admin), then
echo  share http://THIS-PC-IP:8080/ with your team.
echo.
echo  To stop:    schtasks /End    /TN "LIFETECH Dashboard"
echo  To remove:  schtasks /Delete /TN "LIFETECH Dashboard" /F
echo ============================================================
ipconfig | findstr /C:"IPv4"
pause
