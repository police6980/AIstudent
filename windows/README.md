# 🖱 윈도우 퀵스타트 — 더블클릭으로 실행

명령어 칠 필요 없이 **`.bat` 파일 3개를 순서대로 더블클릭**하기만 하면 됩니다.

---

## 🎯 파일 3개 — 이 순서로만 누르세요

| 순서 | 파일 | 언제 | 소요 |
|---|---|---|---|
| 1 | `1_setup.bat` | **처음 한 번만** | 10분 |
| 2 | `2_create_unit.bat` | 새 단원 만들 때마다 | 3분 |
| 3 | `3_run_app.bat` | 앱 띄울 때마다 | 1분 |

---

## 🚀 처음 시작하기

### ⓪ 준비 (한 번만)

**A. Python 설치 확인**
- ⊞ Win → `cmd` → 엔터 → 창이 뜨면 `python --version` 입력 → 엔터
- `Python 3.x.x` 가 나오면 OK. 아니면 ↓
- https://www.python.org/downloads/ 에서 설치
- ⚠️ 설치할 때 **"Add Python to PATH"** 체크박스 꼭 체크!

**B. 코드 받기 (둘 중 하나)**

**(쉬운 방법) ZIP 다운로드**
1. https://github.com/police6980/AIstudent 접속
2. 상단 `claude/ai-science-learning-mvp-Dg1lO` 브랜치로 전환
3. 초록 `Code` 버튼 → `Download ZIP`
4. 다운받은 ZIP 압축해제 (예: `문서\AIstudent`)
5. 안에 들어가면 `windows` 폴더가 보임

**(나중에 업데이트 편한 방법) Git 클론**
1. Git 설치: https://git-scm.com/download/win (기본값으로 설치)
2. 명령 프롬프트에서:
   ```
   cd %USERPROFILE%\Documents
   git clone https://github.com/police6980/AIstudent.git
   cd AIstudent
   git checkout claude/ai-science-learning-mvp-Dg1lO
   ```

---

### ① `1_setup.bat` 더블클릭

`AIstudent\windows\` 폴더 안에 있는 **`1_setup.bat`** 을 더블클릭합니다.

자동으로:
- Python 확인
- 가상환경 생성
- 필요한 라이브러리 설치 (2~5분)
- `.env` 파일 생성 후 **메모장이 열림**

메모장이 열리면 아래 2줄을 **본인 값으로 채우기**:
```
ANTHROPIC_API_KEY=sk-ant-api03-새로발급받은키
INSTRUCTOR_PASSWORD=원하는비밀번호아무거나
```

> 💡 **API 키 발급**: https://console.anthropic.com → Settings → API Keys → Create Key
> ⚠️ **키는 절대 다른 사람에게 공유하지 마세요.**

저장(Ctrl+S) → 메모장 닫기 → 명령창에서 아무 키나 눌러서 종료.

---

### ② `2_create_unit.bat` 더블클릭

단원을 만드는 창이 뜹니다. 질문에 답하세요 (그냥 엔터 치면 괄호 안 기본값 사용):
```
단원 코드 [photo-01]:            ← 엔터 (그대로 쓰려면)
단원명 [광합성]:                 ← 엔터
대상 학년 [초등 6학년]:          ← 엔터
AI 페르소나 이름 [지후]:         ← 엔터
담당 교수 이름 [교수]:           ← 본인 이름 입력
학생 계정 수 [30]:               ← 엔터
```

끝나면:
- `configs\photo-01.yaml` ← 단원 설정
- `configs\photo-01.accounts.txt` ← **학생 30명 ID/비밀번호** (배포용)

아무 키나 눌러서 창 닫기.

---

### ③ `3_run_app.bat` 더블클릭

앱이 시작됩니다. **1분 정도 기다리면** 창에 이런 줄이 나와요:

```
* Running on local URL:  http://127.0.0.1:7860
* Running on public URL: https://abc123xyz.gradio.live
```

**`https://abc123xyz.gradio.live`** ← 이 주소를 복사해서 학생에게 배포하면 됩니다.

학생에게 보낼 **최종 링크**:
```
https://abc123xyz.gradio.live/?unit=photo-01
```
(뒤에 `?unit=단원코드` 를 붙여야 바로 그 단원으로 들어갑니다)

**관리자 페이지** (교수자 본인 확인용):
```
https://abc123xyz.gradio.live/?admin=true
```
→ `.env` 에 넣은 `INSTRUCTOR_PASSWORD` 로 로그인

**중단하려면**: 그 창에서 **Ctrl + C** 누르거나 창 그냥 X 로 닫기.

---

## 📋 학생에게 보낼 내용 만들기

`configs\photo-01.accounts.txt` 를 메모장으로 열면 이렇게 나와요:
```
단원 코드: photo-01
단원명: 광합성
학생 계정 (30명)
========================================

학생ID   비밀번호
----------------------------------------
s01     k3m9x
s02     p7q2h
s03     m4n8v
...
```

**학생 1명에게 보낼 메시지 예시**:
```
📚 광합성 단원 AI 대화 활동

🔗 링크: https://abc123xyz.gradio.live/?unit=photo-01
🔑 ID: s05
🔑 비밀번호: q7t3n

약 20~30분 소요. 끝나면 PDF 2개 다운받아 제출하세요.
```

자세한 학생 안내문 템플릿은 `docs\STUDENT_GUIDE.md` 참고.

---

## 🚨 문제 생기면

| 증상 | 해결 |
|---|---|
| `python` 을 인식할 수 없다 | Python 설치 시 "Add Python to PATH" 체크 안 한 것. Python 재설치 |
| 빨간 에러 메시지가 줄줄 뜬다 | 창을 닫지 말고 **스크린샷** 찍어서 저에게 보내주세요 |
| `1_setup.bat` 이 멈춰있다 | 2~5분은 정상. 5분 지나도 안 움직이면 창 닫고 다시 시도 |
| `Public URL` 이 안 나온다 | 인터넷 연결 확인. 또는 `3_run_app.bat` 다시 시도 |
| 학생이 링크 접속해도 로그인 안 됨 | `configs\.accounts.txt` 의 ID/PW 오타 확인 |

---

## 🔄 업데이트 받는 법

### ZIP 으로 받았다면
위 "B. 코드 받기" 과정을 **다시 반복** (새 ZIP 받고, 기존 폴더 `configs\`와 `data\` 는 새 폴더로 복사).

### Git 으로 받았다면
명령 프롬프트에서:
```
cd %USERPROFILE%\Documents\AIstudent
git pull
```

---

## 📞 문의
- 에러 메시지는 **창 전체를 스크린샷** 해서 보내주세요
- 가장 중요한 건 **빨간 글자** 부분이에요
