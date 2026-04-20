@echo off
cd /d "%~dp0.."
setlocal

echo ============================================================
echo   [ 3 / 3 ]  Running the app
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

echo [..] Starting app... takes about 30 seconds.
echo.
echo When you see a line like:
echo.
echo      Running on public URL: https://xxxxxxxx.gradio.live
echo.
echo That URL is your student link. Share it with the student URL format:
echo.
echo      https://xxxxxxxx.gradio.live/?unit=YOUR_UNIT_CODE
echo.
echo Instructor page:
echo      https://xxxxxxxx.gradio.live/?admin=true
echo.
echo To stop: press Ctrl + C in this window.
echo ============================================================
echo.

python -m src.main --share

echo.
echo App stopped.
pause
endlocal
