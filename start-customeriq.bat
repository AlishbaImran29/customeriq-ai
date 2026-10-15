@echo off
setlocal
cd /d "%~dp0"
title CustomerIQ AI starter

rem Double-click this file to start CustomerIQ AI on your computer.
rem Run "start-customeriq.bat check" to test the setup without starting anything.

if not defined CIQ_BACKEND_PORT set CIQ_BACKEND_PORT=8000
if not defined CIQ_SITE_PORT set CIQ_SITE_PORT=3001

echo.
echo   CustomerIQ AI
echo   =============
echo.

rem --- 1. The one-time setup must be done ---
if not exist "backend\.venv\Scripts\python.exe" (
  echo   [!] The backend is not set up yet. Open README.md and follow "First-time setup".
  echo.
  pause
  exit /b 1
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo   [!] Node.js was not found. Install it from https://nodejs.org and run this again.
  echo.
  pause
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo   First run: installing the website packages. This can take a few minutes...
  pushd frontend
  call npm.cmd install
  popd
)

rem --- 2. The ports must be free ---
netstat -ano | findstr /R /C:":%CIQ_BACKEND_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo   [!] Port %CIQ_BACKEND_PORT% is already in use. Is CustomerIQ already running?
  echo       Close its old black windows ^(or old VS Code terminals^) and try again.
  echo.
  pause
  exit /b 1
)
netstat -ano | findstr /R /C:":%CIQ_SITE_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo   [!] Port %CIQ_SITE_PORT% is already in use. Is CustomerIQ already running?
  echo       Close its old black windows ^(or old VS Code terminals^) and try again.
  echo.
  pause
  exit /b 1
)

if /i "%~1"=="check" (
  echo   All checks passed. Nothing was started because this was a check run.
  exit /b 0
)

rem --- 3. Start the backend and the website, then open the browser ---
start "CustomerIQ backend - keep this window open" /d "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port %CIQ_BACKEND_PORT%"
start "CustomerIQ website - keep this window open" /d "%~dp0frontend" cmd /k "npm.cmd run dev -- --port %CIQ_SITE_PORT%"

echo   Starting... your browser opens in about 15 seconds.
timeout /t 15 /nobreak >nul
start "" "http://localhost:%CIQ_SITE_PORT%"

echo.
echo   Done! CustomerIQ is at  http://localhost:%CIQ_SITE_PORT%
echo   To STOP the app, close the two black windows named "backend" and "website".
echo.
pause
