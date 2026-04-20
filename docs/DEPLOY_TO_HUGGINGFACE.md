# 🤗 Hugging Face Spaces 배포 가이드 (가장 쉬운 방법)

**교수님 노트북에 아무것도 설치하지 않고** 웹에서 앱을 띄우는 방법입니다.
- 명령 프롬프트 사용 ❌
- Python 설치 ❌
- Git 설치 ❌
- 브라우저만 있으면 OK ✅

소요 시간: **15~20분** (처음 한 번만)

---

## ⏱ 한눈에 보기

1. Hugging Face 계정 만들기 (2분)
2. 새 Space 만들기 (3분)
3. GitHub 파일 복사해서 Space 에 올리기 (5~10분)
4. API 키 등록 (1분)
5. 완료! → 학생에게 공유할 URL 자동 생성됨

---

## 1️⃣ Hugging Face 계정 만들기

1. https://huggingface.co/join 접속
2. 이메일 / 사용자이름 / 비밀번호 입력 (일반 사이트 가입과 똑같음)
3. 이메일 인증 후 로그인

> 💡 이미 계정이 있으면 https://huggingface.co/login 로 로그인

---

## 2️⃣ 새 Space 만들기

1. 우측 상단 본인 프로필 아이콘 클릭 → **`+ New Space`**
   (또는 바로 https://huggingface.co/new-space 접속)

2. 양식 작성:
   | 항목 | 값 |
   |---|---|
   | **Owner** | (본인 아이디 그대로) |
   | **Space name** | 원하는 이름. 예: `vygotsky-preservice` (영문·숫자·하이픈만) |
   | **License** | `mit` |
   | **Select the Space SDK** | **Gradio** 선택 |
   | **Gradio SDK version** | `4.44.0` (기본값이 그거면 OK) |
   | **Space hardware** | **CPU basic · Free** |
   | **Public 또는 Private** | 먼저 **Private** 로 만들고 확인 후 Public 으로 바꾸는 걸 추천 |

3. 아래 **`Create Space`** 버튼 클릭

→ 빈 Space 페이지로 이동합니다.

---

## 3️⃣ GitHub 파일을 Space 에 올리기

### 방법 A — 웹에서 파일 복사 (가장 쉬움)

Space 페이지 상단의 탭 중 **`Files`** 클릭 → 아직 비어 있을 거예요.

**우측 상단 `+ Add file`** → **`Upload files`** 선택.

이제 교수님은 새 탭을 하나 더 열고 GitHub 에서 파일을 받습니다:

1. https://github.com/police6980/AIstudent 접속
2. 브랜치를 `claude/ai-science-learning-mvp-Dg1lO` 로 변경
3. 초록 **`Code`** 버튼 → **`Download ZIP`**
4. 받은 ZIP 파일 압축 해제
5. 해제한 폴더 **안의 모든 파일·폴더를 한꺼번에** 드래그 → HF Space 의 업로드 영역에 드롭

업로드는 시간이 좀 걸려요 (5~10분, 파일 수가 많음).

업로드 끝나면 아래 **`Commit changes to main`** 버튼 눌러 저장.

> ⚠️ 업로드 시 **`.venv` 폴더·`__pycache__` 폴더·`data/` 폴더는 제외** 하고 올리세요.
> (해당 폴더가 ZIP 에 포함되었으면 압축 해제 후 지워도 됩니다)

### 방법 B — GitHub 에서 Duplicate (교수님이 Git 아시면)

교수님 GitHub 계정에 우리 저장소를 Fork 한 뒤, HF Space 설정에서 해당 저장소를 연결.
상세 내용은 https://huggingface.co/docs/hub/spaces-github-actions 참고.

---

## 4️⃣ API 키 + 비밀번호 등록 (HF Secrets)

Space 페이지 상단의 **`Settings`** 탭 클릭.

아래로 스크롤하다 보면 **`Variables and secrets`** 섹션이 있어요.
**`New secret`** 버튼 클릭해서 아래 2개 추가:

### Secret 1
- **Name**: `ANTHROPIC_API_KEY`
- **Value**: 새로 발급한 Anthropic API 키 (`sk-ant-api03-...`)
- `Add` 클릭

### Secret 2
- **Name**: `INSTRUCTOR_PASSWORD`
- **Value**: 교수자 관리 페이지 접속할 때 쓸 비밀번호 (아무거나)
- `Add` 클릭

> 💡 Anthropic API 키 발급: https://console.anthropic.com → Settings → API Keys → Create Key

저장하면 Space 가 자동으로 **다시 빌드**됩니다 (3~5분 소요).

---

## 5️⃣ 앱 확인 + 학생 배포

Space 페이지 상단의 **`App`** 탭을 클릭하면 실행 중인 앱이 보여요.

### 앱 URL
```
https://huggingface.co/spaces/본인아이디/vygotsky-preservice
```

**학생이 접속할 URL** 은 여기에 `?unit=단원코드` 를 붙인 형식:
```
https://본인아이디-vygotsky-preservice.hf.space/?unit=photo-01
```

(Spaces 는 `.hf.space` 로 끝나는 단축 URL 도 자동 제공합니다 — 어느 쪽 링크든 동작)

### 관리자 페이지
```
https://본인아이디-vygotsky-preservice.hf.space/?admin=true
```
→ `INSTRUCTOR_PASSWORD` 로 로그인

---

## 6️⃣ 단원·학생 계정 만들기

관리자 페이지 접속 → **`📋 단원 관리`** 탭 → 새 단원 만들기 + 학생 계정 30개 자동 생성.

완료되면 `configs/단원코드.accounts.txt` 가 Space 의 파일 시스템에 만들어져요.
이걸 교수님이 Files 탭 → 해당 파일 클릭 → **`Download`** 로 받아 학생에게 나눠주면 됩니다.

---

## 🛑 중요한 주의사항

### 데이터 휘발성 (무료 플랜 한계)
- 무료 HF Spaces 는 **Sleep 상태** 가 되거나 재빌드될 때 `data/sessions.db` 같은 파일이 **사라질 수 있습니다**
- 해결 1: **세션이 끝나면 학생이 바로 PDF 다운로드** 하면 됨 (PDF 는 학생 브라우저에 저장)
- 해결 2: HF Spaces **Persistent Storage** 플랜 추가 (월 $5, 영구 저장)
- 해결 3: 수업 중에는 계속 접속 유지 → Sleep 방지

### Private vs Public
- **Private** = 본인 로그인한 브라우저에서만 접속. 학생에게는 링크 안 열림. **수업용으로는 부적합**.
- **Public** = 아무나 URL 만 있으면 접속. 학생에게 배포하려면 Public 이어야 함.
- Public 으로 바꿔도 **학생 비밀번호가 없으면 로그인 못 하므로 데이터 안전성은 유지**

### 비용
- **CPU basic: 무료** (이 프로젝트에 충분)
- Anthropic API 호출은 **교수님 API 키** 로 과금됨. 세션 1회당 약 $0.3~0.5 (Sonnet + Opus 혼용)
- 30명 × 1회 = 약 $10~15

---

## 🔁 코드 업데이트 시

제가 저장소에 새 커밋을 올렸으면, 교수님은:

1. GitHub 에서 새 ZIP 다시 다운로드
2. Space 의 Files 탭 → 변경된 파일만 다시 업로드
3. Space 가 자동 재빌드

또는 GitHub 연동을 해두면 자동 sync 가능 (설정 복잡도 있음).

---

## 🚨 문제 생기면

### "Build failed" 가 Space 에서 뜸
- Files 탭 → `requirements.txt` 가 제대로 올라갔는지 확인
- **Logs** 탭 → 붉은 에러 메시지를 스크린샷

### "AI replies will fail" 경고
- Settings → Variables and secrets → `ANTHROPIC_API_KEY` 값이 정확한지 확인

### 학생이 접속했는데 로그인 안 됨
- `configs/단원코드.accounts.txt` 의 ID/비밀번호를 다시 확인
- Space 가 Sleep 상태였다가 깨어나면서 DB 가 리셋됐을 수도 있음 → 관리자 페이지에서 학생 계정 다시 생성

---

## 📞 나한테 알려주실 것

HF Spaces 배포 시 막히면:
1. Space URL (`https://huggingface.co/spaces/...`)
2. Settings 탭 → Logs 의 빨간 에러 메시지
3. 어느 단계에서 막혔는지

이 3가지 주시면 바로 진단해드립니다.
