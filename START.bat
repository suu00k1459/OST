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

echo Step 2: Checking npm...
call npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found in PATH.
    pause
    exit /b 1
)
echo OK
echo.

echo Step 3: Checking Docker...
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
REM STEP 4: NODE DEPENDENCIES
REM ===================================================
echo ===================================================
echo NODE SETUP PHASE
echo ===================================================
echo.

if not exist "frontend" (
    echo [ERROR] frontend folder not found.
    pause
    exit /b 1
)

cd frontend

if exist "node_modules" (
    echo Removing old node_modules folder...
    rmdir /s /q node_modules >nul 2>&1
    call timeout /t 2 >nul
)

echo Installing Node packages...
call npm cache clean --force >nul
call npm install --legacy-peer-deps --no-audit --no-fund
if errorlevel 1 (
    echo [WARNING] npm install encountered issues - retrying with force...
    call npm install --legacy-peer-deps --force --no-audit --no-fund
)

if not exist "node_modules\react" (
    echo [ERROR] React not installed successfully.
    cd ..
    pause
    exit /b 1
)
echo React installation verified successfully.
cd ..
echo Done
echo.

REM ===================================================
REM STEP 5: DOCKER SERVICES
REM ===================================================
echo ===================================================
echo DOCKER SERVICES PHASE
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
REM STEP 6: BACKEND SERVER
REM ===================================================
echo ===================================================
echo BACKEND SETUP PHASE
echo ===================================================
echo.

if not exist "server\app.py" (
    echo [ERROR] Backend not found at server\app.py
    pause
    exit /b 1
)
echo Starting Flask Backend on port 5000...
start "Backend Server" cmd /k "cd server && python app.py"
timeout /t 8 >nul
echo Done
echo.

REM ===================================================
REM STEP 7: FRONTEND SERVER
REM ===================================================
echo ===================================================
echo FRONTEND SETUP PHASE
echo ===================================================
echo.

echo Starting React Frontend on port 3000...
start "Frontend Server" cmd /k "cd frontend && npm start"
timeout /t 30 >nul
echo Done
echo.

REM ===================================================
REM STEP 8: KAFKA PRODUCER (OPTIONAL)
REM ===================================================
echo ===================================================
echo KAFKA PRODUCER PHASE
echo ===================================================
echo.

if exist "scripts\kafka_producer.py" if exist "notebooks\edge_iiot_processed" (
    echo Starting Kafka Producer...
    start "Kafka Producer" cmd /k "python scripts/kafka_producer.py --source notebooks/edge_iiot_processed --mode all-devices --rate 10 --repeat"
    timeout /t 5 >nul
)else (
    echo Kafka Producer or data folder not found. Skipping Kafka Producer startup.
)
echo Done
echo.

REM ===================================================
REM STEP 9: OPEN BROWSER
REM ===================================================
echo ===================================================
echo OPENING BROWSER
echo ===================================================
echo.

echo Waiting 20 seconds for React to compile...
timeout /t 20 >nul
start http://localhost:5000
echo.

REM ===================================================
REM FINAL STATUS
REM ===================================================
echo ===================================================
echo PLATFORM STARTUP COMPLETE
echo ===================================================
echo.
echo SERVICES RUNNING:
echo   Frontend:  http://localhost:3000 (Main Dashboard)
echo   Grafana:   http://localhost:3001 (Analytics - admin/admin)
echo   Backend:   http://localhost:5000 (API)
echo   Kafka:     localhost:9092 (Message Broker)
echo   Database:  localhost:5432 (TimescaleDB)
echo.
echo WINDOWS OPENED IN BACKGROUND:
echo   1. Docker Services (Zookeeper, Kafka, TimescaleDB, Grafana)
echo   2. Flask Backend (Port 5000)
echo   3. React Frontend (Port 3000)
echo   4. Kafka Producer (optional - if data exists)
echo.
echo Wait around 60 seconds for full initialization.
echo Check browser at http://localhost:3000
echo.
pause
