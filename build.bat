@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo  AutoApply Build Script
echo  Produces: dist\installer\AutoApply-Setup.exe
echo ============================================================
echo.

:: ── Check Python ──────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo         Activate your conda/venv environment first.
    pause & exit /b 1
)

:: ── Check PyInstaller ─────────────────────────────────────────────────────────
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 ( echo [ERROR] PyInstaller install failed. & pause & exit /b 1 )
)

:: ── Check Inno Setup ─────────────────────────────────────────────────────────
set ISCC=
for %%p in (
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) do (
    if exist %%p set ISCC=%%p
)

if "%ISCC%"=="" (
    echo [WARNING] Inno Setup not found — installer will not be built.
    echo           Download from: https://jrsoftware.org/isdl.php
    echo           The PyInstaller folder build will still be created.
)

:: ── Create assets/icon.ico if missing ─────────────────────────────────────────
if not exist assets mkdir assets
if not exist assets\icon.ico (
    echo [INFO] No icon found at assets\icon.ico — building without custom icon.
    echo        To add an icon: place a 256x256 .ico file at assets\icon.ico
)

:: ── Clean previous build ──────────────────────────────────────────────────────
echo [1/3] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist\AutoApply rmdir /s /q dist\AutoApply

:: ── PyInstaller ───────────────────────────────────────────────────────────────
echo [2/3] Running PyInstaller...
pyinstaller AutoApply.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause & exit /b 1
)

if not exist "dist\AutoApply\AutoApply.exe" (
    echo [ERROR] dist\AutoApply\AutoApply.exe not found after build.
    pause & exit /b 1
)

echo        PyInstaller build complete: dist\AutoApply\

:: ── Inno Setup ───────────────────────────────────────────────────────────────
if "%ISCC%"=="" (
    echo [3/3] Skipping installer (Inno Setup not installed).
    echo.
    echo Build complete. Distribute the folder: dist\AutoApply\
    pause & exit /b 0
)

echo [3/3] Building installer with Inno Setup...
if not exist dist\installer mkdir dist\installer
%ISCC% installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup build failed.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Installer: dist\installer\AutoApply-Setup.exe
echo ============================================================
echo.
pause
