"""Tests for the telemetry system."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import pythinker_code.telemetry as telemetry_mod
from pythinker_code.telemetry import attach_sink, disable, set_context, track
from pythinker_code.telemetry.sink import EventSink


@pytest.fixture(autouse=True)
def _reset_telemetry_state():
    """Reset telemetry module state before each test."""
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


class TestTrack:
    def test_track_queues_event_before_sink(self):
        """Events are queued in memory before sink is attached."""
        track("test_event", foo=True, bar=42)
        assert len(telemetry_mod._event_queue) == 1
        event = telemetry_mod._event_queue[0]
        assert event["event"] == "test_event"
        assert event["properties"] == {"foo": True, "bar": 42}
        assert event["timestamp"] > 0

    def test_track_includes_context_ids(self):
        """Events include device_id and session_id."""
        set_context(device_id="dev123", session_id="sess456")
        track("test_event")
        event = telemetry_mod._event_queue[0]
        assert event["device_id"] == "dev123"
        assert event["session_id"] == "sess456"

    def test_track_forwards_to_sink(self):
        """Events are forwarded to sink when attached."""
        mock_sink = MagicMock(spec=EventSink)
        attach_sink(mock_sink)
        track("test_event", key=1)
        mock_sink.accept.assert_called_once()
        event = mock_sink.accept.call_args[0][0]
        assert event["event"] == "test_event"
        assert event["properties"] == {"key": 1}

    def test_track_disabled_drops_events(self):
        """Events are silently dropped when disabled."""
        disable()
        track("test_event")
        assert len(telemetry_mod._event_queue) == 0

    def test_attach_sink_drains_queue(self):
        """Attaching sink drains queued events."""
        track("event1")
        track("event2")
        assert len(telemetry_mod._event_queue) == 2

        mock_sink = MagicMock(spec=EventSink)
        attach_sink(mock_sink)
        assert len(telemetry_mod._event_queue) == 0
        assert mock_sink.accept.call_count == 2

    def test_track_empty_properties(self):
        """Events with no properties have empty dict."""
        track("test_event")
        event = telemetry_mod._event_queue[0]
        assert event["properties"] == {}

    def test_track_string_properties(self):
        """String properties are allowed for enum-like values."""
        track("test_event", command="model", mode="agent")
        event = telemetry_mod._event_queue[0]
        assert event["properties"]["command"] == "model"
        assert event["properties"]["mode"] == "agent"

    def test_queue_max_size(self):
        """Queue drops oldest events when exceeding MAX_QUEUE_SIZE."""
        for i in range(telemetry_mod._MAX_QUEUE_SIZE + 100):
            track(f"event_{i}")
        assert len(telemetry_mod._event_queue) == telemetry_mod._MAX_QUEUE_SIZE
        # Oldest events should be dropped; newest should remain
        assert (
            telemetry_mod._event_queue[-1]["event"] == f"event_{telemetry_mod._MAX_QUEUE_SIZE + 99}"
        )
        assert telemetry_mod._event_queue[0]["event"] == "event_100"

    def test_disable_clears_sink_buffer(self):
        """Disabling telemetry clears the sink buffer."""
        mock_sink = MagicMock(spec=EventSink)
        attach_sink(mock_sink)
        track("event_before_disable")
        disable()
        mock_sink.clear_buffer.assert_called_once()
        # Further events should be dropped
        track("event_after_disable")
        # accept should have been called once (before disable), not twice
        assert mock_sink.accept.call_count == 1

    def test_attach_sink_flushes_previous_sink(self):
        """Replacing the global sink (e.g. multi-session ACP) must flush the
        previous sink so its buffered events aren't silently orphaned.
        """
        first_sink = MagicMock(spec=EventSink)
        attach_sink(first_sink)
        second_sink = MagicMock(spec=EventSink)
        attach_sink(second_sink)
        first_sink.flush_sync.assert_called_once()
        # Second attach does not re-flush itself
        second_sink.flush_sync.assert_not_called()

    def test_attach_same_sink_twice_does_not_flush(self):
        """Re-attaching the same sink is a no-op (no self-flush)."""
        sink = MagicMock(spec=EventSink)
        attach_sink(sink)
        attach_sink(sink)
        sink.flush_sync.assert_not_called()

    def test_event_id_is_hex_string(self):
        """Every event has a unique event_id (hex string)."""
        track("test_event")
        event = telemetry_mod._event_queue[0]
        assert "event_id" in event
        assert isinstance(event["event_id"], str)
        assert len(event["event_id"]) == 32  # uuid4 hex

    def test_event_ids_are_unique(self):
        """Each event gets a distinct event_id."""
        track("event_a")
        track("event_b")
        ids = [e["event_id"] for e in telemetry_mod._event_queue]
        assert ids[0] != ids[1]

    def test_backfill_device_and_session_id_on_attach(self):
        """Events tracked before set_context() get backfilled on attach_sink()."""
        # Track before context is set — device_id/session_id are None
        track("early_event")
        assert telemetry_mod._event_queue[0]["device_id"] is None
        assert telemetry_mod._event_queue[0]["session_id"] is None

        # Now set context and attach sink
        set_context(device_id="dev-backfill", session_id="sess-backfill")
        mock_sink = MagicMock(spec=EventSink)
        attach_sink(mock_sink)

        # The event forwarded to sink should have backfilled ids
        event = mock_sink.accept.call_args[0][0]
        assert event["device_id"] == "dev-backfill"
        assert event["session_id"] == "sess-backfill"


class TestEventSink:
    """EventSink emits flattened events to the OTel logs pipeline."""

    def _captured(self, sink: EventSink) -> list[dict[str, Any]]:
        """Run flush_sync with otel.emit_log mocked, return captured args."""
        captured: list[dict[str, Any]] = []

        def _capture(
            *,
            name: str,
            attributes: dict[str, Any],
            severity: str = "info",
            timestamp_ns: int | None = None,
        ):
            captured.append(
                {"name": name, "attrs": attributes, "severity": severity, "ts_ns": timestamp_ns}
            )

        with patch("pythinker_code.telemetry.otel.emit_log", side_effect=_capture):
            sink.flush_sync()
        return captured

    def test_accept_enriches_context(self):
        """Events are enriched with version/platform context before emission."""
        sink = EventSink(version="1.0.0", model="pythinker-ai")
        event: dict[str, Any] = {"event": "test", "timestamp": time.time(), "properties": {}}
        sink.accept(event)
        # accept() must not mutate the original event dict
        assert "context" not in event

        emissions = self._captured(sink)
        assert len(emissions) == 1
        attrs = emissions[0]["attrs"]
        assert attrs["context.version"] == "1.0.0"
        assert attrs["context.model"] == "pythinker-ai"
        assert "context.platform" in attrs
        assert "context.ui_mode" in attrs
        assert "context.python_version" in attrs
        assert "context.os_version" in attrs
        assert isinstance(attrs["context.ci"], bool)
        assert "context.locale" in attrs
        assert "context.terminal" in attrs

    def test_flush_sync_emits_event(self):
        """Sync flush forwards every accepted event to OTel."""
        sink = EventSink(version="1.0.0")
        sink.accept({"event": "test", "timestamp": 1.0, "properties": {}})
        emissions = self._captured(sink)
        assert len(emissions) == 1
        assert emissions[0]["name"] == "test"

    def test_flush_sync_noop_when_empty(self):
        """Sync flush is a no-op when buffer is empty."""
        sink = EventSink(version="1.0.0")
        emissions = self._captured(sink)
        assert emissions == []

    def test_accept_includes_ui_mode(self):
        sink = EventSink(version="1.0.0", ui_mode="print")
        sink.accept({"event": "test", "timestamp": 1.0, "properties": {}})
        emissions = self._captured(sink)
        assert emissions[0]["attrs"]["context.ui_mode"] == "print"

    def test_accept_default_ui_mode_is_shell(self):
        sink = EventSink(version="1.0.0")
        sink.accept({"event": "test", "timestamp": 1.0, "properties": {}})
        emissions = self._captured(sink)
        assert emissions[0]["attrs"]["context.ui_mode"] == "shell"

    def test_event_name_passes_through_as_log_body(self):
        sink = EventSink(version="1.0.0")
        sink.accept({"event": "session_started", "timestamp": 1.0, "properties": {"x": 1}})
        emissions = self._captured(sink)
        assert emissions[0]["name"] == "session_started"
        # property keys are flattened
        assert emissions[0]["attrs"].get("property.x") == 1

    def test_timestamp_converted_to_nanos(self):
        sink = EventSink(version="1.0.0")
        sink.accept({"event": "test", "timestamp": 1.5, "properties": {}})
        emissions = self._captured(sink)
        assert emissions[0]["ts_ns"] == 1_500_000_000

    def test_non_primitive_attribute_drops_event(self):
        """Schema violations drop the offending event without raising."""
        sink = EventSink(version="1.0.0")
        # Nested dict in properties is rejected by _flatten_event.
        sink.accept({"event": "good", "timestamp": 1.0, "properties": {}})
        sink.accept({"event": "bad", "timestamp": 1.0, "properties": {"nested": {"x": 1}}})
        emissions = self._captured(sink)
        # Only the good event makes it through.
        names = [e["name"] for e in emissions]
        assert "good" in names
        assert "bad" not in names


class TestFlatten:
    """The _flatten_event helper that powers OTel attribute mapping."""

    def test_properties_become_property_dot_keys(self):
        from pythinker_code.telemetry.sink import _flatten_event

        out = _flatten_event({"event": "x", "timestamp": 1.0, "properties": {"foo": "bar", "n": 3}})
        assert out["property.foo"] == "bar"
        assert out["property.n"] == 3

    def test_context_becomes_context_dot_keys(self):
        from pythinker_code.telemetry.sink import _flatten_event

        out = _flatten_event({"event": "x", "context": {"version": "1.0.0", "ci": False}})
        assert out["context.version"] == "1.0.0"
        assert out["context.ci"] is False

    def test_top_level_fields_pass_through(self):
        from pythinker_code.telemetry.sink import _flatten_event

        out = _flatten_event({"event": "x", "timestamp": 1.0, "device_id": "abc"})
        assert out["event"] == "x"
        assert out["timestamp"] == 1.0
        assert out["device_id"] == "abc"

    def test_nested_dict_property_raises_typeerror(self):
        from pythinker_code.telemetry.sink import _flatten_event

        with pytest.raises(TypeError):
            _flatten_event({"event": "x", "properties": {"nested": {"y": 1}}})

    def test_list_property_raises_typeerror(self):
        from pythinker_code.telemetry.sink import _flatten_event

        with pytest.raises(TypeError):
            _flatten_event({"event": "x", "properties": {"items": [1, 2, 3]}})


class TestErrorSeverity:
    """Error-like events are emitted at ERROR/WARN severity with canonical
    ``error.*`` attributes, so SigNoz dashboards can find and group them."""

    def _captured(self, sink: EventSink) -> list[dict[str, Any]]:
        captured: list[dict[str, Any]] = []

        def _capture(
            *,
            name: str,
            attributes: dict[str, Any],
            severity: str = "info",
            timestamp_ns: int | None = None,
        ):
            captured.append({"name": name, "attrs": attributes, "severity": severity})

        with patch("pythinker_code.telemetry.otel.emit_log", side_effect=_capture):
            sink.flush_sync()
        return captured

    def test_handled_error_event_is_error_severity_with_canonical_attrs(self):
        sink = EventSink(version="1.0.0")
        sink.accept(
            {
                "event": "error",
                "timestamp": 1.0,
                "properties": {"site": "tool.read", "exc_class": "ValueError", "expected": False},
            }
        )
        emission = self._captured(sink)[0]
        assert emission["severity"] == "error"
        attrs = emission["attrs"]
        # Canonical keys derived from exc_class (handled errors don't set error_type).
        assert attrs["error.type"] == "ValueError"
        assert attrs["error.site"] == "tool.read"
        assert attrs["error.expected"] is False
        assert attrs["error.kind"] == "error"
        # Original property.* values are preserved untouched.
        assert attrs["property.exc_class"] == "ValueError"

    def test_crash_event_canonical_type_from_error_type_key(self):
        sink = EventSink(version="1.0.0")
        sink.accept(
            {
                "event": "crash",
                "timestamp": 1.0,
                "properties": {"error_type": "RuntimeError", "where": "startup"},
            }
        )
        emission = self._captured(sink)[0]
        assert emission["severity"] == "error"
        assert emission["attrs"]["error.type"] == "RuntimeError"
        assert emission["attrs"]["error.kind"] == "crash"

    def test_api_error_event_is_error_severity(self):
        sink = EventSink(version="1.0.0")
        sink.accept(
            {
                "event": "api_error",
                "timestamp": 1.0,
                "properties": {"error_type": "rate_limit", "status_code": 429},
            }
        )
        emission = self._captured(sink)[0]
        assert emission["severity"] == "error"
        assert emission["attrs"]["error.type"] == "rate_limit"

    def test_session_load_failed_is_warning(self):
        sink = EventSink(version="1.0.0")
        sink.accept(
            {"event": "session_load_failed", "timestamp": 1.0, "properties": {"reason": "OSError"}}
        )
        emission = self._captured(sink)[0]
        assert emission["severity"] == "warning"
        # Not in the error set → no canonical error.* attributes.
        assert "error.type" not in emission["attrs"]

    def test_regular_event_is_info_without_error_attrs(self):
        sink = EventSink(version="1.0.0")
        sink.accept({"event": "tool_call", "timestamp": 1.0, "properties": {"tool": "ReadFile"}})
        emission = self._captured(sink)[0]
        assert emission["severity"] == "info"
        assert not any(k.startswith("error.") for k in emission["attrs"])


class TestCrashSafeFlush:
    """flush_sync() drains the pre-sink event queue so a startup crash (before
    attach_sink) still reaches SigNoz."""

    def test_flush_sync_drains_event_queue_when_no_sink(self):
        set_context(device_id="dev1", session_id="sess1")
        track("crash", error_type="RuntimeError", where="startup")
        assert len(telemetry_mod._event_queue) == 1
        assert telemetry_mod._sink is None

        captured: list[dict[str, Any]] = []

        def _capture(*, name: str, attributes: dict[str, Any], severity: str = "info", **_):
            captured.append({"name": name, "severity": severity, "attrs": attributes})

        with patch("pythinker_code.telemetry.otel.emit_log", side_effect=_capture):
            telemetry_mod.flush_sync()

        assert len(captured) == 1
        assert captured[0]["name"] == "crash"
        assert captured[0]["severity"] == "error"
        assert captured[0]["attrs"]["error.type"] == "RuntimeError"
        # Queue drained so a second flush is a no-op.
        assert len(telemetry_mod._event_queue) == 0

    def test_flush_sync_no_sink_empty_queue_is_noop(self):
        captured: list[dict[str, Any]] = []

        def _capture(**kwargs):
            captured.append(kwargs)

        with patch("pythinker_code.telemetry.otel.emit_log", side_effect=_capture):
            telemetry_mod.flush_sync()
        assert captured == []

    def test_flush_sync_retains_queue_when_emit_raises(self):
        """A failed crash-safe emit must not drop the buffered events, so the
        later vendor-SDK flush (or a retry) can still send them."""
        set_context(device_id="dev1", session_id="sess1")
        track("crash", error_type="RuntimeError", where="startup")
        assert len(telemetry_mod._event_queue) == 1

        with patch(
            "pythinker_code.telemetry.sink.emit_events_to_otel",
            side_effect=RuntimeError("boom"),
        ):
            telemetry_mod.flush_sync()

        # Emit failed, so the queue is left intact rather than silently cleared.
        assert len(telemetry_mod._event_queue) == 1
