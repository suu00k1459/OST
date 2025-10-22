@echo off
title Initial Setup

echo.
echo ========================================
echo  SIMPLIFIED PIPELINE - INITIAL SETUP
echo ========================================
echo.

echo [1/3] Checking Docker...
docker ps >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker Desktop is not running!
    echo Please start Docker Desktop and run this again.
    pause
    exit /b 1
)
echo [OK] Docker is running

echo.
echo [2/3] Installing Python packages...
pip install --quiet numpy pandas scikit-learn matplotlib psycopg2-binary
echo [OK] Packages installed

echo.
echo [3/3] Starting TimescaleDB...
docker ps | findstr timescaledb >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Starting TimescaleDB container...
    docker run -d -p 5432:5432 --name timescaledb -e POSTGRES_PASSWORD=postgres timescale/timescaledb:latest-pg15
    timeout /t 5 /nobreak >nul
)
echo [OK] TimescaleDB ready

echo.
echo ========================================
echo  SETUP COMPLETE
echo ========================================
echo.
echo You can now test individual components:
echo   1_TEST_DATA.bat
echo   2_TEST_LOCAL_TRAINING.bat
echo   3_TEST_AGGREGATION.bat
echo   4_TEST_ANALYTICS.bat
echo   5_TEST_VISUALIZATION.bat
echo.
pause
