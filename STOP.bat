: <<'BATCH'
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
goto :EOF
BATCH

# -----------------------
# POSIX / bash section
# -----------------------
# Run this on Linux / WSL / macOS with:
#   bash STOP.bat
# or via ./stop wrapper (see separate file)

set -e

# Go to this script's directory
cd "$(dirname "$0")"

echo
echo "==================================================="
echo "FEDERATED LEARNING PLATFORM - SHUTDOWN (POSIX)"
echo "==================================================="
echo

echo "Stopping all services..."
echo

echo "Step 1: Stopping Docker containers..."
# docker compose down (with volumes + orphans)
docker compose down -v --remove-orphans || true
echo "Done"
echo

echo "Step 2: Stopping any leftover Python processes (orchestrator, local tools)..."
echo "WARNING: This may kill other Python processes on this user/session."
# Try pkill if available, otherwise skip gracefully
if command -v pkill >/dev/null 2>&1; then
  pkill -f python || true
else
  echo "  pkill not available, skipping Python process cleanup."
fi
echo "Done"
echo

echo "Step 3: Cleaning up unused Docker resources (stopped containers)..."
# This does NOT remove images or volumes, only stopped containers.
docker container prune -f >/dev/null 2>&1 || true
echo "Done"
echo

echo "==================================================="
echo "SHUTDOWN COMPLETE (POSIX)"
echo "==================================================="
echo
echo "All services stopped:"
echo "  FLEAD Docker stack:     Stopped (docker compose down)"
echo "  Python helpers:         Stopped (pkill -f python, if available)"
echo
echo "To start again on POSIX:  ./start"
echo "To start again on Windows: START.bat"
echo