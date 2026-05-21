from datetime import UTC, datetime

from pythinker_review.engine.dedupe import dedupe_findings, finding_id
from pythinker_review.reviewers.schema import RawFinding
from pythinker_review.store.models import Category, Finding, Location, Severity


def _raw(
    rule: str = "sec.x", line: int = 5, sev: Severity = Severity.high, conf: float = 0.7
) -> RawFinding:
    return RawFinding(
        rule_id=rule,
        title="t",
        rationale="r",
        category=Category.security,
        severity=sev,
        file="a.py",
        start_line=line,
        end_line=line,
        confidence=conf,
    )


def test_finding_id_is_deterministic() -> None:
    assert finding_id("sec.x", "a.py", 5, "t") == finding_id("sec.x", "a.py", 5, "t")
    assert len(finding_id("sec.x", "a.py", 5, "t")) == 12


def test_dedupe_collapses_same_key_keeping_higher_severity() -> None:
    now = datetime(2026, 5, 20, tzinfo=UTC)
    result = dedupe_findings(
        [
            ("security_review", _raw(sev=Severity.low, conf=0.9)),
            ("security_review", _raw(sev=Severity.high, conf=0.5)),
        ],
        run_id="r1",
        head_sha="abc",
        created_at=now,
    )
    assert len(result) == 1
    assert result[0].severity is Severity.high


def test_dedupe_security_wins_tie_with_code_review() -> None:
    now = datetime(2026, 5, 20, tzinfo=UTC)
    out = dedupe_findings(
        [
            ("code_review", _raw(rule="sec.x", sev=Severity.medium, conf=0.8)),
            ("security_review", _raw(rule="sec.x", sev=Severity.medium, conf=0.8)),
        ],
        run_id="r1",
        head_sha="abc",
        created_at=now,
    )
    assert len(out) == 1
    assert out[0].pass_ == "security_review"


def test_dedupe_returns_full_finding() -> None:
    now = datetime(2026, 5, 20, tzinfo=UTC)
    out = dedupe_findings([("code_review", _raw())], run_id="r1", head_sha="abc", created_at=now)
    assert isinstance(out[0], Finding)
    assert isinstance(out[0].location, Location)
