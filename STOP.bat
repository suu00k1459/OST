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
REM Use Compose v2 syntax
call docker compose down -v --remove-orphans
echo Done
echo.

echo Step 2: Stopping any leftover Python processes (orchestrator, local tools)...
REM WARNING: This kills all python.exe on this Windows user/session.
REM If you have other Python apps running, comment this out.
taskkill /F /IM python.exe /T >nul 2>&1
echo Done
echo.

echo Step 3: Cleaning up unused Docker resources (stopped containers)...
REM This does NOT remove images or volumes, only stopped containers.
call docker container prune -f >nul 2>&1
echo Done
echo.

echo ===================================================
echo SHUTDOWN COMPLETE
echo ===================================================
echo.
echo All services stopped:
echo   FLEAD Docker stack:     Stopped (docker compose down)
echo   Python helpers:         Stopped (taskkill python.exe)
echo.
echo To start again, run: START.bat
echo.
pause
