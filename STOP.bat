@echo off
REM ============================================================================
REM FLEAD Platform Shutdown Script (Windows)
REM Stops all Docker services and cleans up containers
REM Usage: STOP.bat
REM ============================================================================
setlocal
title FEDERATED LEARNING PLATFORM - SHUTDOWN (WINDOWS)

rem Ensure we run from repo root (folder containing this file)
cd /d "%~dp0"

echo.
echo ===================================================
echo FEDERATED LEARNING PLATFORM - SHUTDOWN (WINDOWS)
echo ===================================================
echo.

echo Stopping all services...
echo.

REM Force kill all running containers
echo Killing running containers...
for /f "tokens=*" %%i in ('docker ps -q 2^>nul') do docker kill %%i >nul 2>&1
echo Done.

REM Force remove all containers
echo Removing all containers...
for /f "tokens=*" %%i in ('docker ps -aq 2^>nul') do docker rm -f %%i >nul 2>&1
echo Done.

REM Docker compose cleanup
echo Running docker compose cleanup...
docker compose down -v --remove-orphans >nul 2>&1
echo Done.

REM Prune volumes
echo Pruning unused volumes...
docker volume prune -f >nul 2>&1
echo Done.

REM Stop leftover Python processes
echo Stopping leftover Python processes (may kill other Python apps)...
taskkill /IM python.exe /F >nul 2>&1
echo Done.
echo.

echo ===================================================
echo SHUTDOWN COMPLETE (WINDOWS)
echo ===================================================
echo To start again: START.bat
echo.
pause
endlocal
