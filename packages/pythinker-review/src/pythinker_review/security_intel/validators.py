"""Input validation and redaction for public security-intelligence lookups."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
SAFE_KEYWORD_RE = re.compile(r"^[a-zA-Z0-9\s\-_.:/@+]{1,240}$")
PACKAGE_RE = re.compile(r"^[a-zA-Z0-9@][a-zA-Z0-9_.@/+:\-]{0,240}$")
ECOSYSTEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._+\-/]{0,80}$")

ALLOWED_HOSTS = frozenset(
    {
        "services.nvd.nist.gov",
        "api.osv.dev",
        "api.first.org",
        "www.cisa.gov",
        "raw.githubusercontent.com",
        "api.github.com",
        "gitlab.com",
        "api.msrc.microsoft.com",
        "access.redhat.com",
        "ubuntu.com",
    }
)

_SENSITIVE_PARAMS = re.compile(
    r"((?:apikey|api_key|key|token|access_token|secret|client_secret)=)[^&\s]+",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\b(Bearer|token)\s+[A-Za-z0-9._\-+/=]+", re.IGNORECASE)


def normalize_cve(cve_id: str) -> str | None:
    value = cve_id.strip().upper()
    return value if CVE_RE.fullmatch(value) else None


def sanitize_keyword(query: str) -> str | None:
    value = query.strip()
    return value if SAFE_KEYWORD_RE.fullmatch(value) else None


def validate_package_name(name: str) -> str:
    value = name.strip()
    if not PACKAGE_RE.fullmatch(value):
        raise ValueError("Invalid package name")
    return value


def validate_ecosystem(ecosystem: str) -> str:
    value = ecosystem.strip()
    if not ECOSYSTEM_RE.fullmatch(value):
        raise ValueError("Invalid ecosystem")
    return value


def validate_intel_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Security intelligence requests must use https")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Blocked request to unauthorized host: {parsed.hostname}")
    return url


def sanitize_url_for_log(url: str) -> str:
    return _BEARER.sub(r"\1 ***REDACTED***", _SENSITIVE_PARAMS.sub(r"\1***REDACTED***", url))


def validate_ip_address(ip: str) -> str:
    addr = ipaddress.ip_address(ip.strip())
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        raise ValueError(f"Private/reserved IP not allowed: {ip}")
    return str(addr)


def validate_hash(hash_str: str) -> str | None:
    value = hash_str.strip().lower()
    if len(value) in (32, 40, 64) and all(c in "0123456789abcdef" for c in value):
        return value
    return None
