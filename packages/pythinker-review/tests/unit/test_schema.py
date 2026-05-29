import pytest
from pydantic import ValidationError

from pythinker_review.reviewers.schema import RawFinding, ReviewerOutput
from pythinker_review.store.models import Category, Severity


def test_reviewer_output_parses_minimal_payload() -> None:
    out = ReviewerOutput.model_validate(
        {
            "findings": [
                {
                    "rule_id": "review.error_handling",
                    "title": "Catch is too broad",
                    "rationale": "...",
                    "category": "correctness",
                    "severity": "medium",
                    "file": "src/a.py",
                    "start_line": 5,
                    "end_line": 5,
                    "confidence": 0.8,
                }
            ]
        }
    )
    assert len(out.findings) == 1
    assert out.findings[0].category is Category.correctness
    assert out.findings[0].severity is Severity.medium


def test_reviewer_output_truncates_overlong_title() -> None:
    # An over-long title must not fail the whole parse (which would drop every
    # finding in the chunk); it is truncated to the budget instead.
    out = ReviewerOutput.model_validate(
        {
            "findings": [
                {
                    "rule_id": "r",
                    "title": "T" * 200,
                    "rationale": "...",
                    "category": "correctness",
                    "severity": "low",
                    "file": "a.py",
                    "start_line": 1,
                    "end_line": 1,
                    "confidence": 0.5,
                }
            ]
        }
    )
    title = out.findings[0].title
    assert len(title) == 80
    assert title.endswith("…")


def test_reviewer_output_keeps_short_title_unchanged() -> None:
    finding = RawFinding(
        rule_id="r",
        title="Short title",
        rationale="r",
        category=Category.correctness,
        severity=Severity.low,
        file="a",
        start_line=1,
        end_line=1,
        confidence=0.5,
    )
    assert finding.title == "Short title"


def test_reviewer_output_rejects_lines_under_one() -> None:
    with pytest.raises(ValidationError):
        RawFinding(
            rule_id="r",
            title="t",
            rationale="r",
            category=Category.correctness,
            severity=Severity.low,
            file="a",
            start_line=0,
            end_line=1,
            confidence=0.5,
        )
