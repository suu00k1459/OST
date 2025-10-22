@echo off
echo ========================================
echo TEST: PREPROCESSING
echo Team: SU YOUNG, ROBERT
echo ========================================
echo.

cd /d "%~dp0..\scripts"

python 1_preprocessing.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Preprocessing completed!
    echo.
    pause
    exit /b 0
) else (
    echo.
    echo [ERROR] Preprocessing failed!
    echo.
    pause
    exit /b 1
)
