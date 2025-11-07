@echo off
setlocal enabledelayedexpansion
title FEDERATED LEARNING PLATFORM - COMPLETE PIPELINE STARTUP

echo.
echo ====================================================================
echo FEDERATED LEARNING PLATFORM - COMPLETE PIPELINE STARTUP
echo ====================================================================
echo This will start the entire FLEAD pipeline:
echo   1. Kafka Producer (streaming IoT data)
echo   2. Flink Local Training (real-time anomaly detection)
echo   3. Federated Aggregation (global model)
echo   4. Spark Batch Analytics (trends and predictions)
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
echo ====================================================================
echo CLEANUP PHASE
echo ====================================================================
echo.

echo Cleaning up old Docker containers...
call docker-compose down 2>nul
call docker container rm -f zookeeper kafka timescaledb grafana kafka-ui flink-jobmanager flink-taskmanager spark-master spark-worker-1 2>nul
echo Done
echo.

REM ===================================================
REM STEP 3: PYTHON DEPENDENCIES
REM ===================================================
echo ====================================================================
echo PYTHON SETUP PHASE
echo ====================================================================
echo.

echo Installing Python dependencies...
call python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip/setuptools.
    pause
    exit /b 1
)

echo Installing from requirements.txt...
call pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt
    pause
    exit /b 1
)

if exist "scripts\install_dependencies.py" (
    echo Running install_dependencies.py...
    call python scripts\install_dependencies.py
    if errorlevel 1 (
        echo [WARNING] install_dependencies.py encountered issues
    )
) else (
    echo [WARNING] install_dependencies.py not found
)

echo Done
echo.

REM ===================================================
REM STEP 4: DOCKER SERVICES STARTUP
REM ===================================================
echo ====================================================================
echo DOCKER SERVICES STARTUP
echo ====================================================================
echo.

echo Starting Docker containers...
echo This includes: Kafka, TimescaleDB, Flink, Spark, Grafana
echo.
echo Docker logs will appear below:
echo ====================================================================
call docker-compose up -d
echo ====================================================================
echo.

echo Waiting for Docker services to become healthy (max 120 seconds)...
setlocal enabledelayedexpansion
set "wait_count=0"
set "max_wait=120"

:wait_for_services
set /a wait_count=!wait_count!+1

REM Check if critical services are healthy
docker-compose ps | find "kafka" | find "healthy" >nul 2>&1
set kafka_ok=!errorlevel!
docker-compose ps | find "timescaledb" | find "healthy" >nul 2>&1
set db_ok=!errorlevel!

if !kafka_ok! equ 0 if !db_ok! equ 0 (
    echo [OK] Docker services are healthy
    goto services_ready
)

if !wait_count! lss !max_wait! (
    if !wait_count! equ 1 (
        echo Attempt !wait_count!/!max_wait!...
        echo Showing Docker service status:
        docker-compose ps
        echo.
    ) else (
        if !wait_count! equ 30 (
            echo Still waiting... Attempt !wait_count!/!max_wait!
            echo Recent Docker logs:
            docker-compose logs --tail 5 2^>nul
        )
        if !wait_count! equ 60 (
            echo Still waiting... Attempt !wait_count!/!max_wait!
        )
        if !wait_count! equ 90 (
            echo Final attempts... Attempt !wait_count!/!max_wait!
        )
    )
    timeout /t 1 >nul
    goto wait_for_services
)

echo [WARNING] Docker services may not be fully healthy, continuing anyway...

:services_ready
echo Done
echo.

echo Current Docker container status:
docker-compose ps
echo.

echo Showing Docker logs summary:
docker-compose logs --tail 10 2^>nul
echo.

REM ===================================================
REM STEP 5: PIPELINE ORCHESTRATOR (COMPLETE PIPELINE)
REM ===================================================
echo ====================================================================
echo STARTING COMPLETE FLEAD PIPELINE
echo ====================================================================
echo.

echo Starting Pipeline Orchestrator...
echo This will:
echo   - Setup Kafka topics
echo   - Start Kafka Producer (IoT data streaming)
echo   - Start Flink Local Training (real-time anomaly detection)
echo   - Start Federated Aggregation (global model)
echo   - Start Spark Batch Analytics (historical trends)
echo.
echo Pipeline logs will be saved to: logs/
echo.

python scripts\pipeline_orchestrator.py
if errorlevel 1 (
    echo [ERROR] Pipeline orchestrator failed
    pause
    exit /b 1
)

REM ===================================================
REM FINAL STATUS
REM ===================================================
echo.
echo ====================================================================
echo PLATFORM STARTUP COMPLETE
echo ====================================================================
echo.
echo ACCESS POINTS:
echo   Grafana Dashboard:        http://localhost:3001  (admin/admin)
echo   Kafka UI:                 http://localhost:8081
echo   Device Viewer Website:    http://localhost:8082
echo   Flink Dashboard:          http://localhost:8161
echo   Spark Master:             http://localhost:8086
echo   TimescaleDB:              localhost:5432
echo.
echo PIPELINE COMPONENTS:
echo   Kafka Producer:          STREAMING IoT Data
echo   Flink:                   Real-time Local Training (Anomaly Detection)
echo   Federated Aggregation:   Global Model via FedAvg
echo   Spark Analytics:         Batch Processing (Trends, Predictions)
echo.
echo LOG FILES:
echo   See logs/ directory for detailed component logs
echo.
echo Press Ctrl+C to stop all services
echo.
pause

