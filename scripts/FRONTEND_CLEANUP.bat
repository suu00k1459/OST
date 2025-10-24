@echo off
REM Complete frontend cleanup and reinstall
REM This fixes the ajv/codegen error

echo.
echo ===================================================
echo FRONTEND - COMPLETE CLEANUP AND REINSTALL
echo ===================================================
echo.

cd frontend

echo Step 1: Removing node_modules (this takes ~30 seconds)...
rmdir /s /q node_modules >nul 2>&1
echo Done
echo.

echo Step 2: Removing package-lock.json...
del package-lock.json >nul 2>&1
echo Done
echo.

echo Step 3: Cleaning npm cache...
call npm cache clean --force
echo Done
echo.

echo Step 4: Installing ajv first (critical dependency)...
call npm install ajv --force --no-audit --no-fund
echo Done
echo.

echo Step 5: Full npm install with all options...
call npm install --legacy-peer-deps --force --no-audit --no-fund
if errorlevel 1 (
    echo WARNING: First install had issues
    echo Retrying...
    call npm install --legacy-peer-deps --force --save-exact
)
echo Done
echo.

echo Step 6: Verifying React installation...
if not exist "node_modules\react" (
    echo ERROR: React installation failed!
    cd ..
    pause
    exit /b 1
)
echo OK: React installed
echo.

cd ..

echo ===================================================
echo FRONTEND CLEANUP COMPLETE!
echo ===================================================
echo.
echo Frontend is ready to start.
echo You can now run: npm start (in frontend folder)
echo Or run: ./START_PROFESSIONAL.bat
echo.
pause
