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
call docker container rm -f zookeeper kafka timescaledb grafana kafka-ui flink-jobmanager flink-taskmanager spark-master spark-worker-1 kafka-broker-1 kafka-broker-2 kafka-broker-3 kafka-broker-4 2>nul
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
REM ===================================================
REM STEP 5: START PIPELINE ORCHESTRATOR
REM ===================================================
echo.
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

REM Run the pipeline orchestrator
python scripts\pipeline_orchestrator.py

REM If orchestrator exits, perform cleanup
echo.
echo Orchestrator stopped. Shutting down...
pause