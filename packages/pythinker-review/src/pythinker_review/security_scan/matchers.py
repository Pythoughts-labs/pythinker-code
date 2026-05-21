"""Python-native Pythinker Security Scan matcher registry and regex execution."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from pythinker_review.security_scan.matchers_data import GENERATED_MATCHERS
from pythinker_review.security_scan.models import CandidateMatch, DetectedTech, NoiseTier

PatternTriple = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class MatcherGate:
    tech: tuple[str, ...] = ()
    sentinel_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RegexPattern:
    regex: str
    flags: str
    label: str
    compiled: re.Pattern[str] | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        py_flags = 0
        if "i" in self.flags:
            py_flags |= re.IGNORECASE
        if "m" in self.flags:
            py_flags |= re.MULTILINE
        if "s" in self.flags:
            py_flags |= re.DOTALL
        try:
            object.__setattr__(
                self, "compiled", re.compile(_translate_js_regex(self.regex), py_flags)
            )
        except re.error:
            # Keep the matcher in the registry for traceability, but skip this
            # unsupported TS-regex fragment at runtime.
            object.__setattr__(self, "compiled", None)


@dataclass(frozen=True, slots=True)
class MatcherSpec:
    slug: str
    description: str
    noise_tier: NoiseTier
    file_patterns: tuple[str, ...]
    requires: MatcherGate | None = None
    patterns: tuple[RegexPattern, ...] = ()
    examples: tuple[str, ...] = ()
    source_file: str | None = None

    def match(self, content: str, file_path: str) -> list[CandidateMatch]:
        matches: list[CandidateMatch] = []
        normalized = content.replace("\r\n", "\n")
        for pattern in self.patterns:
            if pattern.compiled is None:
                continue
            hit_lines: list[int] = []
            snippets: list[str] = []
            lines = normalized.split("\n")
            for idx, line in enumerate(lines):
                if pattern.compiled.search(line):
                    line_no = idx + 1
                    if line_no not in hit_lines:
                        hit_lines.append(line_no)
                    if not snippets:
                        start = max(0, idx - 2)
                        end = min(len(lines), idx + 3)
                        snippets.append("\n".join(lines[start:end]))
            if hit_lines:
                matches.append(
                    CandidateMatch.model_validate(
                        {
                            "vulnSlug": self.slug,
                            "lineNumbers": hit_lines,
                            "snippet": snippets[0] if snippets else "",
                            "matchedPattern": pattern.label,
                        }
                    )
                )
        return matches


class MatcherRegistry:
    def __init__(self) -> None:
        self._matchers: dict[str, MatcherSpec] = {}

    def register(self, matcher: MatcherSpec) -> None:
        self._matchers[matcher.slug] = matcher

    def get_all(self) -> list[MatcherSpec]:
        return list(self._matchers.values())

    def get_by_slug(self, slug: str) -> MatcherSpec | None:
        return self._matchers.get(slug)

    def get_by_slugs(self, slugs: list[str]) -> list[MatcherSpec]:
        return [matcher for slug in slugs if (matcher := self.get_by_slug(slug)) is not None]

    def slugs(self) -> list[str]:
        return list(self._matchers)


# Custom Pythinker Security Scan matcher files often build line-aware logic instead of calling
# regexMatcher(). They are migrated here as compact Python pattern specs. The
# generated metadata still records every source matcher and source path.
_CURATED_PATTERNS: dict[str, tuple[PatternTriple, ...]] = {
    "agent-loop-no-cap": (
        (
            r"\b(?:generateText|streamText|generateObject)\s*\([^\n]*(?![^\n]*(?:maxSteps|maxTurns|stopWhen))",
            "",
            "LLM/agent call without explicit turn cap",
        ),
    ),
    "agentic-untrusted-prompt-input": (
        (
            r"\b(?:system_prompt|developer_prompt|prompt|messages|user_message|tool_output)\b\s*(?:=|\+=|\.append|\.extend|\.format).*\b(?:request|req|user|issue|comment|body|payload|webpage|input)\b",
            "i",
            "untrusted content flows into prompt/messages",
        ),
    ),
    "algorithm-confusion": (
        (
            r"\bjwt\.(?:verify|decode)\s*\([^\n]*(?:algorithms\s*[:=]\s*None|verify\s*[:=]\s*False|'none'|\"none\")",
            "i",
            "JWT verification disabled or algorithm not pinned",
        ),
        (
            r"\bjwt\.(?:verify|decode)\s*\([^\n]*\b(?:publicKey|secret|key)\b(?![^\n]*algorithms)",
            "i",
            "JWT verify call without algorithm allowlist",
        ),
    ),
    "dangerous-html": (
        (
            r"\b(?:dangerouslySetInnerHTML|innerHTML\s*=|outerHTML\s*=|v-html\b|\.html\s*\()",
            "",
            "unsafe HTML rendering sink",
        ),
        (
            r"\b(?:mark_safe|format_html|html_safe|raw\(|\|raw\b|autoescape\s+off)",
            "",
            "explicit template escaping bypass",
        ),
    ),
    "debug-endpoint": (
        (
            r"\b(?:debug\s*=\s*True|DEBUG\s*=\s*True|/debug\b|/admin/debug\b|werkzeug\.debug)",
            "i",
            "debug mode or debug endpoint",
        ),
    ),
    "dockerfile-curl-pipe-unverified": (
        (r"^\s*RUN\s+.*\bcurl\b[^|\n]*\|\s*(?:sh|bash)\b", "i", "curl piped directly to shell"),
        (r"^\s*RUN\s+.*\bwget\b[^|\n]*\|\s*(?:sh|bash)\b", "i", "wget piped directly to shell"),
    ),
    "dockerfile-from-mutable-tag": (
        (
            r"^\s*FROM\s+(?:--platform=\S+\s+)?(?!scratch\b)(?!\$)(?!\S+@sha256:)\S+(?:\s+AS\s+\S+)?\s*$",
            "i",
            "FROM without immutable sha256 digest",
        ),
    ),
    "dockerfile-run-as-root": (
        (r"^\s*USER\s+root\b", "i", "explicit root user"),
        (r"^\s*FROM\s+", "i", "base image defaults to root unless USER is set later"),
    ),
    "env-exposure": (
        (
            r"\b(?:NEXT_PUBLIC_|VITE_|PUBLIC_)\w*(?:SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL)\w*",
            "i",
            "secret-shaped public env var",
        ),
    ),
    "event-handler-mismatch": (
        (
            r"\b(?:addEventListener|onmessage|postMessage)\b",
            "",
            "cross-window/message event trust boundary",
        ),
    ),
    "github-workflow-security": (
        (r"^\s*-?\s*pull_request_target\s*:", "m", "pull_request_target trigger"),
        (
            r"\buses\s*:\s*[\w-]+/[\w./-]+@(?:main|master|develop|v?\d+)\s*$",
            "i",
            "unpinned action ref",
        ),
        (r"\$\{\{\s*github\.(?:event\.|head_ref)", "", "untrusted GitHub context interpolation"),
        (r"^\s*permissions\s*:\s*write-all\b", "mi", "permissions: write-all"),
        (r"\bid-token\s*:\s*write\b", "i", "OIDC token permission"),
        (r"\bcurl\b[^|\n]*\|\s*(?:sh|bash)\b", "i", "curl pipe shell in workflow"),
    ),
    "mcp-tool-handler": (
        (
            r"\b(?:server\.tool|addTool|registerTool|list_tools|call_tool|Tool\()\b",
            "i",
            "MCP/agent tool registration or handler",
        ),
    ),
    "missing-auth": (
        (
            r"\b(?:app|router|api)\.(?:post|put|delete|patch)\s*\([^\n]*(?![^\n]*(?:auth|login_required|Depends|Security|permission|guard))",
            "i",
            "state-changing route without inline auth marker",
        ),
        (
            r"^\s*@(?:app|router|api)\.(?:post|put|delete|patch)\s*\(",
            "m",
            "state-changing route decorator",
        ),
    ),
    "missing-await": (
        (
            r"\b(?:verify|authorize|authenticate|save|delete|update|create)\w*\s*\([^\n;]*\)\s*;",
            "",
            "async-looking security/data operation may be missing await",
        ),
    ),
    "non-atomic-operation": (
        (
            r"\b(?:find|get|select|read).*\n.{0,120}\b(?:update|delete|insert|write|save)\b",
            "is",
            "read-then-write sequence",
        ),
    ),
    "postmessage-origin": (
        (r"\bpostMessage\s*\([^\n]*['\"]\*['\"]", "", "postMessage wildcard target origin"),
        (
            r"\bmessage\.origin\b(?![^\n]*(?:===|!==|startsWith|includes))",
            "",
            "message origin read without obvious validation",
        ),
    ),
    "process-env-access": (
        (
            r"\bprocess\.env\.[A-Z0-9_]*(?:SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL)[A-Z0-9_]*\b",
            "",
            "direct secret env var access",
        ),
    ),
    "prompt-leaks-system-prompt": (
        (
            r"\b(?:system_prompt|developer_prompt|SYSTEM_PROMPT)\b[^\n]*(?:return|send|json|log|print|console)",
            "i",
            "system prompt may be logged or returned",
        ),
    ),
    "rate-limit-bypass": (
        (
            r"\b(?:login|password|reset|otp|2fa|mfa|sendgrid|twilio|openai|anthropic|stripe|checkout|llm|completion|embedding)\b",
            "i",
            "sensitive or expensive operation; verify abuse controls",
        ),
    ),
    "secret-in-log": (
        (
            r"\b(?:console|logger|log|migrationsLogger)\.[a-z]+\s*\([^\n]*(?:token|secret|password|api[_-]?key|credential|privateKey)",
            "i",
            "secret variable in log statement",
        ),
        (
            r"\b(?:throw\s+new\s+\w*Error|res\.(?:json|send|status)|return\s*\{)[^\n]*(?:token|secret|password|api[_-]?key|credential)",
            "i",
            "secret variable in error/response",
        ),
    ),
    "secrets-plaintext-exposure": (
        (
            r"\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|bearer|authorization)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
            "i",
            "credential-shaped literal",
        ),
        (
            r"\b(?:sk_live_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{16,}|ghp_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{12,})\b",
            "",
            "known credential token shape",
        ),
    ),
    "service-entry-point": (
        (
            r"\b(?:handler|handle|Controller|Resource|Function|lambda_handler|main)\b",
            "",
            "service entry point",
        ),
    ),
    "session-cookie-config": (
        (r"\b(?:secure|httpOnly|sameSite)\s*[:=]\s*false\b", "i", "weak cookie flag"),
        (
            r"\bSameSite\s*=\s*(?:None|['\"]none['\"])(?![^\n]*Secure)",
            "i",
            "SameSite=None without Secure",
        ),
    ),
    "slack-signing-verification": (
        (
            r"\b(?:X-Slack-Signature|x-slack-signature|signing_secret|slack_signature)\b",
            "i",
            "Slack signature verification surface",
        ),
    ),
    "tf-iam-wildcard": (
        (r"\b(?:actions?|resources?)\s*=\s*\[?\s*['\"]\*['\"]", "i", "Terraform IAM wildcard"),
    ),
    "tf-public-ingress": (
        (r"\bcidr_blocks\s*=\s*\[[^\]]*0\.0\.0\.0/0", "i", "public ingress CIDR"),
        (r"\bfrom_port\s*=\s*(?:22|3389|5432|3306|6379|9200)\b", "i", "sensitive port exposed"),
    ),
    "tf-secret-in-data": (
        (
            r"\b(?:password|secret|token|api_key)\s*=\s*['\"][^'\"]{8,}['\"]",
            "i",
            "secret literal in Terraform",
        ),
    ),
    "unsafe-redirect": (
        (
            r"\b(?:redirect|RedirectResponse|res\.redirect|router\.push)\s*\([^\n]*(?:next|url|redirect|returnTo|req|request)",
            "i",
            "user-controlled redirect target",
        ),
    ),
    "webhook-handler": (
        (
            r"\b(?:webhook|stripe|github|shopify|slack)\b",
            "i",
            "webhook handler; verify signature before processing",
        ),
    ),
}


def create_default_registry() -> MatcherRegistry:
    registry = MatcherRegistry()
    for raw in cast(list[dict[str, Any]], GENERATED_MATCHERS):
        patterns = [cast(PatternTriple, tuple(pattern)) for pattern in raw.get("patterns") or ()]
        patterns.extend(_CURATED_PATTERNS.get(str(raw["slug"]), ()))
        matcher = MatcherSpec(
            slug=str(raw["slug"]),
            description=str(raw.get("description") or raw["slug"]),
            noise_tier=_noise(str(raw.get("noise_tier") or "normal")),
            file_patterns=tuple(str(p) for p in raw.get("file_patterns", ("**/*",))),
            requires=MatcherGate(tech=tuple(str(t) for t in raw.get("requires_tech") or ()))
            if raw.get("requires_tech")
            else None,
            patterns=tuple(RegexPattern(regex=p[0], flags=p[1], label=p[2]) for p in patterns),
            examples=tuple(str(e) for e in raw.get("examples") or ()),
            source_file=str(raw.get("source_file") or ""),
        )
        registry.register(matcher)
    return registry


def evaluate_gate(matcher: MatcherSpec, detected: DetectedTech, root: Path) -> bool:
    gate = matcher.requires
    if gate is None:
        return True
    if gate.tech and any(tag in set(detected.tags) for tag in gate.tech):
        return True
    return any(any(root.glob(pattern)) for pattern in gate.sentinel_files)


def expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]+)\}", pattern)
    if not match:
        return [pattern]
    prefix = pattern[: match.start()]
    suffix = pattern[match.end() :]
    out: list[str] = []
    for option in match.group(1).split(","):
        out.extend(expand_braces(prefix + option + suffix))
    return out


def path_matches_any(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        for expanded in expand_braces(pattern):
            if fnmatch.fnmatch(normalized, expanded):
                return True
    return False


def files_for_matcher(root: Path, matcher: MatcherSpec, ignore: list[str]) -> list[str]:
    found: set[str] = set()
    for pattern in matcher.file_patterns:
        for expanded in expand_braces(pattern):
            # pathlib handles ** well but not brace expansion; we did that above.
            try:
                candidates = root.glob(expanded)
            except ValueError:
                continue
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                try:
                    rel = candidate.relative_to(root).as_posix()
                except ValueError:
                    continue
                if path_matches_any(rel, ignore):
                    continue
                found.add(rel)
    return sorted(found)


def _noise(value: str) -> NoiseTier:
    if value in {"precise", "normal", "noisy"}:
        return cast(NoiseTier, value)
    return "normal"


def _translate_js_regex(pattern: str) -> str:
    # The source registry is TS regex metadata. Most patterns are already
    # PCRE/Python compatible. Apply only safe mechanical translations.
    return pattern.replace("\\/", "/")
