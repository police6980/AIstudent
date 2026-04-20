# 🖱 Windows Quickstart — 더블클릭으로 실행

명령어 칠 필요 없이 **`.bat` 파일 2개만** 순서대로 더블클릭하면 됩니다.

---

## 🎯 새 흐름 (매우 간단해짐)

| 순서 | 파일 | 언제 | 소요 |
|---|---|---|---|
| 1 | `1_setup.bat` | **처음 한 번만** | 10분 |
| 2 | `3_run_app.bat` | 앱 띄울 때마다 | 30초 |

나머지 **모든 작업은 웹 관리자 페이지에서** 진행합니다.

> ⚠️ `2_create_unit.bat` 은 옛 방식(명령줄). 이제 안 쓰셔도 됩니다. 관리자 페이지에서 단원 만드세요.

---

## 🚀 처음 시작하기

### ⓪ 준비 (한 번만)

**A. Python 설치 확인**
- ⊞ Win → `cmd` → 엔터 → `python --version` 입력 → 엔터
- `Python 3.x.x` 가 나오면 OK. 아니면 ↓
- https://www.python.org/downloads/ 에서 설치
- ⚠️ 설치할 때 **"Add Python to PATH"** 체크박스 꼭 체크!

**B. 코드 다운로드**
1. https://github.com/police6980/AIstudent/archive/refs/heads/main.zip 클릭 → ZIP 받기
2. 압축 풀기 (예: `문서\AIstudent`)
3. 안에 들어가면 `windows` 폴더 보임

---

### ① `1_setup.bat` 더블클릭 (처음 한 번)

자동으로:
- Python 확인
- 가상환경 생성
- 필요한 라이브러리 설치 (2~5분)
- `.env` 파일 생성 후 **메모장이 열림**

메모장이 열리면 **이 줄만** 채우세요 (나머지는 그대로 두거나 비워둬도 됨):
```
INSTRUCTOR_PASSWORD=원하는비밀번호아무거나
```

> 💡 `ANTHROPIC_API_KEY` 는 **비워둬도 됩니다** — 앱 실행 후 웹 관리자 페이지에서 직접 입력 가능

저장 (Ctrl+S) → 메모장 닫기 → 아무 키 눌러 종료.

---

### ② `3_run_app.bat` 더블클릭 (매번)

검은 창에서 30초 정도 기다리면 이런 줄이 나와요:

```
* Running on local URL:  http://127.0.0.1:7860
* Running on public URL: https://abc123xyz.gradio.live   ← 이게 핵심!
```

**`https://abc123xyz.gradio.live`** 이 주소가 학생·교수자 모두 접속할 공개 URL.

---

## 🧑‍🏫 교수자: 관리자 페이지에서 모든 설정

### 1. 관리자 페이지 접속
브라우저에서:
```
https://abc123xyz.gradio.live/?admin=true
```

### 2. 로그인
`.env` 에 넣은 `INSTRUCTOR_PASSWORD` 입력.

### 3. API 키 입력 (맨 위 접이식 섹션)
**"🔑 API 키 설정 (이 세션에만 유효)"** 클릭해서 펼치기
- 새 API 키 입력 (`sk-ant-api03-...`)
- **적용** 버튼 클릭
- 💡 API 키가 없으면 https://console.anthropic.com → Settings → API Keys → Create Key

### 4. 단원 만들기 (**📋 단원 관리** 탭)
- **unit_code**: URL에 쓰일 이름 (예: `solution-01`)
- **단원명**: `용액과 용질`
- **학습 목표**: 여러 줄로 입력
- **루브릭**: 항목 + 키워드 추가
- **AI 초기 오개념**: AI 가 실제로 품고 시작할 오개념
- **학생 계정 수**: `30`
- **저장** 클릭 → 학생 30명 ID/비밀번호가 자동 생성됨!

### 5. 학생 계정 받기
생성된 **`configs/solution-01.accounts.txt`** 파일을 `C:\...\AIstudent\configs\` 폴더에서 메모장으로 열면:
```
s01   k3m9x
s02   p7q2h
s03   m4n8v
...
```
이 목록을 학생 한 명당 한 줄씩 나눠 보내기.

### 6. 학생용 링크
```
https://abc123xyz.gradio.live/?unit=solution-01
```
이 URL + 개별 ID/비밀번호를 학생에게 배포.

---

## 👥 학생: 링크 접속 → 활동 → PDF 다운로드

1. 교수님이 준 링크 접속
2. ID/비밀번호 로그인
3. **초기 개념도** 작성
4. **AI 와 대화** (설명하기)
5. **사후 개념도** 작성
6. **성찰 5문항** 답변 (각 100자 이상)
7. 완료 후 **PDF 2개 다운로드**:
   - `summary.pdf` — 핵심 요약
   - `detail.pdf` — 전체 기록
8. PDF 를 교수님에게 이메일/LMS 로 제출

---

## 📦 교수자 서버에도 PDF 자동 저장

학생이 완료하는 순간, 교수님 컴퓨터의 이 폴더에도 **자동으로 같은 PDF 저장**:
```
AIstudent\data\reports\<단원>_<학생ID>_<세션>\
  ├── summary.pdf
  └── detail.pdf
```

학생이 깜빡하고 제출 안 해도 교수님 컴퓨터에 남아있어서 안전.

---

## 🔌 컴퓨터 계속 켜두기 (수업 중)

학생이 접속하는 동안 **서버 = 교수님 노트북** 이므로 절대 꺼지면 안 됩니다.

- Windows 설정 → **전원 및 절전**:
  - "화면 끄기" → **사용 안 함**
  - "절전" → **사용 안 함**
- Wi-Fi 연결 유지
- 검은 명령 창 **닫지 않기** (최소화만 OK)

---

## 🛑 앱 중단

검은 창에서 **Ctrl + C** 또는 창 닫기.

---

## 🚨 자주 만나는 문제

| 증상 | 해결 |
|---|---|
| Python 인식 안 됨 | Python 재설치할 때 "Add Python to PATH" 체크 |
| Public URL 안 나옴 | 인터넷 연결 확인, `3_run_app.bat` 다시 시도 |
| 학생 로그인 안 됨 | 관리자 페이지에서 해당 단원 계정 다시 확인 |
| API 키 인증 실패 | 관리자 페이지 최상단 "🔑 API 키 설정" 에서 새 키 입력 |
| 한글이 PDF 에서 깨짐 | 윈도우엔 Malgun Gothic 기본 탑재. 재시작 한 번 시도 |
| 분석이 1분 넘게 걸림 | 정상 범위 (최대 2분). 학생에겐 "분석 중…" 안내 |

---

## 🔄 업데이트 받기

1. 검은 창 종료 (Ctrl+C)
2. https://github.com/police6980/AIstudent/archive/refs/heads/main.zip 재다운로드 → 압축 해제
3. 기존 폴더의 `src\`, `app.py`, `requirements.txt` 등을 새 ZIP 내용으로 덮어쓰기
4. ⚠️ `.env`, `data\` 폴더는 **덮어쓰지 마세요** (본인 데이터 있음)
5. `3_run_app.bat` 다시 실행

---

## 📞 문의

빨간 에러 메시지 스크린샷 찍어서 저에게 보내주세요.
