@echo off
cd /d "%~dp0.."
setlocal

echo ============================================================
echo   [ 2 / 3 ]  Create a unit + 30 student accounts
echo ============================================================
echo.

if not exist .venv (
    echo [X] venv not found. Run 1_setup.bat first.
    pause
    exit /b 1
)

if not exist .env (
    echo [X] .env not found. Run 1_setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo Answer the prompts. Press Enter to accept the default shown in brackets.
echo.
python scripts\pilot_setup.py
if errorlevel 1 (
    echo.
    echo [X] Unit creation failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   [OK] Unit created!
echo ============================================================
echo.
echo Next: double-click 3_run_app.bat to launch the app.
echo.
echo Your student credentials are in:  configs\*.accounts.txt
echo (Send each student one line from that file)
echo.
pause
endlocal
