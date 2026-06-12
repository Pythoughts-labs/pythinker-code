"""Tests for telemetry.errors.report_handled_error."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import pythinker_code.telemetry as telemetry_mod
from pythinker_code.telemetry import set_context
from pythinker_code.telemetry.errors import report_handled_error


@pytest.fixture(autouse=True)
def _reset_telemetry_state():
    telemetry_mod._event_queue.clear()
    telemetry_mod._device_id = None
    telemetry_mod._session_id = None
    telemetry_mod._client_info = None
    telemetry_mod._session_started_sessions.clear()
    telemetry_mod._sink = None
    telemetry_mod._disabled = False
    yield
    telemetry_mod._event_queue.clear()
    telemetry_mod._device_id = None
    telemetry_mod._session_id = None
    telemetry_mod._client_info = None
    telemetry_mod._session_started_sessions.clear()
    telemetry_mod._sink = None
    telemetry_mod._disabled = False


def test_emits_track_event_with_site_and_exc_class():
    set_context(device_id="dev1", session_id="sess1")
    exc = ValueError("boom")
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception"):
        report_handled_error(exc, site="tool.read", tool="ReadFile")

    assert len(telemetry_mod._event_queue) == 1
    record = telemetry_mod._event_queue[0]
    assert record["event"] == "error"
    assert record["properties"]["site"] == "tool.read"
    assert record["properties"]["exc_class"] == "ValueError"
    assert record["properties"]["tool"] == "ReadFile"


def test_forwards_to_sentry():
    set_context(device_id="dev1", session_id="sess1")
    exc = RuntimeError("explode")
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception") as mock_capture:
        report_handled_error(exc, site="tool.write", tool="WriteFile")
    mock_capture.assert_called_once_with(exc)


def test_extra_attrs_pass_through():
    set_context(device_id="dev1", session_id="sess1")
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception"):
        report_handled_error(
            OSError("nope"),
            site="tool.shell.exec",
            tool="Shell",
            background=False,
            timeout_s=30,
        )
    record = telemetry_mod._event_queue[0]
    assert record["properties"]["background"] is False
    assert record["properties"]["timeout_s"] == 30


def test_track_failure_does_not_raise():
    """If track() somehow raises, the helper must swallow and still call Sentry."""
    set_context(device_id="dev1", session_id="sess1")
    with (
        patch("pythinker_code.telemetry.errors.track", side_effect=RuntimeError("track broke")),
        patch("pythinker_code.telemetry.errors._sentry.capture_exception") as mock_capture,
    ):
        report_handled_error(ValueError("x"), site="tool.read", tool="ReadFile")
    # Sentry path still ran
    mock_capture.assert_called_once()


def test_sentry_failure_does_not_raise():
    """If Sentry raises, the helper must swallow."""
    set_context(device_id="dev1", session_id="sess1")
    with patch(
        "pythinker_code.telemetry.errors._sentry.capture_exception",
        side_effect=RuntimeError("sentry broke"),
    ):
        # No assertion: just verify no exception escapes.
        report_handled_error(ValueError("x"), site="tool.read", tool="ReadFile")
    # Track path still ran
    assert len(telemetry_mod._event_queue) == 1


def test_disabled_telemetry_skips_track_but_still_calls_sentry():
    """When telemetry is disabled, track is a no-op; Sentry capture is still invoked
    because the Sentry SDK has its own opt-out path (PYTHINKER_DISABLE_TELEMETRY
    short-circuits inside sentry.init, not at capture time)."""
    telemetry_mod._disabled = True
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception") as mock_capture:
        report_handled_error(ValueError("x"), site="tool.read", tool="ReadFile")
    assert len(telemetry_mod._event_queue) == 0
    mock_capture.assert_called_once()


def test_no_tool_argument_is_optional():
    set_context(device_id="dev1", session_id="sess1")
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception"):
        report_handled_error(KeyError("missing"), site="auth.oauth.refresh")
    record = telemetry_mod._event_queue[0]
    assert "tool" not in record["properties"]
    assert record["properties"]["site"] == "auth.oauth.refresh"
    assert record["properties"]["exc_class"] == "KeyError"


# ---------------------------------------------------------------------------
# Ring-buffer tests for /report-error
# ---------------------------------------------------------------------------

from pythinker_code.telemetry.errors import (  # noqa: E402
    _RECENT_BUFFER_SIZE,
    clear_recent_errors,
    recent_errors,
)


@pytest.fixture(autouse=True)
def _reset_recent_buffer():
    clear_recent_errors()
    yield
    clear_recent_errors()


def test_recent_errors_records_each_call():
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception"):
        report_handled_error(ValueError("a"), site="tool.read", tool="ReadFile")
        report_handled_error(RuntimeError("b"), site="auth.oauth.refresh")
    errs = recent_errors()
    assert len(errs) == 2
    assert errs[0].site == "tool.read"
    assert errs[0].exc_class == "ValueError"
    assert errs[0].tool == "ReadFile"
    assert errs[1].site == "auth.oauth.refresh"
    assert errs[1].tool is None


def test_recent_errors_truncates_long_messages():
    long_msg = "x" * 1000
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception"):
        report_handled_error(ValueError(long_msg), site="tool.read")
    err = recent_errors()[0]
    assert len(err.message) == 200
    assert err.message == "x" * 200


def test_recent_errors_buffer_caps_at_max():
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception"):
        for i in range(_RECENT_BUFFER_SIZE + 3):
            report_handled_error(ValueError(f"e{i}"), site=f"tool.s{i}")
    errs = recent_errors()
    assert len(errs) == _RECENT_BUFFER_SIZE
    # Oldest entries dropped: first remaining is e3 (3 + buffer = total entries).
    assert errs[0].message == "e3"
    assert errs[-1].message == f"e{_RECENT_BUFFER_SIZE + 2}"


def test_clear_recent_errors():
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception"):
        report_handled_error(ValueError("x"), site="tool.read")
    assert len(recent_errors()) == 1
    clear_recent_errors()
    assert recent_errors() == []


# ---------------------------------------------------------------------------
# Expected-error classification + Sentry suppression
# ---------------------------------------------------------------------------

import socket  # noqa: E402

from pythinker_code.telemetry.errors import is_expected_error  # noqa: E402


class _StatusError(Exception):
    """Duck-typed provider error carrying an HTTP status code."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, True),
        (403, True),
        (408, True),
        (429, True),
        (500, True),
        (503, True),
        (400, False),
        (404, False),
        (422, False),
    ],
)
def test_is_expected_error_http_statuses(status: int, expected: bool):
    assert is_expected_error(_StatusError(status)) is expected


def test_is_expected_error_environmental_classes():
    assert is_expected_error(TimeoutError())
    assert is_expected_error(ConnectionResetError())
    assert is_expected_error(socket.gaierror(8, "nodename nor servname provided"))


def test_is_expected_error_oauth():
    from pythinker_code.auth.oauth import OAuthError

    assert is_expected_error(OAuthError("Invalid callback state."))


def test_is_expected_error_mcp_method_not_found_only():
    from mcp.shared.exceptions import McpError
    from mcp.types import INTERNAL_ERROR, METHOD_NOT_FOUND, ErrorData

    assert is_expected_error(McpError(ErrorData(code=METHOD_NOT_FOUND, message="Method not found")))
    assert not is_expected_error(McpError(ErrorData(code=INTERNAL_ERROR, message="boom")))


def test_is_expected_error_walks_cause_chain():
    outer = RuntimeError("retries exhausted")
    outer.__cause__ = _StatusError(429)
    assert is_expected_error(outer)


def test_is_expected_error_plain_bug_is_not_expected():
    assert not is_expected_error(ValueError("boom"))
    assert not is_expected_error(OSError(8, "Exec format error"))


def test_expected_error_skips_sentry_but_still_tracks_and_buffers():
    set_context(device_id="dev1", session_id="sess1")
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception") as mock_capture:
        report_handled_error(_StatusError(401), site="soul.step.error")
    mock_capture.assert_not_called()
    record = telemetry_mod._event_queue[0]
    assert record["properties"]["expected"] is True
    assert len(recent_errors()) == 1


def test_unexpected_error_is_marked_and_sent_to_sentry():
    set_context(device_id="dev1", session_id="sess1")
    with patch("pythinker_code.telemetry.errors._sentry.capture_exception") as mock_capture:
        report_handled_error(ValueError("boom"), site="tool.read")
    mock_capture.assert_called_once()
    assert telemetry_mod._event_queue[0]["properties"]["expected"] is False
