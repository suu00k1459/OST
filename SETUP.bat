@echo off
echo ========================================
echo SIMPLIFIED PIPELINE - SETUP
echo ========================================
echo.

echo [1/3] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)
echo [SUCCESS] Python found
python --version
echo.

echo [2/3] Checking Docker installation...
docker --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not installed or not running!
    echo Please install Docker Desktop from https://www.docker.com/
    pause
    exit /b 1
)
echo [SUCCESS] Docker found
docker --version
echo.

echo [3/3] Installing Python dependencies...
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)
echo [SUCCESS] Dependencies installed
echo.

echo ========================================
echo SETUP COMPLETE!
echo ========================================
echo.
echo Next steps:
echo 1. Start MongoDB: docker run -d --name mongodb_simple -p 27017:27017 mongo:latest
echo 2. Test individual components: cd tests ^& 1_TEST_DATA.bat
echo 3. Run complete pipeline: RUN_ALL.bat
echo.
pause
