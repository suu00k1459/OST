@echo off
echo ========================================
echo TEST: VISUALIZATION
echo Team: YUSIF, AMIR
echo ========================================
echo.

cd /d "%~dp0..\scripts"

python 5_visualization.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Visualization completed!
    echo Dashboard should be displayed.
    echo.
    pause
    exit /b 0
) else (
    echo.
    echo [ERROR] Visualization failed!
    echo.
    pause
    exit /b 1
)
