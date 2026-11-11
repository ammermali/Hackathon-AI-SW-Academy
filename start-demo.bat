@echo off
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "DEMO_ARGS="
if /i "%~1"=="--no-browser" set "DEMO_ARGS=-NoBrowser"
if /i "%~1"=="-NoBrowser" set "DEMO_ARGS=-NoBrowser"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_demo.ps1" %DEMO_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERRORE] Avvio demo terminato con codice %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
