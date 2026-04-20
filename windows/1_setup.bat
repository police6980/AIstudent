@echo off
chcp 65001 > nul
cd /d "%~dp0.."
setlocal

echo ============================================================
echo   [ 1 / 3 ]  예비교사 과학 설명 훈련  -  첫 세팅
echo ============================================================
echo.

REM --- Python check -------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [X] Python 이 설치되어 있지 않습니다.
    echo.
    echo     다운로드: https://www.python.org/downloads/
    echo.
    echo     * 설치할 때 "Add Python to PATH" 체크박스 반드시 체크
    echo     * 설치 끝나면 이 창 닫고 setup.bat 다시 더블클릭
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% 확인

REM --- venv ---------------------------------------------------
if not exist .venv (
    echo.
    echo [..] 가상환경 생성 중...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] 가상환경 생성 실패
        pause
        exit /b 1
    )
    echo [OK] 가상환경 생성 완료
) else (
    echo [OK] 가상환경 이미 있음
)

REM --- pip install --------------------------------------------
echo.
echo [..] 라이브러리 설치 중...  (2 ~ 5 분 걸립니다. 기다려주세요)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo [X] pip 업그레이드 실패 - 인터넷 연결 확인
    pause
    exit /b 1
)
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [X] 라이브러리 설치 실패 - 오류 메시지 위를 확인
    pause
    exit /b 1
)
echo [OK] 라이브러리 설치 완료

REM --- .env ---------------------------------------------------
echo.
if not exist .env (
    copy /Y .env.example .env >nul
    echo [!] .env 파일을 만들었습니다.
    echo.
    echo     이제 메모장이 열립니다. 아래 두 줄을 채우세요:
    echo.
    echo       ANTHROPIC_API_KEY=sk-ant-api03-...  (여기에 키 붙여넣기)
    echo       INSTRUCTOR_PASSWORD=원하는비밀번호
    echo.
    echo     * 키는 https://console.anthropic.com 에서 새로 발급
    echo     * 저장하고 메모장 닫으면 됩니다
    echo.
    pause
    notepad .env
) else (
    echo [OK] .env 파일 이미 있음
)

echo.
echo ============================================================
echo   [OK] 세팅 완료!
echo ============================================================
echo.
echo 다음 단계:
echo.
echo   [ 2 / 3 ]  2_create_unit.bat  더블클릭  (단원 만들기)
echo   [ 3 / 3 ]  3_run_app.bat      더블클릭  (앱 실행)
echo.
pause
endlocal
