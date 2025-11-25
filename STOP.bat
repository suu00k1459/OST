#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo
echo "==================================================="
echo "FEDERATED LEARNING PLATFORM - SHUTDOWN (POSIX)"
echo "==================================================="
echo

echo "Stopping all services..."
docker compose down -v --remove-orphans || true
echo "Done."
echo

echo "Stopping leftover Python processes (may kill other Python apps)..."
if command -v pkill >/dev/null 2>&1; then
  pkill -f python || true
else
  echo "  pkill not available, skipping Python cleanup."
fi
echo "Done."
echo

echo "Cleaning up stopped Docker containers..."
docker container prune -f >/dev/null 2>&1 || true
echo "Done."
echo

echo "==================================================="
echo "SHUTDOWN COMPLETE (POSIX)"
echo "==================================================="
echo "To start again: ./start"
echo
