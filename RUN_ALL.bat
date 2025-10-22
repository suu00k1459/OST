@echo off
echo ========================================
echo SIMPLIFIED IoT FEDERATED LEARNING PIPELINE
echo Complete Execution
echo ========================================
echo.

cd /d "%~dp0scripts"

echo [STEP 1/6] Starting TimescaleDB...
echo ----------------------------------------
docker ps -q -f name=timescaledb >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo TimescaleDB already running
) else (
    docker run -d --name timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=postgres timescale/timescaledb:latest-pg15
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to start TimescaleDB!
        pause
        exit /b 1
    )
    echo Waiting for TimescaleDB to initialize...
    timeout /t 10 /nobreak >nul
)
echo [SUCCESS] TimescaleDB ready
echo.

echo [STEP 2/6] Data Ingestion...
echo ----------------------------------------
python 1_data_ingestion.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Data ingestion failed!
    pause
    exit /b 1
)
echo.

echo [STEP 3/6] Preprocessing...
echo ----------------------------------------
python 1_preprocessing.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Preprocessing failed!
    pause
    exit /b 1
)
echo.

echo [STEP 4/6] Local Training...
echo ----------------------------------------
python 2_local_training.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Local training failed!
    pause
    exit /b 1
)
echo.

echo [STEP 5/6] Federated Aggregation...
echo ----------------------------------------
python 3_aggregation.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Federated aggregation failed!
    pause
    exit /b 1
)
echo.

echo [STEP 6/6] Analytics...
echo ----------------------------------------
python 4_analytics.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Analytics failed!
    pause
    exit /b 1
)
echo.

echo ========================================
echo PIPELINE COMPLETE!
echo ========================================
echo.
echo Next steps:
echo 1. Run visualization: python 5_visualization.py
echo 2. Check outputs in: outputs/
echo 3. View TimescaleDB data: Use pgAdmin or psql at localhost:5432
echo.
pause
