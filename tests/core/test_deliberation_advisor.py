from pythinker_code.soul.deliberation import (
    _format_questions_for_advisor,
    _strip_recommended,
)
from pythinker_code.wire.types import QuestionItem, QuestionOption


def test_strip_recommended_marker() -> None:
    assert _strip_recommended("Use Postgres (Recommended)") == "Use Postgres"
    assert _strip_recommended("Use Postgres") == "Use Postgres"
    assert _strip_recommended("Keep (recommended)") == "Keep"


def test_format_questions_is_blind() -> None:
    q = QuestionItem(
        question="Which DB?",
        header="DB",
        options=[
            QuestionOption(label="Postgres (Recommended)", description="solid"),
            QuestionOption(label="SQLite", description="simple"),
        ],
        multi_select=False,
    )
    text = _format_questions_for_advisor([q])
    assert "Which DB?" in text
    assert "Postgres" in text and "SQLite" in text
    # blind-first: the favored marker must not leak to the advisor
    assert "(Recommended)" not in text
    assert "recommended" not in text.lower()
