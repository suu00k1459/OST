@echo off
REM FLEAD Platform - Complete Shutdown Script
REM Stops all services cleanly

echo.
echo ===================================================
echo FLEAD PLATFORM - COMPLETE SHUTDOWN
echo ===================================================
echo.

echo Stopping all services...
echo.

echo Step 1: Stopping Docker containers...
docker-compose -f docker-compose-production.yml down
echo Done
echo.

echo Step 2: Stopping any remaining Python processes...
taskkill /F /IM python.exe /T >nul 2>&1
echo Done
echo.

echo Step 3: Stopping any remaining Node processes...
taskkill /F /IM node.exe /T >nul 2>&1
echo Done
echo.

echo Step 4: Cleaning up Docker resources...
docker container prune -f >nul 2>&1
echo Done
echo.

echo ===================================================
echo SHUTDOWN COMPLETE
echo ===================================================
echo.
echo All FLEAD services have been stopped.
echo.
echo Docker containers: Stopped
echo Backend (Python): Stopped
echo Frontend (Node): Stopped
echo Kafka Producer: Stopped
echo.
echo To start again, run: ./START_PROFESSIONAL.bat
echo.
pause
