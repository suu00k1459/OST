@echo off
echo ========================================
echo TEST: FEDERATED AGGREGATION
echo Team: IMED, AMIR
echo ========================================
echo.

cd /d "%~dp0..\scripts"

python 3_aggregation.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Federated aggregation completed!
    echo.
    pause
    exit /b 0
) else (
    echo.
    echo [ERROR] Federated aggregation failed!
    echo.
    pause
    exit /b 1
)
