@echo off
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
docker compose down -v --remove-orphans
echo Done.
echo.

echo Stopping leftover Python processes (may kill other Python apps)...
taskkill /IM python.exe /F >nul 2>&1
echo Done.
echo.

echo Cleaning up stopped Docker containers...
docker container prune -f >nul 2>&1
echo Done.
echo.

echo ===================================================
echo SHUTDOWN COMPLETE (WINDOWS)
echo ===================================================
echo To start again: START.bat
echo.
pause
endlocal
