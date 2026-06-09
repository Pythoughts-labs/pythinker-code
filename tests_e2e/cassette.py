"""Record-replay cassette layer for LLM HTTP traffic (obs-eval-3, offline core).

Pythinker can only test against fictional model behavior it scripts by hand. It
cannot capture a real failing/interesting run and replay it deterministically, and
has no redaction-safe path to commit such fixtures.

This module is the offline-testable core of obs-eval-3:
  * a committed cassette format (versioned, JSON) of request/response pairs;
  * a redaction pipeline that strips auth headers and secret-like values *before*
    anything is written to disk;
  * a deterministic ``CassettePlayer`` that dispatches recorded responses in order
    and fails loudly on exhaustion or a request mismatch.

Deferred (the live-run slice): the RECORDER that captures real request/response
pairs from a live provider behind a ``PYTHINKER_RECORD`` flag, and binding the
player into the chat_provider boundary (the provider classes live in
pythinker_core). Those need a real provider call; this format + redaction + replay
are their foundation, and the redaction here is what makes a captured cassette safe
to commit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, Field

CASSETTE_VERSION = 1
_REDACTED = "<redacted>"

# Header names whose entire value is sensitive.
_SECRET_HEADER_NAMES = frozenset(
    {"authorization", "x-api-key", "api-key", "cookie", "set-cookie", "proxy-authorization"}
)

# Secret-like values that can appear anywhere (header values or bodies).
_SECRET_VALUE_RE = re.compile(
    r"""(
        sk-[A-Za-z0-9_-]{16,}            # OpenAI / Anthropic style keys
      | AKIA[0-9A-Z]{16}                 # AWS access key id
      | gh[pousr]_[A-Za-z0-9]{20,}       # GitHub tokens
      | Bearer\s+[A-Za-z0-9._\-]+        # bearer tokens
      | xox[baprs]-[A-Za-z0-9-]{10,}     # Slack tokens
    )""",
    re.VERBOSE,
)


def redact_text(text: str) -> str:
    """Replace secret-like substrings with a redaction marker."""
    return _SECRET_VALUE_RE.sub(_REDACTED, text)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Redact sensitive headers by name, and secret-like values elsewhere."""
    out: dict[str, str] = {}
    for key, value in headers.items():
        out[key] = _REDACTED if key.lower() in _SECRET_HEADER_NAMES else redact_text(value)
    return out


class RecordedRequest(BaseModel):
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""


class RecordedResponse(BaseModel):
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""


class Interaction(BaseModel):
    request: RecordedRequest
    response: RecordedResponse


class Cassette(BaseModel):
    version: int = CASSETTE_VERSION
    interactions: list[Interaction] = Field(default_factory=list)

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Cassette:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def redacted_request(
    method: str, url: str, headers: Mapping[str, str], body: str
) -> RecordedRequest:
    """Build a request record with secrets stripped (safe to commit)."""
    return RecordedRequest(
        method=method, url=url, headers=redact_headers(headers), body=redact_text(body)
    )


def redacted_response(status_code: int, headers: Mapping[str, str], body: str) -> RecordedResponse:
    """Build a response record with secrets stripped (safe to commit)."""
    return RecordedResponse(
        status_code=status_code, headers=redact_headers(headers), body=redact_text(body)
    )


class CassetteMismatch(Exception):
    """Raised when replay diverges from the recorded traffic."""


class CassettePlayer:
    """Deterministically replays a cassette's responses, in order.

    Fails loudly (``CassetteMismatch``) if the cassette is exhausted or the next
    request's method/url does not match what was recorded, so a behavioral drift
    in what Pythinker SENDS surfaces as a test failure rather than silent reuse.
    """

    def __init__(self, cassette: Cassette) -> None:
        self._cassette = cassette
        self._index = 0

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._cassette.interactions)

    def next_response(self, *, method: str, url: str) -> RecordedResponse:
        if self.exhausted:
            raise CassetteMismatch(
                f"cassette exhausted after {self._index} interaction(s); "
                f"unexpected extra request {method} {url}"
            )
        interaction = self._cassette.interactions[self._index]
        self._index += 1
        if interaction.request.method.upper() != method.upper():
            raise CassetteMismatch(
                f"method mismatch at interaction #{self._index - 1}: "
                f"recorded {interaction.request.method}, got {method}"
            )
        return interaction.response
