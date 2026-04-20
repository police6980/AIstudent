@echo off
chcp 65001 > nul
cd /d "%~dp0.."
setlocal

echo ============================================================
echo   [ 3 / 3 ]  앱 실행
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

echo [..] 앱 시작 중... 30초 정도 걸립니다.
echo.
echo 잠시 후 아래와 같은 줄이 나오면 그 주소를 학생에게 배포하세요:
echo.
echo      Running on public URL: https://xxxxxxxx.gradio.live
echo.
echo 학생에게 보낼 최종 링크 형식:
echo      https://xxxxxxxx.gradio.live/?unit=photo-01
echo                                            ^^^^^^^^^^^ 본인 단원 코드
echo.
echo 관리자 페이지:
echo      https://xxxxxxxx.gradio.live/?admin=true
echo.
echo 중단하려면 Ctrl + C
echo ============================================================
echo.

python -m src.main --share

echo.
echo 앱이 종료되었습니다.
pause
endlocal
