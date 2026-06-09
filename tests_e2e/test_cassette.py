"""obs-eval-3 (offline core): cassette format + redaction + deterministic replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests_e2e.cassette import (
    CASSETTE_VERSION,
    Cassette,
    CassetteMismatch,
    CassettePlayer,
    Interaction,
    redact_headers,
    redact_text,
    redacted_request,
    redacted_response,
)


def test_redact_text_strips_secret_values() -> None:
    text = "key=sk-abcdefABCDEF0123456789 and token Bearer abc.def-123"
    out = redact_text(text)
    assert "sk-abcdefABCDEF0123456789" not in out
    assert "Bearer abc.def-123" not in out
    assert "<redacted>" in out
    assert "key=" in out  # surrounding context preserved


def test_redact_headers_strips_auth_by_name() -> None:
    headers = redact_headers(
        {"Authorization": "Bearer secrettoken", "X-Api-Key": "sk-xxx", "Accept": "application/json"}
    )
    assert headers["Authorization"] == "<redacted>"
    assert headers["X-Api-Key"] == "<redacted>"
    assert headers["Accept"] == "application/json"


def test_recorded_request_redacts_before_storage() -> None:
    req = redacted_request(
        "POST",
        "https://api.example.com/v1/messages",
        {"authorization": "Bearer sk-realkey1234567890"},
        body='{"prompt": "hi", "leaked": "sk-anotherrealkey0987654321"}',
    )
    assert req.headers["authorization"] == "<redacted>"
    assert "sk-realkey1234567890" not in str(req.headers)
    assert "sk-anotherrealkey0987654321" not in req.body
    assert "<redacted>" in req.body


def test_cassette_roundtrip(tmp_path: Path) -> None:
    cassette = Cassette(
        interactions=[
            Interaction(
                request=redacted_request("POST", "https://api/x", {}, '{"q": 1}'),
                response=redacted_response(
                    200, {"content-type": "application/json"}, '{"ok": true}'
                ),
            )
        ]
    )
    path = tmp_path / "cassette.json"
    cassette.save(path)
    loaded = Cassette.load(path)
    assert loaded.version == CASSETTE_VERSION
    assert len(loaded.interactions) == 1
    assert loaded.interactions[0].response.body == '{"ok": true}'


def _cassette() -> Cassette:
    return Cassette(
        interactions=[
            Interaction(
                request=redacted_request("POST", "https://api/1", {}, ""),
                response=redacted_response(200, {}, "first"),
            ),
            Interaction(
                request=redacted_request("POST", "https://api/2", {}, ""),
                response=redacted_response(200, {}, "second"),
            ),
        ]
    )


def test_player_replays_in_order() -> None:
    player = CassettePlayer(_cassette())
    assert player.next_response(method="POST", url="https://api/1").body == "first"
    assert player.next_response(method="POST", url="https://api/2").body == "second"
    assert player.exhausted


def test_player_raises_when_exhausted() -> None:
    player = CassettePlayer(Cassette())
    with pytest.raises(CassetteMismatch, match="exhausted"):
        player.next_response(method="POST", url="https://api/extra")


def test_player_raises_on_method_mismatch() -> None:
    player = CassettePlayer(_cassette())
    with pytest.raises(CassetteMismatch, match="method mismatch"):
        player.next_response(method="GET", url="https://api/1")
