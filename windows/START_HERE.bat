@echo off
cd /d "%~dp0.."
setlocal EnableDelayedExpansion

echo ==============================================================
echo    Preservice Teacher Training  -  One-click starter
echo ==============================================================
echo.

REM ---------- Step 0: Python available? ----------
where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed on this computer.
    echo.
    echo     Opening the Python download page in your browser...
    echo     When installing, YOU MUST CHECK "Add Python to PATH".
    echo.
    start https://www.python.org/downloads/
    echo     After install, close and re-run START_HERE.bat.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% detected

REM ---------- Step 1: venv ----------
if not exist .venv (
    echo [..] First-time setup: creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] Failed to create .venv
        pause
        exit /b 1
    )
    echo [OK] .venv created
)

call .venv\Scripts\activate.bat

REM ---------- Step 2: dependencies ----------
if not exist .venv\installed.flag (
    echo [..] Installing libraries (first run, 3~5 min)...
    python -m pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [X] Library install failed.
        pause
        exit /b 1
    )
    echo libraries-installed > .venv\installed.flag
    echo [OK] Libraries installed
) else (
    echo [OK] Libraries already installed (.venv\installed.flag present)
)

REM ---------- Step 3: .env ----------
if not exist .env (
    copy /Y .env.example .env >nul
    echo.
    echo [!] First-time setup: .env file created.
    echo.
    echo     Notepad will open. Fill in AT LEAST this line:
    echo.
    echo         INSTRUCTOR_PASSWORD=your-admin-password
    echo.
    echo     You can leave ANTHROPIC_API_KEY blank here and enter it
    echo     on the admin page later.
    echo.
    echo     Save and close Notepad to continue.
    pause
    notepad .env
)

REM ---------- Step 4: launch ----------
echo.
echo ==============================================================
echo    Launching the app...  (about 30 seconds)
echo.
echo    When 'Public URL: https://xxxxxx.gradio.live' appears,
echo    - Student link: that URL + /?unit=your-unit-code
echo    - Admin link  : that URL + /?admin=true
echo.
echo    Keep this window open. Ctrl+C to stop.
echo ==============================================================
echo.

python -m src.main --share

echo.
echo App stopped.
pause
endlocal
