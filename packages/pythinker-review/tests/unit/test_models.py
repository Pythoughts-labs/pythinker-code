from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pythinker_review.store.models import (
    Category,
    ChunkFailure,
    Finding,
    Location,
    RunMeta,
    Severity,
    Suggestion,
)


def _now() -> datetime:
    return datetime(2026, 5, 20, 12, 30, 45, tzinfo=UTC)


def test_severity_and_category_are_string_enums() -> None:
    assert Severity.high.value == "high"
    assert Category.security.value == "security"
    assert Category.debugging.value == "debugging"


def test_finding_round_trip_uses_pass_alias() -> None:
    finding = Finding.model_validate(
        {
            "id": "abcd12345678",
            "rule_id": "sec.injection.sql",
            "title": "Unsanitized user input concatenated into SQL",
            "rationale": "...",
            "category": Category.security,
            "severity": Severity.high,
            "location": Location(file="src/db.py", start_line=10, end_line=12, sha="deadbeef"),
            "suggestion": Suggestion(summary="Use parameterized query"),
            "evidence_snippet": "cursor.execute('... ' + user_input)",
            "confidence": 0.9,
            "created_at": _now(),
            "run_id": "20260520123045-a1b2c3d4",
            "pass": "security_review",
        }
    )
    dumped = finding.model_dump(by_alias=True)
    assert dumped["pass"] == "security_review"
    assert "pass_" not in dumped
    assert Finding.model_validate(dumped).pass_ == "security_review"


def test_finding_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate(
            {
                "id": "abcd12345678",
                "rule_id": "r",
                "title": "t",
                "rationale": "r",
                "category": Category.correctness,
                "severity": Severity.low,
                "location": Location(file="a", start_line=1, end_line=1),
                "confidence": 1.5,
                "created_at": _now(),
                "run_id": "r",
                "pass": "code_review",
            }
        )


def test_run_meta_default_lists_are_empty() -> None:
    run = RunMeta(
        id="20260520123045-a1b2c3d4",
        started_at=_now(),
        finished_at=None,
        status="running",
        repo_root="/tmp/repo",
        branch="main",
        head_sha="abc",
        base_ref="origin/main",
        base_sha="def",
        source_label="git-diff:origin/main",
        passes=["code_review"],
        model="anthropic:claude-sonnet-4-6",
        chunks_total=0,
        chunks_done=0,
        chunks_failed=0,
        findings_count=0,
        allow_partial=False,
        config_hash="0" * 64,
    )
    assert run.chunk_failures == []


def test_chunk_failure_serializes_pass_alias() -> None:
    failure = ChunkFailure.model_validate(
        {"file": "src/x.py", "reason": "timeout", "message": "exceeded 120s", "pass": "code_review"}
    )
    assert failure.model_dump(by_alias=True)["pass"] == "code_review"
