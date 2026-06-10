"""Tests for session error recovery in process.py and sessions.py.

Verifies that _in_flight_prompt_ids is properly cleared on errors so
that sessions don't get stuck in a permanent "busy" state.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from pythinker_code.web.api.sessions import _read_wire_lines
from pythinker_code.web.models import SessionStatus
from pythinker_code.web.runner.process import PythinkerCLIRunner, SessionProcess

# ---------------------------------------------------------------------------
# Tests: SessionProcess.clear_in_flight
# ---------------------------------------------------------------------------


def test_clear_in_flight_resets_is_busy() -> None:
    """clear_in_flight should empty _in_flight_prompt_ids so is_busy is False."""
    sp = SessionProcess(uuid4())
    sp._in_flight_prompt_ids.add("prompt-1")
    sp._in_flight_prompt_ids.add("prompt-2")

    assert sp.is_busy is True

    sp.clear_in_flight()

    assert sp.is_busy is False
    assert len(sp._in_flight_prompt_ids) == 0


# ---------------------------------------------------------------------------
# Tests: _read_loop clears in-flight on unexpected exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_loop_clears_in_flight_on_exception() -> None:
    """When _read_loop encounters a non-EOF, non-CancelledError exception,
    it should clear _in_flight_prompt_ids and emit an error status.
    """
    sp = SessionProcess(uuid4())
    sp._in_flight_prompt_ids.add("prompt-in-flight")
    assert sp.is_busy is True

    # Create a mock process whose stdout has one line then EOF
    mock_stdout = asyncio.StreamReader()
    mock_stdout.feed_data(b"not-valid-json\n")
    mock_stdout.feed_eof()

    mock_stderr = asyncio.StreamReader()
    mock_stderr.feed_data(b"mock stderr")
    mock_stderr.feed_eof()

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = None

    sp._process = mock_process

    # _broadcast raises on the first call (the stdout line),
    # succeeds on subsequent calls (_emit_status broadcast).
    call_count = 0

    async def failing_then_ok_broadcast(msg: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("broadcast failed")

    sp._broadcast = failing_then_ok_broadcast  # type: ignore[assignment]

    await sp._read_loop()

    assert sp.is_busy is False
    assert sp.status.state == "error"
    assert sp.status.reason == "read_loop_error"


# ---------------------------------------------------------------------------
# Tests: EOF path clears in-flight before broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_loop_eof_clears_in_flight_before_broadcast() -> None:
    """On worker process EOF, _in_flight_prompt_ids should be cleared
    before _broadcast is called, so that is_busy is already False when
    the frontend reacts to the error.
    """
    sp = SessionProcess(uuid4())
    sp._in_flight_prompt_ids.add("prompt-in-flight")

    # Track is_busy at the time broadcast is called
    busy_at_broadcast: list[bool] = []

    async def tracking_broadcast(msg: str) -> None:
        busy_at_broadcast.append(sp.is_busy)

    sp._broadcast = tracking_broadcast  # type: ignore[assignment]

    # Create a mock process that immediately returns EOF
    mock_stdout = asyncio.StreamReader()
    mock_stdout.feed_eof()

    mock_stderr = asyncio.StreamReader()
    mock_stderr.feed_data(b"worker crashed")
    mock_stderr.feed_eof()

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 1

    sp._process = mock_process
    sp._expecting_exit = False

    await sp._read_loop()

    # At the time broadcast was called, is_busy should already be False
    assert busy_at_broadcast[0] is False
    assert sp.status.state == "error"


# ---------------------------------------------------------------------------
# Tests: error state allows recovery with new prompt
# ---------------------------------------------------------------------------


def test_session_in_error_state_clears_stale_ids_on_new_prompt() -> None:
    """When a session is in error state and is_busy is True (stale IDs),
    clear_in_flight should be callable to recover the session.
    This tests the building block used by the sessions.py WebSocket handler.
    """
    session_id = uuid4()
    sp = SessionProcess(session_id)

    # Simulate: session errored out but _in_flight_prompt_ids was not cleared
    sp._in_flight_prompt_ids.add("stale-prompt")
    sp._status = SessionStatus(
        session_id=session_id,
        state="error",
        seq=1,
        worker_id=None,
        reason="process_exit",
        detail=None,
        updated_at=datetime.now(UTC),
    )

    assert sp.is_busy is True
    assert sp.status.state == "error"

    # The sessions.py handler checks this condition and calls clear_in_flight
    if sp.status.state == "error" and sp.is_busy:
        sp.clear_in_flight()

    assert sp.is_busy is False


# ---------------------------------------------------------------------------
# Tests: _read_loop decodes non-UTF-8 stderr with errors='replace'
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_loop_handles_non_utf8_stderr() -> None:
    """When the worker crashes with non-UTF-8 bytes in stderr,
    _read_loop must NOT raise UnicodeDecodeError. The status must be
    'error' with reason 'process_exit', not the fallback 'read_loop_error'.
    """
    sp = SessionProcess(uuid4())
    sp._in_flight_prompt_ids.add("prompt-in-flight")

    broadcasts: list[str] = []

    async def recording_broadcast(msg: str) -> None:
        broadcasts.append(msg)

    sp._broadcast = recording_broadcast  # type: ignore[assignment]

    # stdout immediately at EOF; stderr contains invalid UTF-8 bytes
    mock_stdout = asyncio.StreamReader()
    mock_stdout.feed_eof()

    mock_stderr = asyncio.StreamReader()
    mock_stderr.feed_data(b"crash \xff\xfe dump")
    mock_stderr.feed_eof()

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout
    mock_process.stderr = mock_stderr
    mock_process.returncode = 1

    sp._process = mock_process
    sp._expecting_exit = False

    await sp._read_loop()

    # Must reach the process_exit path, not the generic read_loop_error fallback
    assert sp.status.state == "error"
    assert sp.status.reason == "process_exit", (
        f"Expected reason='process_exit' but got '{sp.status.reason}'. "
        "A UnicodeDecodeError likely caused the fallback path to fire."
    )
    # At least one broadcast (the JSONRPCErrorResponse) must have been emitted
    assert broadcasts, "No broadcasts were emitted; the process_exit path was not reached"


# ---------------------------------------------------------------------------
# Tests: watermark caps replay so late joiners don't see duplicated events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_websocket_watermark_caps_replay(tmp_path: Path) -> None:
    """add_websocket_and_begin_replay returns the wire.jsonl byte size at
    attach time; _read_wire_lines(wire_file, watermark) must return only
    records written before the watermark and ignore any appended afterward.
    """
    wire_file = tmp_path / "wire.jsonl"

    # Write N=3 records to wire.jsonl using the real wire message format.
    # Each record has a "message" dict with "type" and "payload" keys so that
    # _read_wire_lines can deserialize them via deserialize_wire_message.
    def _make_turn_begin(text: str) -> str:
        return json.dumps({"message": {"type": "TurnBegin", "payload": {"user_input": text}}})

    records = [_make_turn_begin(f"msg{i}") for i in range(3)]
    wire_file.write_text("\n".join(records) + "\n", encoding="utf-8")

    # Attach a mock WebSocket; capture the watermark returned
    sp = SessionProcess(uuid4())
    mock_ws = MagicMock()

    watermark = await sp.add_websocket_and_begin_replay(mock_ws, wire_file)

    # Watermark should equal the current byte size of wire.jsonl
    assert watermark is not None
    assert watermark == wire_file.stat().st_size
    assert watermark > 0

    # Now append an (N+1)th record AFTER the watermark was captured
    extra_line = _make_turn_begin("extra_after_watermark")
    with open(wire_file, "a", encoding="utf-8") as f:
        f.write(extra_line + "\n")

    # _read_wire_lines with the watermark must return exactly the first N records
    lines = _read_wire_lines(wire_file, watermark)

    # The extra record was written after watermark — must not appear
    assert all("extra_after_watermark" not in line for line in lines), (
        f"Extra record leaked into replay: {lines}"
    )

    # Without a watermark cap, all N+1 records would be returned (verify assumption)
    all_lines = _read_wire_lines(wire_file, None)
    assert len(all_lines) > len(lines), "Expected extra record visible without watermark"


@pytest.mark.asyncio
async def test_add_websocket_watermark_stat_failure_replays_everything(
    tmp_path: Path,
) -> None:
    """A failed stat must yield watermark=None (replay the whole file), not 0.

    _read_wire_lines(wire_file, 0) returns zero lines, so a transient stat
    error right after has_history succeeded would silently hand the client an
    empty history; bounded duplicates beat total history loss.
    """
    wire_file = tmp_path / "wire.jsonl"
    record = json.dumps({"message": {"type": "TurnBegin", "payload": {"user_input": "m"}}})
    wire_file.write_text(record + "\n", encoding="utf-8")

    sp = SessionProcess(uuid4())
    mock_ws = MagicMock()

    # Point the attach at a path whose stat raises.
    missing = tmp_path / "gone.jsonl"
    watermark = await sp.add_websocket_and_begin_replay(mock_ws, missing)

    assert watermark is None
    # None flows into _read_wire_lines as "no cap" — the full history survives.
    assert len(_read_wire_lines(wire_file, watermark)) == 1
    # The wrong sentinel (0) would have dropped everything.
    assert _read_wire_lines(wire_file, 0) == []


# ---------------------------------------------------------------------------
# Tests: PythinkerCLIRunner.remove_session drops the registry entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_remove_session_drops_entry() -> None:
    """remove_session should stop the process and remove it from the registry.

    Before the fix: PythinkerCLIRunner has no remove_session attribute
    (AttributeError). After: get_session returns None and stop was awaited.
    """
    runner = PythinkerCLIRunner()
    sid = uuid4()

    sp = await runner.get_or_create_session(sid)
    assert runner.get_session(sid) is sp

    # Monkeypatch stop to an async no-op so no real subprocess is touched.
    stop_called = False

    async def _fake_stop() -> None:
        nonlocal stop_called
        stop_called = True

    sp.stop = _fake_stop  # type: ignore[method-assign]

    await runner.remove_session(sid)

    assert runner.get_session(sid) is None, "Entry should be removed from registry"
    assert stop_called, "stop() should have been awaited"


# ---------------------------------------------------------------------------
# Tests: send_message rolls back in-flight id on non-ValueError handler error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_rolls_back_in_flight_on_handler_error() -> None:
    """When _handle_in_message raises a non-ValueError exception (e.g. OSError),
    send_message must: remove the just-added in-flight id, emit an idle status,
    and NOT leave is_busy=True or propagate the exception.

    Before the fix: only ValueError is caught; OSError propagates and
    _in_flight_prompt_ids retains 'p1', leaving is_busy=True permanently.
    After the fix: except Exception rolls back the id and emits idle.
    """
    sp = SessionProcess(uuid4())

    # Stub start() so no real subprocess is launched
    async def _fake_start() -> None:
        pass

    sp.start = _fake_start  # type: ignore[method-assign]

    # Give _process a mock stdin (write path won't be reached after rollback)
    mock_stdin = MagicMock()
    mock_process = MagicMock()
    mock_process.stdin = mock_stdin
    sp._process = mock_process

    # _handle_in_message raises OSError to simulate a file-read / config failure
    async def _raising_handle(msg: object) -> None:
        raise OSError("simulated file read failure")

    sp._handle_in_message = _raising_handle  # type: ignore[method-assign]

    # Capture emitted statuses
    emitted_states: list[str] = []

    async def _recording_emit_status(state: str, **kwargs: object) -> None:
        emitted_states.append(state)

    sp._emit_status = _recording_emit_status  # type: ignore[method-assign]

    # Build a valid JSONRPCPromptMessage payload
    prompt_json = '{"jsonrpc":"2.0","method":"prompt","id":"p1","params":{"user_input":"hello"}}'

    # Must NOT raise
    await sp.send_message(prompt_json)

    # After rollback: 'p1' must not be in the set and session must not be busy
    assert "p1" not in sp._in_flight_prompt_ids, (
        "in-flight id 'p1' was not rolled back after handler failure"
    )
    assert sp.is_busy is False, "is_busy should be False after rollback"
    # idle must have been emitted (last status state)
    assert emitted_states, "no status was emitted; expected at least 'busy' then 'idle'"
    assert emitted_states[-1] == "idle", (
        f"last emitted state should be 'idle', got {emitted_states[-1]!r}"
    )
