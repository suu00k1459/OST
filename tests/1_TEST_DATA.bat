@echo off
echo ========================================
echo TEST: DATA INGESTION
echo Team: SU YOUNG, ROBERT
echo ========================================
echo.

cd /d "%~dp0..\scripts"

python 1_data_ingestion.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Data ingestion completed!
    echo.
    pause
    exit /b 0
) else (
    echo.
    echo [ERROR] Data ingestion failed!
    echo.
    pause
    exit /b 1
)
