@echo off
title XuexitongManager Build Tool

echo.
echo =========================================
echo   XuexitongManager Build Tool
echo =========================================
echo.

REM Check Python
echo [1/4] Checking Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found
    goto :error
)
echo       Python OK

REM Check pip
echo.
echo [2/4] Installing dependencies...
where pip >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip not found
    goto :error
)

REM Install dependencies
python -m pip install -r requirements.txt -q >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Dependency installation may have issues
) else (
    echo       Dependencies installed
)

REM Clean old builds
echo.
echo [3/4] Cleaning old builds...
if exist build (
    rmdir /s /q build
    echo       build/ cleaned
)
if exist dist (
    rmdir /s /q dist
    echo       dist/ cleaned
)

REM Check spec file
if not exist xuexitong_win.spec (
    echo [ERROR] xuexitong_win.spec not found
    goto :error
)

REM Build
echo.
echo [4/4] Building application...
echo       Please wait, this may take a few minutes...
echo.
pyinstaller --clean xuexitong_win.spec
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed
    goto :error
)

REM Check result
echo.
echo =========================================
if exist "dist\XuexitongManager.exe" (
    echo   Build SUCCESS!
    echo.
    echo   Output: dist\XuexitongManager.exe
    for %%A in ("dist\XuexitongManager.exe") do echo   Size: %%~zA bytes
    echo =========================================
    echo.
    explorer dist
    goto :success
) else (
    echo   Build FAILED - output not found
    echo =========================================
    goto :error
)

:success
echo.
echo Build complete! Press any key to exit...
pause >nul
exit /b 0

:error
echo.
echo Build error! Press any key to exit...
pause >nul
exit /b 1
