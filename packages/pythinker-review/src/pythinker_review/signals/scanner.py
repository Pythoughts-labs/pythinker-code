"""Deterministic security-signal regex scanner. Prompt anchors only."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pythinker_review.signals.models import Signal


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    reason: str
    confidence: float
    source_kind: str | None = None
    sink_kind: str | None = None
    exploitability: str | None = None
    mitigation_hint: str | None = None


_RULES: tuple[_Rule, ...] = (
    _Rule(
        "sec.signal.secret.aws_access_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "Looks like an AWS access key ID added to source.",
        0.95,
        source_kind="literal",
        sink_kind="source",
        exploitability="Committed credentials can be used directly if active.",
        mitigation_hint="Remove the key, rotate it, and load credentials from a secret store.",
    ),
    _Rule(
        "sec.signal.secret.generic_token",
        re.compile(
            r"""(?ix)
            (?:api[_-]?key|secret|token|password|passwd|pwd)\s*[=:]\s*
            ['\"][A-Za-z0-9_\-]{16,}['\"]
            """
        ),
        "Possible hardcoded credential.",
        0.7,
        source_kind="literal",
        sink_kind="source",
        mitigation_hint="Load secrets from environment or a secret manager.",
    ),
    _Rule(
        "sec.signal.shell.user_var",
        re.compile(
            r"""(?x)
            (?:subprocess\.(?:run|Popen|call|check_call|check_output)|os\.(?:system|popen))
            \([^)]*\bshell\s*=\s*True
            """
        ),
        "shell=True with dynamic argument shape.",
        0.75,
        sink_kind="command_execution",
        mitigation_hint="Pass argv as a list and avoid shell=True unless input is fixed.",
    ),
    _Rule(
        "sec.signal.sql.concat",
        re.compile(
            r"""(?ix)
            (?:cursor|conn|connection|db)\.execute\s*\(
            \s*["'][^"']*\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^"']*["']\s*[+%]
            """
        ),
        "SQL string concatenation passed to execute().",
        0.85,
        sink_kind="sql_execution",
        mitigation_hint="Use parameterized queries.",
    ),
    _Rule(
        "sec.signal.deserialization.unsafe",
        re.compile(r"\b[p]ickle\.(?:load|loads)\s*\("),
        "Unsafe deserialization of potentially untrusted data.",
        0.7,
        sink_kind="deserialization",
        mitigation_hint="Use a safe format or prove the input is trusted.",
    ),
    _Rule(
        "sec.signal.ssrf.requests_var_url",
        re.compile(
            r"""(?x)
            (?:requests|urllib|httpx|aiohttp)\.(?:get|post|put|delete|request)\s*\(
            \s*[A-Za-z_][A-Za-z0-9_]*
            """
        ),
        "HTTP request to a URL held in a variable; check for SSRF guard.",
        0.5,
        sink_kind="http_client",
        mitigation_hint="Validate scheme/host and block private-network destinations.",
    ),
    _Rule(
        "sec.signal.crypto.weak_hash",
        re.compile(r"\bhashlib\.(?:md5|sha1)\s*\("),
        "Weak hash used; verify it is not a security boundary.",
        0.6,
        sink_kind="crypto",
        mitigation_hint="Use SHA-256+ or a password-hashing/KDF primitive as appropriate.",
    ),
)


def scan_signals(*, file_path: str, added_lines: list[tuple[int, str]]) -> list[Signal]:
    out: list[Signal] = []
    for lineno, text in added_lines:
        for rule in _RULES:
            if rule.pattern.search(text):
                out.append(
                    Signal(
                        rule_id=rule.rule_id,
                        file=file_path,
                        line=lineno,
                        snippet=text.strip(),
                        reason=rule.reason,
                        confidence=rule.confidence,
                        source_kind=rule.source_kind,
                        sink_kind=rule.sink_kind,
                        exploitability=rule.exploitability,
                        mitigation_hint=rule.mitigation_hint,
                    )
                )
    return out
