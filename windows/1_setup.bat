@echo off
cd /d "%~dp0.."
setlocal

echo ============================================================
echo   [ 1 / 3 ]  Preservice Teacher Training  -  First Setup
echo ============================================================
echo.

REM --- Python check -------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed.
    echo.
    echo     Download: https://www.python.org/downloads/
    echo.
    echo     IMPORTANT: Check "Add Python to PATH" during install
    echo     Then close this window and double-click 1_setup.bat again
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% detected

REM --- venv ---------------------------------------------------
if not exist .venv (
    echo.
    echo [..] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] venv creation failed
        pause
        exit /b 1
    )
    echo [OK] venv created
) else (
    echo [OK] venv already exists
)

REM --- pip install --------------------------------------------
echo.
echo [..] Installing libraries... (2-5 minutes, please wait)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [X] pip upgrade failed - check internet connection
    pause
    exit /b 1
)
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [X] Library install failed - see error above
    pause
    exit /b 1
)
echo [OK] Libraries installed

REM --- .env ---------------------------------------------------
echo.
if not exist .env (
    copy /Y .env.example .env >nul
    echo [!] Created .env file.
    echo.
    echo     Notepad will now open. Fill in two lines:
    echo.
    echo       ANTHROPIC_API_KEY=sk-ant-api03-...  (your API key)
    echo       INSTRUCTOR_PASSWORD=any-password-you-want
    echo.
    echo     * Get API key at: https://console.anthropic.com
    echo     * Save and close Notepad when done
    echo.
    pause
    notepad .env
) else (
    echo [OK] .env already exists
)

echo.
echo ============================================================
echo   [OK] Setup complete!
echo ============================================================
echo.
echo Next steps:
echo.
echo   [ 2 / 3 ]  Double-click  2_create_unit.bat   (make a unit)
echo   [ 3 / 3 ]  Double-click  3_run_app.bat       (run the app)
echo.
pause
endlocal
