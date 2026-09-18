@echo off
setlocal enabledelayedexpansion
title PIDataPipeline - Patch & Update Manager

echo ================================================================
echo   AVEVA PI to Oracle ERP Cloud Data Pipeline
echo   Software Update & Patch Manager
echo ================================================================
echo.

set PYTHON_BIN=python
if exist "%~dp0python\python.exe" (
    set "PYTHON_BIN=%~dp0python\python.exe"
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Python was not found in your system PATH or local package.
        pause
        exit /b 1
    )
)

cd /d "%~dp0"

:: If user dragged and dropped a .zip patch directly onto update.bat or passed as argument
if not "%~1"=="" (
    echo [INFO] Applying patch file: %~1
    "%PYTHON_BIN%" -m app.updater --file "%~1"
) else (
    "%PYTHON_BIN%" -m app.updater
)

echo.
echo ================================================================
echo If an update was applied and the pipeline was running in background,
echo restart it now:
echo   stop.bat  (or scripts\stop_background.bat)
echo   start.bat (or start_silent.vbs)
echo ================================================================
echo.
pause
