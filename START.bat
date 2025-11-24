: <<'BATCH'
@echo off
setlocal enabledelayedexpansion
title FEDERATED LEARNING PLATFORM - COMPLETE PIPELINE STARTUP

REM ====================================================================
REM NEW: ensure we run from the directory where this script lives
REM ====================================================================
cd /d "%~dp0"

REM ====================================================================
REM NEW: if cross-platform Python launcher exists, delegate to it
REM ====================================================================
if exist "start_flead_pipeline.py" (
    echo Detected cross-platform Python launcher. Delegating to it...
    echo.
    python start_flead_pipeline.py

    echo.
    echo ====================================================================
    echo Script finished. Press any key to close this window.
    echo ====================================================================
    echo.
    pause >nul
    goto :EOF
)

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
REM STEP 2: PREPARE DATA (Convert chunks to CSV if needed)
REM ===================================================

echo Step 3: Preparing data...
if not exist "data\processed\device_0.csv" (
    echo   No device CSV files found, converting from chunks...
    call python scripts\convert_chunks_to_device_csvs.py
    if errorlevel 1 (
        echo [WARNING] Data conversion failed, but continuing anyway...
    )
) else (
    echo   Device CSV files already exist, skipping conversion...
)
echo OK
echo.

REM ===================================================
REM STEP 3: CLEANUP PHASE
REM ===================================================
echo.
echo ====================================================================
echo CLEANUP PHASE
echo ====================================================================
echo.

echo Cleaning up old Docker containers...
REM Compose v2 syntax
call docker compose down 2>nul

REM Extra hard cleanup (safe even if some containers don't exist)
call docker container rm -f zookeeper kafka timescaledb grafana kafka-ui ^
    flink-jobmanager flink-taskmanager spark-master spark-worker-1 ^
    kafka-broker-1 kafka-broker-2 kafka-broker-3 kafka-broker-4 ^
    timescaledb-collector federated-aggregator device-viewer ^
    monitoring-dashboard grafana-init database-init 2>nul

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
echo This includes: Kafka (4 brokers), TimescaleDB, Flink, Spark, Grafana, UI services
echo.
echo Docker logs will appear below:
echo ====================================================================
call docker compose up -d
echo ====================================================================
echo.

echo Waiting for Docker services to become healthy (max 120 seconds)...
setlocal enabledelayedexpansion
set "wait_count=0"
set "max_wait=120"

:wait_for_services
set /a wait_count=!wait_count!+1

REM Check if critical services are healthy / started
REM Kafka brokers: at least one line with "kafka-broker-1" and "Up"
docker compose ps | find "kafka-broker-1" | find "Up" >nul 2>&1
set kafka_ok=!errorlevel!

REM TimescaleDB: must be healthy (has proper healthcheck)
docker compose ps | find "timescaledb" | find "healthy" >nul 2>&1
set db_ok=!errorlevel!

if !kafka_ok! equ 0 if !db_ok! equ 0 (
    echo [OK] Docker services are ready (Kafka brokers up, TimescaleDB healthy)
    goto services_ready
)

if !wait_count! lss !max_wait! (
    if !wait_count! equ 1 (
        echo Attempt !wait_count!/!max_wait!...
        echo Showing Docker service status:
        docker compose ps
        echo.
    ) else (
        if !wait_count! equ 30 (
            echo Still waiting... Attempt !wait_count!/!max_wait!
            echo Recent Docker logs:
            docker compose logs --tail 5
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
docker compose ps
echo.

echo Showing Docker logs summary:
docker compose logs --tail 10
echo.

REM ===================================================
REM STEP 5: SUBMIT PIPELINE JOBS (FLINK + SPARK)
REM ===================================================
echo.
echo ====================================================================
echo STARTING PIPELINE ORCHESTRATOR
echo ====================================================================
echo.
echo This will:
echo   - Submit Flink job for local training
echo   - Submit Spark job for analytics
echo   - Run optional Grafana setup
echo   (Kafka Producer, Federated Aggregator, Monitoring, Device Viewer
echo    are managed directly by Docker Compose in this version.)
echo.
echo Pipeline logs will be saved to: logs/
echo.

python scripts\pipeline_orchestrator.py

REM ===================================================
REM STEP 6: ALL SERVICES NOW RUNNING
REM ===================================================
echo ====================================================================
echo ALL DOCKER SERVICES RUNNING
echo ====================================================================
echo.

echo All pipeline components are now running inside Docker containers:
echo   - Kafka (4 brokers with multi-broker architecture)
echo   - Producer (streaming 2400 IoT devices across brokers)
echo   - Flink (real-time local training)
echo   - Federated Aggregator (global model)
echo   - Spark (batch analytics)
echo   - Monitoring Dashboard (real-time status)
echo   - Device Viewer (web interface)
echo   - TimescaleDB (time-series database)
echo   - Grafana (visualization)
echo.
echo All setup and initialization is complete!
echo.

REM ===================================================
REM FINAL STATUS
REM ===================================================
echo.
echo ====================================================================
echo PLATFORM STARTUP COMPLETE - ALL SERVICES IN DOCKER
echo ====================================================================
echo.
echo ACCESS POINTS:
echo   Live Monitoring:          http://localhost:5001
echo   Grafana Dashboard:        http://localhost:3001  (admin/admin)
echo   Kafka UI:                 http://localhost:8081
echo   Device Viewer Website:    http://localhost:8082
echo   Flink Dashboard:          http://localhost:8161
echo   Spark Master:             http://localhost:8086
echo   TimescaleDB:              localhost:5432
echo.
echo PIPELINE COMPONENTS:
echo   Kafka Producer:          STREAMING IoT Data (Docker)
echo   Flink:                   Real-time Local Training (Docker)
echo   Federated Aggregation:   Global Model (Docker)
echo   Spark Analytics:         Batch Processing (Docker)
echo.
echo LOG FILES:
echo   View logs in real-time:
echo   docker compose logs -f
echo.
echo STATUS CHECK:
echo   docker compose ps
echo.
echo STOP ALL SERVICES:
echo   docker compose down
echo.
echo RESTART SERVICES:
echo   docker compose restart
echo.
echo ====================================================================
echo.
echo LAUNCHING WEB INTERFACES
echo ====================================================================
echo.

REM Wait a moment for services to fully stabilize
timeout /t 3 /nobreak

REM Launch all dashboards in browser
echo Opening dashboards in your browser...
start http://localhost:8081
timeout /t 1 /nobreak
start http://localhost:3001
timeout /t 1 /nobreak
start http://localhost:8161
timeout /t 1 /nobreak
start http://localhost:8086
timeout /t 1 /nobreak
start http://localhost:8087
timeout /t 1 /nobreak
start http://localhost:5001
timeout /t 1 /nobreak
start http://localhost:8082

echo.
echo ====================================================================
echo All dashboards opened! 
echo Press any key to close this window.
echo ====================================================================
echo.
pause >nul
goto :EOF
BATCH

# -----------------------
# POSIX / bash section
# -----------------------
# Run this on Linux / WSL / macOS with:
#   bash start.bat
# or via ./start wrapper (see separate file)

set -e

# Go to this script's directory
cd "$(dirname "$0")"

echo
echo "===================================================================="
echo "FEDERATED LEARNING PLATFORM - COMPLETE PIPELINE STARTUP (POSIX)"
echo "===================================================================="
echo

echo "Step 1: Checking Python..."
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] Python not found in PATH."
  exit 1
fi
echo "OK"
echo

echo "Step 2: Checking Docker..."
if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] Docker not found in PATH or Docker daemon not running."
  exit 1
fi
echo "OK"
echo

echo "Step 3: Preparing data..."
if [ ! -f "data/processed/device_0.csv" ]; then
  echo "  No device CSV files found, converting from chunks..."
  if command -v python3 >/dev/null 2>&1; then
    python3 scripts/convert_chunks_to_device_csvs.py || echo "[WARNING] Data conversion failed, but continuing anyway..."
  else
    python scripts/convert_chunks_to_device_csvs.py || echo "[WARNING] Data conversion failed, but continuing anyway..."
  fi
else
  echo "  Device CSV files already exist, skipping conversion..."
fi
echo "OK"
echo

echo
echo "===================================================================="
echo "CLEANUP PHASE (POSIX)"
echo "===================================================================="
echo
docker compose down || true
docker container rm -f zookeeper kafka timescaledb grafana kafka-ui \
  flink-jobmanager flink-taskmanager spark-master spark-worker-1 \
  kafka-broker-1 kafka-broker-2 kafka-broker-3 kafka-broker-4 \
  timescaledb-collector federated-aggregator device-viewer \
  monitoring-dashboard grafana-init database-init 2>/dev/null || true

echo "Done"
echo

echo "===================================================================="
echo "DOCKER SERVICES STARTUP (POSIX)"
echo "===================================================================="
echo
docker compose up -d
echo

echo "Waiting 30 seconds for services to come up..."
sleep 30
docker compose ps
echo

echo "===================================================================="
echo "STARTING PIPELINE ORCHESTRATOR (POSIX)"
echo "===================================================================="
echo

if command -v python3 >/dev/null 2>&1; then
  python3 scripts/pipeline_orchestrator.py
else
  python scripts/pipeline_orchestrator.py
fi

echo
echo "===================================================================="
echo "PLATFORM STARTUP COMPLETE - ALL SERVICES IN DOCKER (POSIX)"
echo "===================================================================="
echo
echo "ACCESS POINTS:"
echo "  Live Monitoring:          http://localhost:5001"
echo "  Grafana Dashboard:        http://localhost:3001  (admin/admin)"
echo "  Kafka UI:                 http://localhost:8081"
echo "  Device Viewer Website:    http://localhost:8082"
echo "  Flink Dashboard:          http://localhost:8161"
echo "  Spark Master:             http://localhost:8086"
echo "  TimescaleDB:              localhost:5432"
echo
echo "LOGS:"
echo "  docker compose logs -f"
echo
