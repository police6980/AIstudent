"""Interactive demo: run a realistic student -> AI dialogue and print responses.

Purpose: verify that AI '지후' actually follows the Vygotsky principles
(no answer disclosure, keeps questioning, holds misconception, etc.) by
showing the actual replies against scripted student utterances.

Run:
    source .venv/bin/activate
    PYTHONPATH=. python scripts/dialogue_demo.py
"""

from __future__ import annotations

import sys
import time

from src.config.settings import get_settings
from src.db.database import Base, get_engine
from src.models.concept_map import Concept, ConceptMap, Example, Proposition
from src.models.schemas import RubricItem, StudentAccount, UnitConfig
from src.services.instructor_service import save_unit_config
from src.services.session_manager import SessionManager

BAR = "─" * 70


def _section(title: str) -> None:
    print()
    print(BAR)
    print(f"  {title}")
    print(BAR)


def _turn(label: str, text: str, color: str = "") -> None:
    RESET = "\033[0m"
    print(f"\n{color}{label}{RESET}")
    for line in text.splitlines():
        print(f"  {line}")


def main() -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("❌ ANTHROPIC_API_KEY 가 .env 에 없어요.", file=sys.stderr)
        return 2

    # Reset DB for clean run
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    unit = UnitConfig(
        unit_code="demo-photo",
        subject="초등 과학 교과교육",
        unit_name="광합성",
        target_grade_for_teaching="초등 6학년",
        learning_goals=[
            "광합성의 조건 (빛, 물, 이산화탄소)",
            "광합성의 산물 (포도당, 산소)",
            "광합성이 일어나는 장소 (엽록체)",
        ],
        rubric_items=[
            RubricItem(item_id="r_light", description="빛", keywords=["빛"]),
            RubricItem(item_id="r_water", description="물", keywords=["물"]),
            RubricItem(item_id="r_oxygen", description="산소", keywords=["산소"]),
        ],
        common_misconceptions=[
            "식물은 흙에서 양분을 흡수해 자란다",
            "잎의 녹색 색소가 산소를 만든다",
        ],
        persona_name="지후",
        persona_role="같은 단원을 공부하는 교대 동료 학생",
        persona_initial_misconceptions=[
            "식물은 흙에서 양분을 흡수해 자란다",
        ],
        instructor_name="테스트 교수",
        student_accounts=[StudentAccount(id="s01", password="demo1")],
    )
    save_unit_config(unit)

    mgr = SessionManager()
    login = mgr.login("demo-photo", "s01", "demo1")
    sid = login.session_id

    # Pre-map with intentional misconception
    cmap = ConceptMap(
        concepts=[
            Concept(id="c1", label="광합성"),
            Concept(id="c2", label="빛"),
            Concept(id="c3", label="흙"),
            Concept(id="c4", label="식물"),
            Concept(id="c5", label="에너지"),
        ],
        propositions=[
            Proposition(from_id="c4", to_id="c1", linking_phrase="이 수행함"),
            Proposition(from_id="c1", to_id="c2", linking_phrase="의 조건은"),
            Proposition(from_id="c4", to_id="c3", linking_phrase="에서 양분을 얻음"),  # misconception
            Proposition(from_id="c1", to_id="c5", linking_phrase="을 만듦"),
        ],
        examples=[Example(concept_id="c4", text="해바라기")],
    )

    _section("학생 초기 개념도 제출 (흙에서 양분 얻음 오개념 포함)")
    print("  개념: 광합성, 빛, 흙, 식물, 에너지")
    print("  명제: 식물→광합성, 광합성의 조건은 빛, 식물→흙에서 양분, 광합성→에너지")

    t0 = time.time()
    pre_result = mgr.submit_pre_concept_map(sid, cmap)
    elapsed = time.time() - t0
    _section(f"진단 결과 (Opus 분석 · {elapsed:.1f}초)")
    diag = pre_result.diagnosis
    if diag:
        print(f"  • 수준 판정: {diag.level}")
        print(f"  • 판정 근거: {diag.level_justification[:150]}")
        print(f"  • 강점: {', '.join(diag.strong_points[:3])}")
        print(f"  • ZPD 목표: {', '.join(diag.zpd_targets[:3])}")
        if diag.detected_misconceptions:
            print("  • 감지된 오개념:")
            for m in diag.detected_misconceptions[:2]:
                misc = m.get("misconception") if isinstance(m, dict) else str(m)
                print(f"      - {misc}")
        print(f"  • AI에게 권장된 첫 질문: \"{diag.recommended_first_question}\"")

    _section("첫 AI 발화 (페르소나 지후가 방금 개념도를 본 뒤 말 건넴)")
    ai_first = [t for t in pre_result.turns if t.speaker.value == "ai"][0]
    _turn("🤖 지후:", ai_first.content, color="\033[36m")

    # Scripted student turns — each chosen to probe specific Vygotsky principles
    scenarios = [
        (
            "학생 turn 1 — 모호한 설명",
            "광합성은 식물이 햇빛을 이용해 에너지를 만드는 과정이야.",
            "[기대] AI가 '만든다'라는 표현을 지적하거나, 결정론적 답을 피하고 되물음",
        ),
        (
            "학생 turn 2 — 오개념 건드리기",
            "그리고 식물은 뿌리로 흙에서 양분을 받아 자라는 거 알지?",
            "[기대] AI가 이 오개념을 바로 반박하지 말고, 자기도 그렇게 생각하던 척 따라가거나 되물음",
        ),
        (
            "학생 turn 3 — 학생이 재정리 시도",
            "아 잠깐, 사실 식물은 스스로 광합성으로 양분을 만들고, 흙에서는 물하고 무기질만 얻어.",
            "[기대] AI가 바로 '정답!' 하지 않고, 좀 더 자세히 물어보거나 남은 오개념을 찌름",
        ),
        (
            "학생 turn 4 — 연결 시도",
            "그러니까 광합성의 산물이 식물의 양분인 셈이야. 포도당 같은 거.",
            "[기대] AI가 점진적으로 수긍하면서도 '그럼 산소는?' 같은 추가 질문",
        ),
    ]

    for label, student_text, expectation in scenarios:
        _section(label)
        _turn("👤 학생:", student_text)
        print(f"\n  {expectation}")
        t0 = time.time()
        ai_turn = mgr.submit_student_turn(sid, student_text)
        elapsed = time.time() - t0
        _turn(f"🤖 지후: ({elapsed:.1f}초)", ai_turn.content, color="\033[36m")

    _section("검증 체크리스트 (교수님이 직접 판단)")
    print("""  대화를 다 읽어보고 다음 항목을 체크하세요:

  □ 지후가 '정답', '맞아요' 류의 판정 언어를 쓰지 않았는가?
  □ 지후가 핵심 개념/용어(엽록체, 포도당, 이산화탄소 등)를 먼저 말하지 않았는가?
  □ 지후가 매 턴 최소 1개 이상 질문/되묻기를 던졌는가?
  □ 지후가 '흙에서 양분' 오개념을 자기도 갖고 시작한 티가 났는가?
  □ 학생이 수정한 뒤에도 너무 빨리 완전 수긍하지 않았는가?
  □ 지후가 초등학생 말투('헤헤~', '몰라용~')로 퇴행하지 않았는가?
  □ 응답 길이가 1~3문장 수준에서 관리되는가?
  □ 자연스러운 또래 대학생 구어체인가?
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
