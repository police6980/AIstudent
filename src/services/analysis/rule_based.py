"""Rule-based analysis of a completed session.

Pure-Python, no LLM. Runs in milliseconds. Produces:
    - turn statistics (counts, lengths, ratios)
    - keyword frequency for rubric matching
    - hesitation markers / metacognitive markers
    - rubric item hit map (which turn first mentioned each rubric keyword)
    - question vs statement ratio
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Optional

from src.models.enums import Speaker
from src.models.schemas import RubricItem, Turn

# Hedging / uncertainty expressions frequently used in Korean student speech.
HESITATION_PATTERNS = [
    r"같아요?",
    r"같은데",
    r"인\s*것\s*같",
    r"아마",
    r"아마도",
    r"것\s*같아",
    r"일\s*수도",
    r"잘\s*모르",
    r"헷갈",
    r"확실하지\s*않",
    r"확실치\s*않",
]

# Metacognitive / reflective markers.
METACOGNITIVE_PATTERNS = [
    r"정리하면",
    r"다시\s*말하면",
    r"내가\s*방금",
    r"내가\s*아까",
    r"내\s*말",
    r"요약하면",
    r"쉽게\s*말하면",
    r"그러니까\s*결국",
    r"핵심은",
]

# Simple Korean question heuristic: ends with question mark, or ends with
# common interrogative endings.
_QUESTION_ENDINGS_RE = re.compile(r"(\?|까요?\s*[?]?$|요[?]?$|거야\?|ㄴ가요?$|나요?$)")

# Very lightweight stopword list for keyword extraction / noise filtering.
_STOP_TOKENS = {
    "그래서", "그런데", "그리고", "그럼", "그러면",
    "있어", "있어요", "있다", "없다", "없어", "없어요",
    "해요", "하다", "한다", "합니다", "하고",
    "돼요", "되다", "된다", "됩니다",
    "저는", "나는", "너는", "우리",
    "뭐야", "뭔데", "뭐지",
}


# ---- stats dataclasses ------------------------------------------------

@dataclass
class SpeakerStats:
    turn_count: int = 0
    total_chars: int = 0
    lengths: list[int] = field(default_factory=list)
    question_count: int = 0

    @property
    def avg_length(self) -> float:
        if not self.lengths:
            return 0.0
        return round(statistics.mean(self.lengths), 1)

    @property
    def max_length(self) -> int:
        return max(self.lengths) if self.lengths else 0

    @property
    def min_length(self) -> int:
        return min(self.lengths) if self.lengths else 0


@dataclass
class TurnStatistics:
    student: SpeakerStats = field(default_factory=SpeakerStats)
    ai: SpeakerStats = field(default_factory=SpeakerStats)
    total_turns: int = 0

    def to_dict(self) -> dict:
        def _spk(s: SpeakerStats) -> dict:
            return {
                "turn_count": s.turn_count,
                "total_chars": s.total_chars,
                "avg_length": s.avg_length,
                "max_length": s.max_length,
                "min_length": s.min_length,
                "question_count": s.question_count,
            }

        return {
            "total_turns": self.total_turns,
            "student": _spk(self.student),
            "ai": _spk(self.ai),
        }


@dataclass
class MarkerHit:
    turn_index: int
    pattern: str
    excerpt: str


@dataclass
class RubricHit:
    item_id: str
    keyword_matched: str
    first_turn_index: int
    first_turn_excerpt: str
    hit_count: int


@dataclass
class RuleBasedAnalysis:
    turn_statistics: TurnStatistics
    hesitation_markers: list[MarkerHit]
    metacognitive_markers: list[MarkerHit]
    rubric_hits: list[RubricHit]
    rubric_items_achieved: dict[str, bool]
    keyword_frequencies: dict[str, int]

    def to_dict(self) -> dict:
        def _m(m: MarkerHit) -> dict:
            return {"turn_index": m.turn_index, "pattern": m.pattern, "excerpt": m.excerpt}

        def _r(r: RubricHit) -> dict:
            return {
                "item_id": r.item_id,
                "keyword_matched": r.keyword_matched,
                "first_turn_index": r.first_turn_index,
                "first_turn_excerpt": r.first_turn_excerpt,
                "hit_count": r.hit_count,
            }

        return {
            "turn_statistics": self.turn_statistics.to_dict(),
            "hesitation_markers": [_m(m) for m in self.hesitation_markers],
            "metacognitive_markers": [_m(m) for m in self.metacognitive_markers],
            "rubric_hits": [_r(r) for r in self.rubric_hits],
            "rubric_items_achieved": self.rubric_items_achieved,
            "keyword_frequencies": self.keyword_frequencies,
        }


# ---- helpers ----------------------------------------------------------


def _is_question(text: str) -> bool:
    return bool(_QUESTION_ENDINGS_RE.search(text or ""))


def _find_patterns(
    patterns: list[str], turns: list[Turn], speaker_filter: Optional[Speaker] = None
) -> list[MarkerHit]:
    hits: list[MarkerHit] = []
    compiled = [re.compile(p) for p in patterns]
    for idx, t in enumerate(turns):
        if speaker_filter and t.speaker != speaker_filter:
            continue
        for cp, pat in zip(compiled, patterns):
            m = cp.search(t.content)
            if m:
                hits.append(
                    MarkerHit(
                        turn_index=idx,
                        pattern=pat,
                        excerpt=_windowed_excerpt(t.content, m.start(), m.end()),
                    )
                )
    return hits


def _windowed_excerpt(text: str, start: int, end: int, window: int = 25) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right]
    if left > 0:
        snippet = "…" + snippet
    if right < len(text):
        snippet = snippet + "…"
    return snippet.replace("\n", " ")


def _count_tokens_case_insensitive(text: str, needle: str) -> int:
    if not needle:
        return 0
    return len(re.findall(re.escape(needle), text))


# ---- main entry point -------------------------------------------------


def analyse_turns_rule_based(
    turns: list[Turn], rubric_items: list[RubricItem]
) -> RuleBasedAnalysis:
    """Compute all rule-based analyses for a completed session's transcript."""

    stats = TurnStatistics(total_turns=len(turns))
    for t in turns:
        target = stats.student if t.speaker == Speaker.STUDENT else stats.ai
        target.turn_count += 1
        target.total_chars += len(t.content)
        target.lengths.append(len(t.content))
        if _is_question(t.content):
            target.question_count += 1

    hesitation = _find_patterns(HESITATION_PATTERNS, turns, speaker_filter=Speaker.STUDENT)
    metacog = _find_patterns(METACOGNITIVE_PATTERNS, turns, speaker_filter=Speaker.STUDENT)

    rubric_hits: list[RubricHit] = []
    items_achieved: dict[str, bool] = {item.item_id: False for item in rubric_items}
    keyword_freq: dict[str, int] = {}

    # Rubric matching runs on student turns only — the AI is forbidden from
    # disclosing answers, so a hit must come from the student to count.
    student_turns_indexed = [
        (idx, t) for idx, t in enumerate(turns) if t.speaker == Speaker.STUDENT
    ]

    for item in rubric_items:
        first_hit_turn: Optional[int] = None
        first_hit_kw: Optional[str] = None
        first_hit_excerpt: str = ""
        total = 0
        for kw in item.keywords:
            kw_total = 0
            for idx, t in student_turns_indexed:
                c = _count_tokens_case_insensitive(t.content, kw)
                if c:
                    kw_total += c
                    if first_hit_turn is None or idx < first_hit_turn:
                        first_hit_turn = idx
                        first_hit_kw = kw
                        # Excerpt around the first occurrence
                        m = re.search(re.escape(kw), t.content)
                        if m:
                            first_hit_excerpt = _windowed_excerpt(
                                t.content, m.start(), m.end()
                            )
            if kw_total:
                keyword_freq[kw] = keyword_freq.get(kw, 0) + kw_total
                total += kw_total

        if total > 0 and first_hit_turn is not None and first_hit_kw is not None:
            rubric_hits.append(
                RubricHit(
                    item_id=item.item_id,
                    keyword_matched=first_hit_kw,
                    first_turn_index=first_hit_turn,
                    first_turn_excerpt=first_hit_excerpt,
                    hit_count=total,
                )
            )
            items_achieved[item.item_id] = True

    return RuleBasedAnalysis(
        turn_statistics=stats,
        hesitation_markers=hesitation,
        metacognitive_markers=metacog,
        rubric_hits=rubric_hits,
        rubric_items_achieved=items_achieved,
        keyword_frequencies=keyword_freq,
    )
