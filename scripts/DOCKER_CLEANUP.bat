@echo off
REM ===================================================
REM Emergency Docker Cleanup Script
REM Use this if containers are stuck or conflicting
REM ===================================================

echo.
echo ===================================================
echo DOCKER EMERGENCY CLEANUP
echo ===================================================
echo.

echo WARNING: This will stop and remove ALL containers!
echo Press Ctrl+C to cancel, or any other key to continue...
pause >nul

echo.
echo Stopping all containers...
call docker ps -aq >nul 2>&1
if %errorlevel% neq 0 (
    echo Docker is not running. Please start Docker Desktop first.
    pause
    exit /b
)
call docker stop $(docker ps -aq) 2>nul
echo Done
echo.

echo Removing all containers...
call docker rm -f zookeeper kafka timescaledb grafana kafka-ui 2>nul
echo Done
echo.

echo Removing old networks...
call docker network rm ost_edge-iiot-net 2>nul
call docker network rm flead_flead_network 2>nul
echo Done
echo.

echo Pruning Docker system (removing unused resources)...
call docker system prune -f
echo Done
echo.

echo ===================================================
echo CLEANUP COMPLETE
echo ===================================================
echo.
echo You can now run: START_PROFESSIONAL.bat
echo.
pause
