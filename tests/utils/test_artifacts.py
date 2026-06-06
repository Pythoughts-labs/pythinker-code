"""Tests for the boundary-artifact dataclasses used between subagents."""

from __future__ import annotations

import dataclasses
import json

import pytest

from pythinker_code.utils.artifacts import (
    AuditVerdict,
    CodingArtifact,
    VerificationResult,
    VulnerabilityArtifact,
)

# ---------------------------------------------------------------------------
# CodingArtifact
# ---------------------------------------------------------------------------


def test_coding_artifact_round_trip() -> None:
    artifact = CodingArtifact(
        files_changed=["src/a.py", "src/b.py"],
        test_command="pytest -q",
        expected_behavior="all tests pass",
        edge_cases_claimed=["empty input", "unicode"],
    )
    payload = json.loads(artifact.to_json())
    restored = CodingArtifact.from_dict(payload)
    assert restored == artifact


def test_coding_artifact_default_edge_cases() -> None:
    artifact = CodingArtifact(
        files_changed=["a.py"],
        test_command="pytest",
        expected_behavior="passes",
    )
    assert artifact.edge_cases_claimed == []


def test_coding_artifact_frozen() -> None:
    artifact = CodingArtifact(
        files_changed=["a.py"],
        test_command="pytest",
        expected_behavior="passes",
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        artifact.files_changed = ["b.py"]  # type: ignore[misc]


def test_coding_artifact_to_json_field_names() -> None:
    artifact = CodingArtifact(
        files_changed=["a.py"],
        test_command="pytest",
        expected_behavior="passes",
        edge_cases_claimed=["x"],
    )
    payload = json.loads(artifact.to_json())
    assert set(payload.keys()) == {
        "files_changed",
        "test_command",
        "expected_behavior",
        "edge_cases_claimed",
    }


def test_coding_artifact_to_json_is_indented() -> None:
    artifact = CodingArtifact(
        files_changed=["a.py"],
        test_command="pytest",
        expected_behavior="passes",
    )
    rendered = artifact.to_json()
    assert "\n" in rendered


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------


def test_verification_result_defaults() -> None:
    result = VerificationResult(
        passed=True,
        stdout_summary="ok",
        stderr_summary="",
    )
    assert result.discovered_gaps == []


def test_verification_result_frozen() -> None:
    result = VerificationResult(
        passed=True,
        stdout_summary="ok",
        stderr_summary="",
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        result.passed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# VulnerabilityArtifact
# ---------------------------------------------------------------------------


def test_vulnerability_artifact_round_trip() -> None:
    artifact = VulnerabilityArtifact(
        target_file="src/auth.py",
        vulnerability_type="sql_injection",
        reproduction_command="python exploit.py",
        expected_failure_output="Traceback ...",
    )
    payload = json.loads(artifact.to_json())
    restored = VulnerabilityArtifact.from_dict(payload)
    assert restored == artifact


def test_vulnerability_artifact_to_json_field_names() -> None:
    artifact = VulnerabilityArtifact(
        target_file="src/auth.py",
        vulnerability_type="sql_injection",
        reproduction_command="python exploit.py",
        expected_failure_output="Traceback ...",
    )
    payload = json.loads(artifact.to_json())
    assert set(payload.keys()) == {
        "target_file",
        "vulnerability_type",
        "reproduction_command",
        "expected_failure_output",
    }


def test_vulnerability_artifact_frozen() -> None:
    artifact = VulnerabilityArtifact(
        target_file="src/auth.py",
        vulnerability_type="sql_injection",
        reproduction_command="python exploit.py",
        expected_failure_output="Traceback ...",
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        artifact.target_file = "src/other.py"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AuditVerdict
# ---------------------------------------------------------------------------


def test_audit_verdict_defaults() -> None:
    verdict = AuditVerdict(
        vulnerability_confirmed=True,
        execution_logs="logs",
    )
    assert verdict.false_positive_reasoning == ""


def test_audit_verdict_frozen() -> None:
    verdict = AuditVerdict(
        vulnerability_confirmed=True,
        execution_logs="logs",
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        verdict.vulnerability_confirmed = False  # type: ignore[misc]
