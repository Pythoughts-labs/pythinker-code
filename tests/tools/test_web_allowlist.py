"""Tests for the web domain allowlist helper."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pythinker_code.config import WebConfig
from pythinker_code.tools.web._allowlist import host_in_allowlist


@pytest.mark.parametrize(
    ("host", "allowed", "expected"),
    [
        # None / empty allowlist is unrestricted.
        ("anything.com", None, True),
        ("anything.com", [], True),
        ("anything.com", ["  ", "."], True),  # entries normalize to empty
        # Exact match.
        ("example.com", ["example.com"], True),
        # Subdomain match.
        ("docs.example.com", ["example.com"], True),
        ("a.b.example.com", ["example.com"], True),
        # Lookalike must NOT match.
        ("notexample.com", ["example.com"], False),
        ("example.com.evil.com", ["example.com"], False),
        # Different domain.
        ("other.org", ["example.com"], False),
        # Case-insensitivity and normalization (leading dot, whitespace).
        ("DOCS.Example.COM", ["  .Example.com "], True),
        # Trailing-dot FQDN host.
        ("docs.example.com.", ["example.com"], True),
        # Multiple entries: match any.
        ("foo.org", ["example.com", "foo.org"], True),
        # Empty / None host with a non-empty allowlist is rejected.
        ("", ["example.com"], False),
        (None, ["example.com"], False),
    ],
)
def test_host_in_allowlist(host: str | None, allowed: list[str] | None, expected: bool) -> None:
    assert host_in_allowlist(host, allowed) is expected


def test_web_config_accepts_bare_hostnames() -> None:
    cfg = WebConfig(allowed_domains=["example.com", "docs.python.org"])
    assert cfg.allowed_domains == ["example.com", "docs.python.org"]


@pytest.mark.parametrize(
    "bad_entry",
    [
        "https://example.com",  # scheme
        "example.com/path",  # path
        "example.com:8080",  # port
        "two words.com",  # whitespace
    ],
)
def test_web_config_rejects_malformed_entries(bad_entry: str) -> None:
    with pytest.raises(ValidationError):
        WebConfig(allowed_domains=[bad_entry])
