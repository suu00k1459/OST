@echo off
echo ========================================
echo TEST: ANALYTICS
echo Team: SU YOUNG, ROBERT
echo ========================================
echo.

cd /d "%~dp0..\scripts"

echo Checking MongoDB...
docker ps -q -f name=mongodb_simple >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] MongoDB container not running!
    echo Please start MongoDB first: docker run -d --name mongodb_simple -p 27017:27017 mongo:latest
    pause
    exit /b 1
)

echo MongoDB is running...
echo.

python 4_analytics.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Analytics completed!
    echo.
    pause
    exit /b 0
) else (
    echo.
    echo [ERROR] Analytics failed!
    echo.
    pause
    exit /b 1
)
