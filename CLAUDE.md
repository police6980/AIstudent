# CLAUDE.md — Claude Code 작업 지침

본 저장소에서 작업하는 Claude(또는 파생 에이전트)를 위한 **상위 지침**.
최상위 설계 결정(사용자와의 대화에서 확정한 사항)과 이 파일이 충돌하면 **최신 결정이 우선**한다.

---

## 🎯 시스템 개요 (현재 설계)

**대상**: 교육대학교 학생(예비 교사).
**메커니즘**: Learning by Teaching — 교대생이 **단원 내용을 AI에게 설명**하며 본인 이해를 재조직.
**AI 역할**: **오개념을 가진 대학 동료 학습자**. 정답을 주지 않고 계속 질문.
**배포**: 단원별 고유 URL (`?unit=<unit_code>`) + 학생별 ID/비밀번호(5자 난수).
**산출물**: 세션 종료 시 PDF 리포트 (Phase B). 이메일 발송 없음.

---

## 🧭 절대 원칙 — Vygotsky 비계 6원칙 (역할 교체 반영)

모든 AI 응답은 아래 6원칙을 **최상위 제약**으로 지킨다.

1. **답을 먼저 주지 않는다** — 핵심 개념/용어/결론을 AI가 먼저 말하지 않는다.
2. **상대(교대생)의 주도성** — 설명의 흐름과 깊이는 상대가 결정.
3. **기여 감소(Fading)** — AI의 질문은 쉬운 것부터 점차 미묘한 것으로.
4. **사고 구조 매개** — 내용이 아닌 "왜/어떻게"를 묻는다.
5. **메타인지 촉진** — 상대가 자기 설명을 되돌아보게 하는 질문.
6. **정서적 안전** — 막힘을 같이 풀어갈 퍼즐로.

Layer 1 원칙 텍스트는 `src/prompts/layer1_vygotsky.py`에 박혀 있다.
**사용자 명시 승인 없이 수정 금지.**

---

## 🤖 AI 페르소나 구도 (중요)

- AI는 **초등학생 흉내 금지**. 교대생과 **같은 대학생 동료**로 행동.
- YAML의 `persona_initial_misconceptions`에 지정된 오개념을 실제로 품고 시작.
- 상대 설명이 설득력 있으면 **점진적으로** 오개념을 수정. 너무 빨리 수용 금지.
- 한 번에 1~3문장, 질문 하나씩.
- 지나치게 공손한 존댓말 지양, 자연스러운 또래 대학생 구어.

---

## 📁 프로젝트 구조 (현재)

```
src/
├── config/       환경변수(settings) + YAML 로더(unit_config)
├── models/       Pydantic 스키마, SQLAlchemy 테이블, Enum
├── prompts/
│   ├── layer1_vygotsky.py     6원칙 (불변)
│   └── layer2_preservice.py   교대생 페르소나 상호작용 스타일
├── services/
│   ├── scaffolding_engine.py  4-Layer 조립
│   ├── claude_service.py      Anthropic SDK 래퍼
│   └── session_manager.py     로그인·재접속·완료 잠금 orchestrator
├── tools/
│   └── generate_codes.py      학생 계정 생성 CLI
├── db/           SQLite 계층
└── ui/           Gradio (URL 파싱 → 로그인 → 채팅 → 종료)
configs/          단원 YAML (실파일은 .gitignore; example_*.yaml만 커밋)
```

---

## 🗺️ 페이즈

- **Phase A (완료)** — 인프라: 단원 URL, ID/비밀번호, 대화, 재접속, 완료 잠금
- **Phase B** — 분석 + PDF 리포트
  - 룰 기반: 턴 통계, 어휘 빈도, 루브릭 키워드 매칭, 망설임·메타인지 표현
  - LLM (Opus): 오개념 동태, 설명 품질 궤적, PCK 전략, 하이라이트, 강점/약점, 종합
  - 출력: Summary PDF(2p) + Detail PDF(10~20p). matplotlib 차트, Noto Sans KR 폰트 번들.
- **Phase C** — 음성(Whisper + ElevenLabs)
- **Phase D** — 에러 처리, 테스트, 배포, 데이터 보존 자동화

**한 페이즈가 검증되기 전에 다음으로 넘어가지 않는다.**

---

## 🔧 개발 철학

- **교육적 가치 > 기술적 복잡도** — Vygotsky 원칙 준수가 최우선.
- **단순함 > 완벽함** — MVP 먼저.
- **검증 가능성** — 각 페이즈 독립 검증.

## 🧪 커밋 전 체크리스트

- [ ] `black src/ tests/` 포매팅
- [ ] `ruff check src/ tests/` 통과
- [ ] 타입 힌트 누락 없음
- [ ] 공개 함수 docstring 있음
- [ ] API 키·학생 비밀번호가 코드/커밋에 없음
- [ ] 관련 단위 테스트 통과

## 🛑 사용자에게 반드시 확인할 사항

- 새 외부 API/라이브러리 도입
- Layer 1 Vygotsky 원칙 텍스트 수정 또는 새 힌트 유형 추가
- 학생 식별·비밀번호 정책 변경
- 수집·저장 데이터 범위 확대
- 페르소나 구도(오개념 가진 동료) 변경

## 🌐 언어 규칙

- 학생·교수자 대면 UI: **한국어**
- 시스템 프롬프트(Claude 입력): **한국어**
- 코드·내부 주석: 영어/한국어 혼용 OK
- 내부 에러 로그: 영어, 사용자 표시: 한국어

## 🔒 프라이버시

- `.env` 에만 API 키. 코드·커밋 하드코딩 금지.
- `configs/*.yaml` 은 `student_accounts`(평문 비밀번호) 포함 가능 → **`.gitignore` 처리됨.**
  `example_*.yaml` 만 커밋.
- `.accounts.txt` 배포용 파일도 gitignore.
- 학생 음성 원본은 Phase C에서 STT 직후 삭제.
- 세션 데이터 기본 30일 보존.

## 📦 커밋 규칙

- 의미 단위로 분리 (feat / fix / refactor / test / chore / docs)
- 메시지는 짧은 영어 — 예: `feat(auth): add student login with unit url + password`
- 한 커밋에 여러 기능 섞지 말 것
