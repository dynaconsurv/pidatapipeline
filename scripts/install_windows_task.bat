@echo off
:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ================================================================
    echo Error: Please right-click this script and select "Run as Administrator".
    echo ================================================================
    pause
    exit /b 1
)

set SCRIPT_DIR=%~dp0
set VBS_PATH=%SCRIPT_DIR%start_background.vbs

echo ================================================================
echo Registering PIDataPipeline as a Windows Startup Task...
echo Task will automatically start on system boot without any CMD window.
echo ================================================================

schtasks /create /tn "PIDataPipeline" /tr "wscript.exe \"%VBS_PATH%\"" /sc onstart /ru "SYSTEM" /rl HIGHEST /f

if %errorLevel% equ 0 (
    echo.
    echo [SUCCESS] PIDataPipeline task created successfully!
    echo It will automatically start every time Windows boots up.
    echo.
    echo To start it right now without restarting, run:
    echo   schtasks /run /tn "PIDataPipeline"
    echo.
    echo To remove this auto-start task in the future, run:
    echo   schtasks /delete /tn "PIDataPipeline" /f
) else (
    echo.
    echo [NOTE] If running as SYSTEM failed, creating user logon task instead...
    schtasks /create /tn "PIDataPipeline" /tr "wscript.exe \"%VBS_PATH%\"" /sc onlogon /rl HIGHEST /f
)

pause
