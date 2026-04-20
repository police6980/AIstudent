"""End-to-end smoke test — real Claude calls, short session.

Exercises:
    1. Unit YAML + student accounts
    2. login + pre-map submission (triggers Claude diagnosis)
    3. 2 dialogue turns (real Claude replies)
    4. end_dialogue + post-map
    5. reflection submission (triggers full analysis + PDF generation)
    6. verifies summary.pdf + detail.pdf exist and are non-trivial

Run:
    source .venv/bin/activate
    python scripts/smoke_test.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from src.config.settings import get_settings
from src.db.database import Base, get_engine
from src.db.repository import SessionRepository
from src.models.concept_map import Concept, ConceptMap, CrossLink, Example, Proposition
from src.models.schemas import RubricItem, StudentAccount, UnitConfig
from src.services.instructor_service import save_unit_config
from src.services.session_manager import SessionManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("smoke")


def _reset_db():
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())


def _seed_unit():
    configs_dir = Path("configs")
    unit = UnitConfig(
        unit_code="smoke-photo",
        subject="초등 과학 교과교육",
        unit_name="광합성",
        target_grade_for_teaching="초등 6학년",
        learning_goals=[
            "광합성의 조건 (빛, 물, 이산화탄소)",
            "광합성의 산물 (포도당, 산소)",
            "광합성이 일어나는 장소 (엽록체)",
        ],
        rubric_items=[
            RubricItem(
                item_id="r_light", description="빛이 조건임을 설명", keywords=["빛", "햇빛"]
            ),
            RubricItem(
                item_id="r_water", description="물이 조건임을 설명", keywords=["물"]
            ),
            RubricItem(
                item_id="r_oxygen", description="산소가 산물임을 설명", keywords=["산소"]
            ),
        ],
        common_misconceptions=[
            "식물은 흙에서 양분을 흡수해 자란다",
            "광합성은 낮에만, 호흡은 밤에만 일어난다",
        ],
        persona_name="지후",
        persona_role="같은 단원을 공부하는 교대 동료 학생",
        persona_initial_misconceptions=[
            "식물은 흙에서 양분을 흡수해 자란다",
        ],
        hint_max_count=3,
        session_duration_minutes=5,
        instructor_name="테스트 교수",
        student_accounts=[StudentAccount(id="s01", password="smoke1")],
    )
    save_unit_config(unit, configs_dir=configs_dir)
    return unit


def main() -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY 가 설정되지 않았어요.")
        return 2

    _reset_db()
    unit = _seed_unit()
    logger.info("Seeded unit: %s", unit.unit_code)

    mgr = SessionManager()

    # 1) Login
    login = mgr.login("smoke-photo", "s01", "smoke1")
    sid = login.session_id
    logger.info("Logged in. Session %s, step=%s", sid, login.current_step.value)

    # 2) Pre-map → Claude diagnosis
    pre_map = ConceptMap(
        concepts=[
            Concept(id="c1", label="광합성"),
            Concept(id="c2", label="빛"),
            Concept(id="c3", label="물"),
            Concept(id="c4", label="흙"),
            Concept(id="c5", label="식물"),
        ],
        propositions=[
            Proposition(from_id="c5", to_id="c1", linking_phrase="이 하는 일은"),
            Proposition(from_id="c1", to_id="c2", linking_phrase="의 조건은"),
            Proposition(from_id="c1", to_id="c3", linking_phrase="의 조건은"),
            # Intentional misconception: 식물이 흙에서 양분을 얻는다는 설정
            Proposition(from_id="c5", to_id="c4", linking_phrase="에서 양분을 얻음"),
        ],
        cross_links=[],
        examples=[
            Example(concept_id="c5", text="해바라기, 상추"),
        ],
    )
    t0 = time.time()
    logger.info("Submitting pre-map (will call Opus for diagnosis)...")
    pre_result = mgr.submit_pre_concept_map(sid, pre_map)
    logger.info(
        "Pre-map submitted in %.1fs. Diagnosis level=%s",
        time.time() - t0,
        pre_result.diagnosis.level if pre_result.diagnosis else "(none)",
    )

    # 3) Two short dialogue turns
    for student_msg in [
        "광합성은 식물이 빛을 받아서 에너지를 만드는 거야. 해바라기가 해를 따라 움직이잖아.",
        "아 그러고보니 흙은 양분 자체가 아니라, 식물이 필요한 물이랑 무기질을 얻는 곳이네.",
    ]:
        t0 = time.time()
        ai_turn = mgr.submit_student_turn(sid, student_msg)
        logger.info(
            "Dialogue turn in %.1fs. AI said: %s",
            time.time() - t0,
            ai_turn.content[:80] + ("..." if len(ai_turn.content) > 80 else ""),
        )

    # 4) End dialogue
    mgr.end_dialogue(sid)

    # 5) Post-map (with new cross-link showing integration)
    post_map = ConceptMap(
        concepts=[
            Concept(id="c1", label="광합성"),
            Concept(id="c2", label="빛"),
            Concept(id="c3", label="물"),
            Concept(id="c4", label="엽록체"),
            Concept(id="c5", label="식물"),
            Concept(id="c6", label="포도당"),
            Concept(id="c7", label="산소"),
        ],
        propositions=[
            Proposition(from_id="c1", to_id="c2", linking_phrase="의 조건은"),
            Proposition(from_id="c1", to_id="c3", linking_phrase="의 조건은"),
            Proposition(from_id="c1", to_id="c6", linking_phrase="의 산물은"),
            Proposition(from_id="c1", to_id="c7", linking_phrase="의 산물은"),
            Proposition(from_id="c1", to_id="c4", linking_phrase="이 일어나는 곳"),
            Proposition(from_id="c5", to_id="c1", linking_phrase="이 수행함"),
        ],
        cross_links=[
            CrossLink(from_id="c4", to_id="c2", linking_phrase="가 흡수함"),
        ],
        examples=[Example(concept_id="c6", text="설탕은 식물이 만든 포도당의 변형")],
    )
    mgr.submit_post_concept_map(sid, post_map)
    logger.info("Post-map submitted.")

    # 6) Reflection submission — triggers full analysis + PDF generation
    reflection_answers = {
        "q1_conceptual_change": (
            "대화 전엔 식물이 흙에서 양분을 흡수한다고 막연히 생각했는데, "
            "지후의 질문을 받으며 '양분'과 '물·무기질'이 다르다는 걸 구분하게 됐다. "
            "광합성이 식물 스스로 양분을 만드는 과정이라는 점이 훨씬 선명해졌다."
        ),
        "q2_effective_question": (
            "'흙은 식물에게 뭘 해주는 거야?' 같은 질문이 가장 좋았다. "
            "내 설명의 빈틈을 직접 드러내서, 흙의 역할을 다시 언어화하게 만들었다. "
            "특히 그 질문 덕분에 '양분'과 '물·무기질'을 구분하게 된 것이 가장 큰 수확이었다."
        ),
        "q3_scaffolding": (
            "중간에 '그럼 밤에는?' 같은 반례 질문에서 막혔다. 광합성과 호흡을 "
            "분리해서 생각하던 습관을 재구성해야 했다. 지후가 성급하게 답을 주지 "
            "않고 계속 물어본 덕에 천천히 정리할 수 있었다."
        ),
        "q4_counterfactual": (
            "다시 한다면 광합성의 '조건-장소-산물' 세 축을 먼저 언급한 뒤에 "
            "각 요소를 설명하는 순서로 가겠다. 오늘은 흙 얘기로 먼저 빠져서 "
            "구조가 흐트러졌다. 또 엽록체를 일찍 꺼내면 '장소' 논의가 자연스럽다."
        ),
        "q5_learning_by_teaching": (
            "교과서를 읽을 땐 넘어갔던 '흙의 역할' 같은 부분이 설명하려니 "
            "갑자기 뚜렷해지지 않았다. 남에게 말로 풀어야 내 이해의 결함이 "
            "드러난다는 점이 가장 큰 차이였다. 읽기만 할 때는 '안다'고 생각하던 걸 "
            "설명하면서 진짜로 이해하고 있었는지 검증하게 됐다."
        ),
    }
    logger.info("Submitting reflection — this triggers full analysis + PDF (may take ~1min)...")
    t0 = time.time()
    mgr.submit_reflection_answers(sid, reflection_answers)
    logger.info("Full session completion took %.1fs", time.time() - t0)

    # 7) Verify PDFs
    paths = mgr.get_report_paths(sid)
    if paths is None:
        logger.error("PDF paths not found.")
        return 1

    summary_ok = paths.summary.exists() and paths.summary.stat().st_size > 2000
    detail_ok = paths.detail.exists() and paths.detail.stat().st_size > 4000
    logger.info(
        "PDFs: summary=%s (%d bytes) · detail=%s (%d bytes)",
        paths.summary.name if summary_ok else "MISSING",
        paths.summary.stat().st_size if paths.summary.exists() else 0,
        paths.detail.name if detail_ok else "MISSING",
        paths.detail.stat().st_size if paths.detail.exists() else 0,
    )

    repo = SessionRepository()
    row = repo.get_session(sid)
    analysis = row.analysis_json or {}
    errors = analysis.get("errors") or []
    logger.info("Analysis error count: %d", len(errors))
    for e in errors[:5]:
        logger.info("  - %s", e)

    ok = summary_ok and detail_ok
    print()
    print("=" * 60)
    print("SMOKE TEST RESULT:", "✅ PASS" if ok else "❌ FAIL")
    print(f"Summary PDF: {paths.summary}")
    print(f"Detail PDF:  {paths.detail}")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
