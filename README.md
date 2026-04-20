---
title: 예비교사 과학 설명 훈련
emoji: 🧠
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 4.44.0
python_version: "3.11"
app_file: app.py
pinned: false
license: mit
---

# 예비교사 과학 설명 훈련 시스템

교육대학교 학생(예비 교사)이 단원 내용을 **동료 학습자(AI)에게 설명**하면서
본인 이해를 깊게 하고, 가르치기 역량을 연습하는 **AI 대화형 학습 시스템**입니다.

AI는 **오개념을 가진 대학 동료** 역할로, 설명을 들으며 계속 질문하고 점진적으로
이해를 수정합니다. 세션이 끝나면 교수자용 분석 리포트(PDF)가 생성됩니다.

## 현재 진행

- ✅ **Phase A — 인프라**: 단원별 URL, 학생 ID/비밀번호 로그인, 대화 진행·재접속·완료 잠금
- ⏭️ **Phase B — 분석·리포트**: 오개념 동태 추적, 루브릭/설명 품질 분석, PDF (요약 + 상세)
- ⏭️ **Phase C — 음성**: Whisper STT + TTS
- ⏭️ **Phase D — 완성도**: 에러 처리, 테스트, 배포, 데이터 보존 정책 자동화

## 빠른 시작

### 1. 환경 준비

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env 파일을 열어 ANTHROPIC_API_KEY 를 채웁니다.
```

### 2. 단원 YAML 작성

`configs/example_photosynthesis.yaml` 을 참고해 단원 파일을 만듭니다:
```yaml
unit_code: "photo-01"
unit_name: "광합성"
persona_name: "지후"
persona_initial_misconceptions:
  - "식물은 흙에서 양분을 흡수해 자란다"
# ...자세한 스키마는 예시 파일 참고
```

### 3. 학생 계정 30개 생성

```bash
python -m src.tools.generate_codes configs/photo-01.yaml
```
- `configs/photo-01.yaml` 에 `student_accounts` 가 자동 추가됩니다(s01~s30).
- `configs/photo-01.accounts.txt` 가 생성됩니다 — **교수자가 학생에게 개별 배포할 ID·비밀번호 목록**.
- ⚠️ 이 파일과 YAML은 `.gitignore` 되어 있어요 (비밀번호 유출 방지).

### 4. 앱 실행

```bash
python -m src.main
```

학생에게 배포할 URL:
```
http://<host>:<port>/?unit=photo-01
```
학생은 URL 접속 → 받은 ID/비밀번호 입력 → 대화 → 종료.

### 5. 저장된 대화 확인

```bash
sqlite3 data/sessions.db
sqlite> SELECT id, unit_code, student_id, status FROM sessions;
sqlite> SELECT speaker, content FROM turns WHERE session_id='...' ORDER BY turn_index;
```

## 세션 정책

| 상황 | 동작 |
|---|---|
| ID/비밀번호 처음 사용 | 새 세션 시작 |
| 진행 중 재접속(끊김 복구) | 같은 세션 이어서 계속 |
| "대화 종료" 버튼을 누른 뒤 | 같은 ID로 재접속 차단 |
| 교수자가 재시도 허용 | DB의 해당 세션 `status` 를 `in_progress` 로 수정, 또는 새 ID 할당 |

## 프로젝트 구조

```
src/
├── config/        환경변수 + YAML 로더
├── models/        Pydantic + SQLAlchemy
├── prompts/       4-Layer 시스템 프롬프트
├── services/      scaffolding_engine, claude_service, session_manager
├── tools/         CLI: generate_codes
├── db/            SQLite 계층
└── ui/            Gradio 컴포넌트
configs/           단원 YAML (실제 파일은 gitignore)
```

자세한 개발 원칙은 [CLAUDE.md](./CLAUDE.md) 참조.

## 개발

```bash
pip install -e ".[dev]"
black src/ tests/
ruff check src/ tests/
pytest
```

## 라이선스 / 프라이버시

- `.env` 와 `configs/<real>.yaml` (실계정 포함) 은 절대 커밋하지 않습니다.
- 학생 음성 원본은 STT 직후 즉시 삭제(Phase C).
- 세션 데이터 기본 30일 보존.
