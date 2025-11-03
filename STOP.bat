@echo off
REM Federated Learning Platform - Complete Shutdown Script

echo.
echo ===================================================
echo FEDERATED LEARNING PLATFORM - SHUTDOWN
echo ===================================================
echo.

echo Stopping all services...
echo.

echo Step 1: Stopping Docker containers...
call docker-compose -f docker-compose-production.yml down
echo Done
echo.

echo Step 2: Stopping Python processes (Website)...
taskkill /F /IM python.exe /T >nul 2>&1
echo Done
echo.

echo Step 3: Cleaning up Docker resources...
call docker container prune -f >nul 2>&1
echo Done
echo.

echo ===================================================
echo SHUTDOWN COMPLETE
echo ===================================================
echo.
echo All services stopped:
echo   Device Viewer Website:  Stopped
echo   Docker containers:      Stopped
echo.
echo To start again, run: ./START.bat
echo.
pause
