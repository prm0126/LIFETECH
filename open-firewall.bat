@echo off
REM ===================================================================
REM  Open Windows Firewall so other PCs on the network can reach the
REM  LIFETECH dashboard on TCP port 8080.
REM  RIGHT-CLICK this file -> "Run as administrator".
REM ===================================================================
net session >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Please RIGHT-CLICK this file and choose "Run as administrator".
  pause
  exit /b 1
)

netsh advfirewall firewall delete rule name="LIFETECH Dashboard 8080" >nul 2>nul
netsh advfirewall firewall add rule name="LIFETECH Dashboard 8080" ^
  dir=in action=allow protocol=TCP localport=8080

echo.
echo Firewall rule added: inbound TCP 8080 is now allowed.
echo.
echo This machine's addresses (share http://THAT-IP:8080/ with your team):
ipconfig | findstr /C:"IPv4"
echo.
pause
