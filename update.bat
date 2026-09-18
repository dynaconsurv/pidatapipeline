@echo off
setlocal enabledelayedexpansion
title PIDataPipeline - Patch & Update Manager

echo ================================================================
echo   AVEVA PI to Oracle ERP Cloud Data Pipeline
echo   Software Update ^& Patch Manager
echo ================================================================
echo.

:: Check if python is available in PATH
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your system PATH.
    echo Please ensure Python 3.10+ is installed and added to PATH.
    pause
    exit /b 1
)

:: Run the updater module interactively
python -m app.updater

echo.
echo ================================================================
echo If an update was applied and the service was running in the background,
echo restart it now by running:
echo   scripts\stop_background.bat
echo   scripts\start_background.vbs
echo ================================================================
echo.
pause
