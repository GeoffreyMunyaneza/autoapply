@echo off
:: AutoApply — Start background job tracker (uses autoapply conda env)
cd /d "%~dp0"
echo AutoApply starting...
echo Logs:    output\autoapply.log
echo Tracker: output\tracker.xlsx
echo Resumes: output\resumes\
echo.
echo Press Ctrl+C to stop.
echo.
"C:\Users\geoff\anaconda3\envs\autoapply\python.exe" main.py
pause
