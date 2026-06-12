from __future__ import annotations

import fnmatch
import re
from pathlib import PurePath

# High-confidence sensitive file patterns.
# Only patterns with very low false-positive risk are included.
SENSITIVE_PATTERNS: list[str] = [
    # Environment variable / secrets
    ".env",
    ".env.*",
    # SSH private keys
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    # Cloud credentials (path-based, also bare name for stripped-path scenarios)
    ".aws/credentials",
    ".gcp/credentials",
    "credentials",
]

# Template/example files that match .env.* but are not sensitive.
SENSITIVE_EXEMPTIONS: set[str] = {
    ".env.example",
    ".env.sample",
    ".env.template",
}


def is_sensitive_file(path: str) -> bool:
    """Check if a file path matches any sensitive file pattern."""
    name = PurePath(path).name.lower()
    path_lower = path.lower()
    if name in SENSITIVE_EXEMPTIONS:
        return False
    for pattern in SENSITIVE_PATTERNS:
        if "/" in pattern:
            if path_lower.endswith(pattern) or ("/" + pattern) in path_lower:
                return True
        else:
            if fnmatch.fnmatch(name, pattern):
                return True
    return False


_REDACTED = "[REDACTED]"

# Key names (case-insensitive) whose assigned value is a secret. Matched as a
# substring of the key, so PASSWORD covers ADMIN_PASSWORD, DB_PASSWORD, etc.
_SECRET_KEY_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "auth_token",
    "client_secret",
)
_SECRET_KEY_GROUP = "|".join(re.escape(h) for h in _SECRET_KEY_HINTS)

# A key=value or key: value assignment whose key ENDS with a secret hint. The
# hint must sit immediately before the separator (optionally through a closing
# JSON quote) so benign keys like ``token_count`` / ``access_key_id`` are left
# alone while ``ADMIN_PASSWORD`` / ``SECRET_TOKEN`` / ``"api_key"`` match. A
# leading grep line-number/path prefix ("3ADMIN_PASSWORD=…") is preserved.
_SECRET_ASSIGNMENT_RE = re.compile(
    rf"(?im)^(?P<prefix>.*?(?:{_SECRET_KEY_GROUP})[\"']?\s*[=:]\s*)(?P<value>\S.*?)\s*$"
)


def redact_secrets(text: str) -> str:
    """Redact secret values from free text (tool output, exported transcripts).

    Conservative and line-oriented: only the value of a ``KEY=VALUE`` /
    ``KEY: VALUE`` assignment whose key looks like a secret (password, token,
    api_key, …) is replaced with ``[REDACTED]``. Non-secret keys, prose, and
    code are left untouched. This is defense-in-depth for places where a tool
    result may have surfaced an ``.env`` value — not a guarantee that every
    possible secret format is caught.
    """
    if not text:
        return text

    def _sub(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{_REDACTED}"

    return _SECRET_ASSIGNMENT_RE.sub(_sub, text)


def sensitive_file_warning(paths: list[str]) -> str:
    """Generate a warning message for sensitive files that were skipped."""
    names = sorted({PurePath(p).name for p in paths})
    file_list = ", ".join(names[:5])
    if len(names) > 5:
        file_list += f", ... ({len(names)} files total)"
    return (
        f"Skipped {len(paths)} sensitive file(s) ({file_list}) "
        f"to protect secrets. These files may contain credentials or private keys."
    )
