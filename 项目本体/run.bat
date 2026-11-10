@echo off
title AI Radar
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found.
    echo Please make sure run.bat is inside the project root folder.
    echo.
    pause
    exit /b 1
)

echo ============================================
echo   AI Radar - AI Frontier News Workbench
echo.
echo   Starting server, please wait ...
echo   URL:  http://127.0.0.1:8002
echo   Press Ctrl+C to stop
echo ============================================
echo.

REM Open the browser after 3 seconds (non-blocking)
start "" powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8002'"

".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8002

echo.
echo Server stopped.
pause
