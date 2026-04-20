@echo off
chcp 65001 > nul
cd /d "%~dp0.."
setlocal

echo ============================================================
echo   [ 2 / 3 ]  단원 만들기 + 학생 계정 30개 생성
echo ============================================================
echo.

if not exist .venv (
    echo [X] 가상환경이 없습니다. 먼저 1_setup.bat 을 실행하세요.
    pause
    exit /b 1
)

if not exist .env (
    echo [X] .env 가 없습니다. 먼저 1_setup.bat 을 실행하세요.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo 이제 몇 가지 질문에 답하세요. 그대로 쓸 값엔 그냥 Enter 만 누르면 됩니다.
echo.
python scripts\pilot_setup.py
if errorlevel 1 (
    echo.
    echo [X] 단원 생성 중 오류 발생
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   [OK] 단원 생성 완료!
echo ============================================================
echo.
echo 이제 3_run_app.bat 을 더블클릭해서 앱을 실행하세요.
echo.
echo 생성된 배포용 계정 파일:  configs\*.accounts.txt
echo (학생에게 한 줄씩 나눠서 보내면 됩니다)
echo.
pause
endlocal
