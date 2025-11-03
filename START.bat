@echo off
setlocal enabledelayedexpansion
title FEDERATED LEARNING PLATFORM - STARTUP

echo.
echo ===================================================
echo FEDERATED LEARNING PLATFORM - STARTUP
echo ===================================================
echo.

REM ===================================================
REM STEP 1: VERIFY PREREQUISITES
REM ===================================================

echo Step 1: Checking Python...
call python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    pause
    exit /b 1
)
echo OK
echo.

echo Step 2: Checking Docker...
call docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not found in PATH or Docker Desktop not running.
    pause
    exit /b 1
)
echo OK
echo.

REM ===================================================
REM STEP 2: CLEANUP PHASE
REM ===================================================
echo.
echo ===================================================
echo CLEANUP PHASE
echo ===================================================
echo.

echo Cleaning up old Docker containers...
call docker-compose -f docker-compose-kafka.yml down 2>nul
call docker container rm -f zookeeper kafka timescaledb grafana kafka-ui 2>nul
echo Done
echo.

REM ===================================================
REM STEP 3: PYTHON DEPENDENCIES
REM ===================================================
echo ===================================================
echo PYTHON SETUP PHASE
echo ===================================================
echo.

if exist "install_dependencies.py" (
    echo Installing Python dependencies using installer...
    call python install_dependencies.py
    if errorlevel 1 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
) else (
    echo Fallback: Installing directly from requirements.txt...
    call pip install --upgrade pip
    call pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Pip installation failed.
        pause
        exit /b 1
    )
)
echo Done
echo.

REM ===================================================
REM STEP 4: DATA PREPROCESSING (OPTIONAL)
REM ===================================================
echo ===================================================
echo DATA PREPROCESSING PHASE
echo ===================================================
echo.

if exist "notebooks\Data PreProcessing.ipynb" (
    echo Initializing data preprocessing pipeline...
    python -c "import sys; sys.path.insert(0, 'Implementation'); from preprocess import *; print('[OK] Preprocessing module loaded successfully')" >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Preprocessing module not available yet. Will handle in notebooks.
    ) else (
        echo [OK] Preprocessing module available for use
    )
) else (
    echo [WARNING] Data preprocessing notebook not found. Skipping preprocessing initialization.
)
echo Done
echo.

REM ===================================================
REM STEP 5: DOCKER SERVICES (OPTIONAL)
REM ===================================================
echo ===================================================
echo DOCKER SERVICES PHASE (OPTIONAL)
echo ===================================================
echo.

echo Starting Docker containers...
echo This may take 30-60 seconds for all services to be healthy.
echo.
start "Docker Services" cmd /k "docker-compose -f docker-compose-production.yml up"
timeout /t 45 >nul
echo Done
echo.

REM ===================================================
REM STEP 6: DEVICE VIEWER WEBSITE
REM ===================================================
echo ===================================================
echo DEVICE VIEWER WEBSITE STARTUP
echo ===================================================
echo.

if not exist "website\app.py" (
    echo [ERROR] Website not found at website\app.py
    pause
    exit /b 1
)
echo Starting Device Viewer Website on port 8080...
start "Device Viewer Website" cmd /k "python website/app.py"
timeout /t 5 >nul
echo Done
echo.

REM ===================================================
REM STEP 7: OPEN BROWSER
REM ===================================================
echo ===================================================
echo OPENING BROWSER
echo ===================================================
echo.

timeout /t 3 >nul
start http://localhost:8080
echo.

REM ===================================================
REM FINAL STATUS
REM ===================================================
echo ===================================================
echo PLATFORM STARTUP COMPLETE
echo ===================================================
echo.
echo SERVICES RUNNING:
echo   Device Viewer Website:  http://localhost:8080
echo   Docker Services:        (Optional - Kafka, TimescaleDB, Grafana)
echo.
echo Check browser at http://localhost:8080
echo.
pause
