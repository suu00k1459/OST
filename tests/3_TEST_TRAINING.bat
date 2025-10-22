@echo off
echo ========================================
echo TEST: LOCAL TRAINING
echo Team: IMED, AMIR
echo ========================================
echo.

cd /d "%~dp0..\scripts"

python 2_local_training.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Local training completed!
    echo.
    pause
    exit /b 0
) else (
    echo.
    echo [ERROR] Local training failed!
    echo.
    pause
    exit /b 1
)
