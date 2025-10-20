@echo off
echo ========================================
echo STOP SIMPLIFIED PIPELINE
echo ========================================
echo.

echo Stopping MongoDB container...
docker stop mongodb_simple 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] MongoDB stopped
) else (
    echo MongoDB was not running
)

echo Removing MongoDB container...
docker rm mongodb_simple 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] MongoDB container removed
) else (
    echo MongoDB container was not found
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
