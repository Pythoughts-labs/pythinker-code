"""Boundary-artifact dataclasses exchanged between coder and verifier subagents.

These dataclasses enforce a strict information barrier: verifiers receive ONLY the
typed fields declared here, never prose or logs from the producer. The shape of
``to_json`` / ``from_dict`` is a contract surface consumed by subagent prompts.

Two pairs are defined:

* ``CodingArtifact`` / ``VerificationResult`` for the generic coder-to-verifier flow.
* ``VulnerabilityArtifact`` / ``AuditVerdict`` for the security-specific finder-to-audit
  flow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CodingArtifact:
    """Producer-side handoff from a coder subagent to a verifier subagent."""

    files_changed: list[str]
    test_command: str
    expected_behavior: str
    edge_cases_claimed: list[str] = field(default_factory=list[str])

    def to_json(self) -> str:
        return json.dumps(
            {
                "files_changed": self.files_changed,
                "test_command": self.test_command,
                "expected_behavior": self.expected_behavior,
                "edge_cases_claimed": self.edge_cases_claimed,
            },
            indent=2,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CodingArtifact:
        return cls(
            files_changed=d["files_changed"],
            test_command=d["test_command"],
            expected_behavior=d["expected_behavior"],
            edge_cases_claimed=d.get("edge_cases_claimed", []),
        )


@dataclass(frozen=True)
class VerificationResult:
    """Verifier-side response back to the coder."""

    passed: bool
    stdout_summary: str
    stderr_summary: str
    discovered_gaps: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class VulnerabilityArtifact:
    """Producer-side handoff from a vulnerability finder to the audit verifier."""

    target_file: str
    vulnerability_type: str
    reproduction_command: str
    expected_failure_output: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "target_file": self.target_file,
                "vulnerability_type": self.vulnerability_type,
                "reproduction_command": self.reproduction_command,
                "expected_failure_output": self.expected_failure_output,
            },
            indent=2,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VulnerabilityArtifact:
        return cls(
            target_file=d["target_file"],
            vulnerability_type=d["vulnerability_type"],
            reproduction_command=d["reproduction_command"],
            expected_failure_output=d["expected_failure_output"],
        )


@dataclass(frozen=True)
class AuditVerdict:
    """Audit-verifier verdict on a claimed vulnerability."""

    vulnerability_confirmed: bool
    execution_logs: str
    false_positive_reasoning: str = ""
