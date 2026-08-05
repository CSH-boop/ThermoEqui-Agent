@echo off
setlocal enabledelayedexpansion
title ThermoEqui-Agent

cd /d "%~dp0"

echo ============================================
echo   ThermoEqui-Agent - Launcher
echo ============================================
echo.

echo [1/2] Starting backend API (FastAPI on :8000)...
start "ThermoEqui-Backend" cmd /k "cd /d ""%~dp0"" && python -m uvicorn apps.api.main:app --reload --port 8000"

echo Waiting for backend...
set waited=0
:wait_backend
python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" 2>nul
if !errorlevel!==0 goto backend_ready
set /a waited+=1
if !waited! geq 30 goto backend_ready
timeout /t 2 /nobreak >nul
goto wait_backend

:backend_ready
echo [2/2] Starting frontend (Next.js on :3000)...
start "ThermoEqui-Frontend" cmd /k "cd /d ""%~dp0""apps\web && npm run dev"

echo Waiting for frontend...
set waited=0
:wait_frontend
python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000', timeout=2)" 2>nul
if !errorlevel!==0 goto frontend_ready
set /a waited+=1
if !waited! geq 60 goto frontend_ready
timeout /t 2 /nobreak >nul
goto wait_frontend

:frontend_ready
echo Opening browser...
start http://localhost:3000

echo.
echo ============================================
echo   Done!
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000/docs
echo   Close this window does not stop services.
echo   To stop, close the two black windows.
echo ============================================
echo.
pause
endlocal
