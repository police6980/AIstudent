# 📘 파일럿 테스트 핸드북

**예비교사 과학 설명 훈련 시스템** 텍스트 모드 파일럿용 가이드.

---

## ⏱ 소요 시간 한눈에

| 단계 | 시간 | 누가 |
|---|---|---|
| 1. 서버 세팅 (처음 한 번만) | 15분 | 교수자 |
| 2. 단원 준비 + 학생 계정 생성 | 3분 | 교수자 |
| 3. 학생 활동 1회 | 20~30분 | 학생 |
| 4. 세션 종료 → PDF 자동 생성 | 1~2분 | 자동 |
| 5. PDF 회수·검토 | 학생 수 × 5분 | 교수자 |

---

## 🚀 1단계 — 서버 세팅 (첫 1회)

### 1-1. 저장소 받기
```bash
git clone <저장소 URL>
cd AIstudent
git checkout claude/ai-science-learning-mvp-Dg1lO
```

### 1-2. Python 가상환경 + 의존성
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 1-3. 한글 폰트 (OS별)
- **Ubuntu/Debian**: `sudo apt install fonts-nanum`
- **macOS**: 이미 있음 (Apple SD Gothic Neo)
- **Windows**: 이미 있음 (Malgun Gothic)

### 1-4. 환경 변수
```bash
cp .env.example .env
```
`.env` 파일을 열어 두 개 채우기:
```
ANTHROPIC_API_KEY=sk-ant-api03-....     # Anthropic 콘솔에서 발급
INSTRUCTOR_PASSWORD=원하는비밀번호      # 관리자 페이지 출입용
```

---

## 📝 2단계 — 단원 준비

### 2-1. 대화형 셋업 스크립트 (추천)
```bash
python scripts/pilot_setup.py
```
물어보는 것:
- 단원 코드 (예: `photo-01`)
- 단원명 (예: `광합성`)
- 대상 학년 (예: `초등 6학년`)
- AI 페르소나 이름 (예: `지후`)
- 담당 교수 이름
- 학생 계정 수 (보통 30)

→ `configs/photo-01.yaml` 자동 생성 + `configs/photo-01.accounts.txt` 에 **학생 30명 ID/비밀번호** 쏟아짐.

### 2-2. 단원 내용 직접 편집 (선택)
`configs/photo-01.yaml` 을 열고 수정:
- `learning_goals` : 이번 단원 학습 목표
- `rubric_items` : 루브릭 (자동 달성 체크에 쓰임)
- `common_misconceptions` : 이 단원에서 알려진 오개념 리스트
- `persona_initial_misconceptions` : AI 지후가 **실제로 품고** 시작할 오개념 (1~2개 추천)

> 💡 `persona_initial_misconceptions`에 명시한 오개념은 AI가 세션 초반에 자연스럽게 드러냅니다. 너무 많이 넣으면 AI가 혼란스러워져 대화가 이상해지니 1~2개 권장.

### 2-3. 관리자 페이지에서도 수정 가능
서버를 띄운 뒤 `<URL>/?admin=true` → 관리자 비밀번호 → 탭별 편집 UI.

---

## 🌐 3단계 — 앱 실행

```bash
source .venv/bin/activate
python -m src.main --share
```

터미널에 출력되는 줄:
```
* Running on local URL:  http://127.0.0.1:7860
* Running on public URL: https://xxxxxxxxx.gradio.live   ← 이게 학생용 링크
```

> ⚠️ `--share` 공개 링크는 **72시간 유효**. 파일럿 끝나면 `Ctrl+C` 로 중단.

### 네트워크 옵션
- `--share` 없이: 본인 노트북에서만 접속
- `--host 0.0.0.0`: 같은 Wi-Fi 학생도 접속 (공유기 IP + 포트 번호 알려줌)
- `--share`: 외부 인터넷 어디서든 접속 가능한 링크 생성

---

## 👥 4단계 — 학생에게 배포

`configs/photo-01.accounts.txt` 파일을 열어 학생별로 한 줄씩 나눠서 보냅니다.

### 배포 메시지 템플릿
```
📚 광합성 단원 AI 대화 활동

안녕하세요 [학생 이름]님.
아래 링크로 접속해서 본인 ID/비밀번호로 로그인해주세요.

🔗 https://xxxxxxxxx.gradio.live/?unit=photo-01
   ID: s01
   비밀번호: k3m9x

⏱ 소요 시간: 20~30분
📋 진행: 초기 개념도 → 지후와 대화 → 사후 개념도 → 성찰 5문항
📄 마치면 PDF 2개 다운로드 → 저에게 제출

참고:
- 중간에 끊어져도 같은 링크로 재접속하면 이어서 진행
- '대화 종료하고 리포트 받기' 를 누르면 그 단원은 다시 못 들어감
- 실명 대신 나중에 구분만 되면 됩니다
```

---

## 📊 5단계 — 세션 모니터링 (선택)

파일럿 중 교수자 화면에서 세션을 모니터링:

1. `<URL>/?admin=true` 접속 → 비밀번호
2. "📊 세션 조회" 탭
3. 실시간으로 학생 진행 단계 (pre_map → dialogue → post_map → reflection → completed) 확인

### 문제 상황 대응
- **학생이 실수로 '대화 종료' 눌렀다** → 관리자 페이지 "세션 잠금 해제" 에 session_id 입력
- **AI가 이상한 응답을 주기 시작했다** → 같은 탭의 PDF 다운로드로 원인 확인
- **진단 YAML 을 바꿨고 기존 세션에도 재적용하고 싶다** → "분석 재실행" 버튼

---

## 🔍 6단계 — 파일럿 후 검토 체크리스트

각 학생 PDF 2개(`summary.pdf` + `detail.pdf`) 받으면 **아래를 훑어봅니다**:

### A. 시스템 품질 (1회 전체 훑기)
- [ ] 모든 학생이 완료(COMPLETED) 상태까지 도달했는가?
- [ ] PDF가 깨짐 없이 열리는가 (한글·차트 포함)?
- [ ] 오개념 추적이 실제 대화와 일치하는가?
- [ ] Novak 점수가 사전·사후 비교에 타당한가?

### B. AI 대화 품질 (Vygotsky 6원칙)
각 학생의 전사(Detail PDF 마지막 섹션)를 샘플링해서:
- [ ] 지후가 핵심 개념·정답을 **먼저** 발설한 적 있는가? (있으면 문제)
- [ ] 지후가 **매 턴 질문을 유지**했는가?
- [ ] 지후가 학생 오개념에 **즉시 반박하지 않고** 동반 탐구했는가?
- [ ] 지후가 **초등학생 말투**로 퇴행한 경우가 있는가?
- [ ] 대화가 **교대생 눈높이**로 유지되었는가?

### C. 교육 성과 (연구 관점)
- [ ] Novak 점수 평균 상승폭은?
- [ ] 루브릭 달성률 분포는?
- [ ] 오개념 해소율 (resolved / total) 분포는?
- [ ] 성찰 응답 5문항 평균 글자 수 / 메타인지 깊이 점수 분포는?
- [ ] 예상 밖의 오개념 (AI가 새로 감지한 것) 이 있는가?

### D. 학생 경험
학생에게 따로 물어보거나 성찰 응답에서 추출:
- [ ] UI가 혼란스러운 지점은?
- [ ] AI 지후의 반응이 어색하거나 기계적이었던 적은?
- [ ] 개념도 입력(개념/명제/교차연결/예시) 형식이 직관적이었나?
- [ ] 전체 소요 시간이 적당했나?

---

## 🛠 자주 만나는 문제 & 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| "ANTHROPIC_API_KEY 설정 안 됨" 경고 | `.env` 미설정 | `.env` 에 키 채우고 재실행 |
| "Public URL" 안 나옴 | `--share` 빼먹음 | `python -m src.main --share` 재실행 |
| 한글이 PDF에서 두부(☐) | 한글 폰트 미설치 | `apt install fonts-nanum` 재실행 |
| "Claude overloaded" 계속 뜸 | Anthropic 서버 과부하 | 재시도 로직이 자동 복구, 그래도 계속되면 잠시 기다림 |
| 학생이 로그인 불가 | ID/PW 오타 또는 잠금 | 관리자 페이지에서 계정 확인 + 잠금 해제 |
| PDF 생성이 2분 넘게 | LLM 분석 6종 + 개념도 시각화 | 정상 범위 (길면 5분까지). 분석 실패 시 에러 로그 탭에서 확인 |

---

## 📈 파일럿 이후 결정

파일럿 결과를 보고 다음 단계 결정:
- **AI 대화 품질 OK** → 본 수업 투입
- **프롬프트 조정 필요** → `src/prompts/layer1_vygotsky.py`, `src/prompts/layer2_preservice.py` 편집 (Layer 1은 사용자 승인 필요)
- **진단 기준 조정** → 관리자 페이지 "🔬 진단 편집" 탭
- **음성 지원 필요** → Phase C 착수 (Whisper + ElevenLabs, 약 2~3일)

---

## 📧 문의·피드백
이 시스템에 대한 개선 요청은 저장소 이슈 또는 담당자에게 직접 연락 주세요.
