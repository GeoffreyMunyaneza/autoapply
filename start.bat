@echo off
:: AutoApply — Launch Windows desktop app (uses autoapply conda env)
cd /d "%~dp0"
echo Starting AutoApply Desktop...
echo Look for the tray icon (bottom-right) — left-click to open.
echo Logs: output\autoapply.log
echo.
start "" "C:\Users\geoff\anaconda3\envs\autoapply\python.exe" app.py --show
