import json
from datetime import UTC, datetime

from pythinker_review.output.json import render_json
from pythinker_review.output.pretty import render_pretty
from pythinker_review.output.sarif import render_sarif
from pythinker_review.store.models import Category, Finding, Location, RunMeta, Severity


def _meta(findings_count: int = 1) -> RunMeta:
    now = datetime(2026, 5, 20, tzinfo=UTC)
    return RunMeta(
        id="r1",
        started_at=now,
        finished_at=now,
        status="completed",
        repo_root="/r",
        branch="main",
        head_sha="h",
        base_ref="main",
        base_sha="b",
        source_label="git-diff:main",
        passes=["security_review"],
        model="m",
        chunks_total=1,
        chunks_done=1,
        chunks_failed=0,
        findings_count=findings_count,
        allow_partial=False,
        config_hash="0" * 64,
    )


def _finding() -> Finding:
    return Finding.model_validate(
        {
            "id": "abcd12345678",
            "rule_id": "sec.x",
            "title": "Hardcoded secret",
            "rationale": "The key looks real.",
            "category": Category.secret,
            "severity": Severity.critical,
            "location": Location(file="a.py", start_line=10, end_line=10),
            "confidence": 0.95,
            "created_at": datetime(2026, 5, 20, tzinfo=UTC),
            "run_id": "r1",
            "pass": "security_review",
        }
    )


def test_pretty_contains_severity_file_and_title() -> None:
    out = render_pretty(_meta(), [_finding()], no_color=True)
    assert "CRITICAL" in out
    assert "a.py:10" in out
    assert "Hardcoded secret" in out


def test_pretty_no_findings_message() -> None:
    assert "no findings" in render_pretty(_meta(0), [], no_color=True).lower()


def test_json_shape() -> None:
    out = json.loads(render_json(_meta(0), []))
    assert out["run"]["id"] == "r1"
    assert out["findings"] == []


def test_sarif_shape_and_level() -> None:
    sarif = json.loads(render_sarif(_meta(), [_finding()]))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"][0]["level"] == "error"
