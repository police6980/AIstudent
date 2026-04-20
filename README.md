# Vygotsky Science Tutor

초등학생부터 과학고 학생까지 사용 가능한 **AI 대화형 과학 학습 시스템** (MVP).

학생이 **이미 학습한 내용**을 AI 친구에게 **음성으로 설명**하는 과정에서 스스로 개념을
재조직·심화하도록 돕는다. AI는 답을 주는 튜터가 아니라 **Vygotsky 비계 원리**를 따라
사고를 촉발하는 동반자다.

## 현재 마일스톤: M1 (뼈대)

- ✅ 프로젝트 구조 / 설정 파일
- ✅ Pydantic 데이터 모델
- ✅ SQLite 저장 계층
- ✅ 4-Layer 시스템 프롬프트(학교급 4종)
- ✅ Claude API 래퍼
- ✅ 최소 Gradio 텍스트 UI
- ⏭️ **M2** — 음성 파이프라인 (Whisper STT, ElevenLabs TTS)
- ⏭️ **M3** — 비계 6유형 + 자기 검증
- ⏭️ **M4** — 루브릭/오개념 자동 분석, PDF 리포트, 이메일
- ⏭️ **M5** — 완성도·배포

## 빠른 시작

### 1. 환경 준비

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 ANTHROPIC_API_KEY 를 채운다.
# M1은 Claude만 있으면 동작한다.
```

### 3. 실행 (M1: 텍스트 대화)

```bash
python -m src.main
```

브라우저에서 Gradio URL을 열고,
- 세션 코드: `photo-g6-0420` (예시 YAML)
- 학생 이름(닉네임 권장) 입력 후 대화를 시작한다.

### 4. 저장된 세션 확인

```bash
sqlite3 data/sessions.db
sqlite> .tables
sqlite> SELECT speaker, content FROM turns ORDER BY turn_index;
```

## 프로젝트 구조

자세한 설계는 [CLAUDE.md](./CLAUDE.md)와 최상위 설계 문서를 참조.

```
src/
├── config/       환경 변수, YAML 로더
├── models/       Pydantic 스키마, SQLAlchemy 모델
├── services/     프롬프트 엔진, Claude 래퍼, 세션 관리자
├── prompts/      4-Layer 시스템 프롬프트
├── db/           SQLite 계층
└── ui/           Gradio 컴포넌트
configs/          교사 단원 설정 YAML
```

## 개발

```bash
pip install -e ".[dev]"
black src/ tests/
ruff check src/ tests/
pytest
```

## 라이선스 / 프라이버시

- 학생 음성 원본은 STT 직후 즉시 삭제(기본값). `.env`의 `KEEP_AUDIO_FILES=true`로만 유지.
- 세션 데이터 기본 30일 보존.
- 학생에게 **실명 대신 닉네임** 입력을 권장한다.

## 참고

본 시스템의 이론적 기반(Vygotsky ZPD, Learning by Teaching, Protégé Effect)과 전체 설계는
저장소에 동봉된 상위 설계 문서를 참조.
