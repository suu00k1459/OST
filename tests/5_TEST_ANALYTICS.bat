@echo off
echo ========================================
echo TEST: ANALYTICS
echo Team: SU YOUNG, ROBERT
echo ========================================
echo.

cd /d "%~dp0..\scripts"

echo Checking TimescaleDB...
docker ps -q -f name=timescaledb >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] TimescaleDB container not running!
    echo Please start TimescaleDB first: docker run -d --name timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=postgres timescale/timescaledb:latest-pg15
    pause
    exit /b 1
)

echo TimescaleDB is running...
echo.

python 4_analytics.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Analytics completed!
    echo.
    pause
    exit /b 0
) else (
    echo.
    echo [ERROR] Analytics failed!
    echo.
    pause
    exit /b 1
)
