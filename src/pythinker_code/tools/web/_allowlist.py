"""Domain allowlist matching shared by the web fetch and search tools."""

from __future__ import annotations


def _normalize(entry: str) -> str:
    return entry.strip().lstrip(".").lower()


def host_in_allowlist(host: str | None, allowed: list[str] | None) -> bool:
    """Return whether *host* is permitted by the *allowed* domain list.

    A ``None`` or empty allowlist imposes no restriction (returns ``True``),
    preserving unconfigured behavior. Otherwise a host matches when it equals an
    allowlist entry or is a subdomain of one. Matching is label-aware and
    case-insensitive: ``example.com`` matches ``example.com`` and
    ``docs.example.com`` but not ``notexample.com``.
    """
    entries = [normalized for entry in (allowed or []) if (normalized := _normalize(entry))]
    if not entries:
        return True

    host = (host or "").strip().rstrip(".").lower()
    if not host:
        return False

    return any(host == entry or host.endswith(f".{entry}") for entry in entries)
