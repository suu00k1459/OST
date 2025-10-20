@echo off
echo ========================================
echo SIMPLIFIED IoT FEDERATED LEARNING PIPELINE
echo Complete Execution
echo ========================================
echo.

cd /d "%~dp0scripts"

echo [STEP 1/6] Starting MongoDB...
echo ----------------------------------------
docker ps -q -f name=mongodb_simple >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo MongoDB already running
) else (
    docker run -d --name mongodb_simple -p 27017:27017 mongo:latest
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to start MongoDB!
        pause
        exit /b 1
    )
    echo Waiting for MongoDB to initialize...
    timeout /t 5 /nobreak >nul
)
echo [SUCCESS] MongoDB ready
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
echo 3. View MongoDB data: Use MongoDB Compass at mongodb://localhost:27017
echo.
pause
