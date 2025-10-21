@echo off
echo ========================================
echo STOP SIMPLIFIED PIPELINE
echo ========================================
echo.

echo Stopping TimescaleDB container...
docker stop timescaledb 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] TimescaleDB stopped
) else (
    echo TimescaleDB was not running
)

echo Removing TimescaleDB container...
docker rm timescaledb 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] TimescaleDB container removed
) else (
    echo TimescaleDB container was not found
)

echo.
echo ========================================
echo CLEANUP COMPLETE
echo ========================================
echo.
echo Optional: Clean all generated files
echo - data/raw/
echo - data/processed/
echo - models/local/
echo - models/global/
echo - outputs/
echo.
pause
