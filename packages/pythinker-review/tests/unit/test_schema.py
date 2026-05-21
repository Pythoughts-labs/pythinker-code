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
