"""Tests for pythinker_code.session_fork module."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from pythinker_core.message import Message
from pythinker_host.path import HostPath

from pythinker_code.session_fork import (
    TurnInfo,
    _extract_user_text,
    _is_checkpoint_user_message,
    enumerate_turns,
    fork_session,
    truncate_context_at_turn,
    truncate_wire_at_turn,
)
from pythinker_code.wire.file import WireFileMetadata, WireMessageRecord  # noqa: I001
from pythinker_code.wire.protocol import WIRE_PROTOCOL_VERSION
from pythinker_code.wire.types import SteerInput, TextPart, TurnBegin, TurnEnd

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_share_dir(monkeypatch, tmp_path: Path) -> Path:
    share_dir = tmp_path / "share"
    share_dir.mkdir()

    def _get_share_dir() -> Path:
        share_dir.mkdir(parents=True, exist_ok=True)
        return share_dir

    monkeypatch.setattr("pythinker_code.share.get_share_dir", _get_share_dir)
    monkeypatch.setattr("pythinker_code.metadata.get_share_dir", _get_share_dir)
    return share_dir


@pytest.fixture
def work_dir(tmp_path: Path) -> HostPath:
    path = tmp_path / "work"
    path.mkdir()
    return HostPath.unsafe_from_local_path(path)


@pytest.fixture
def session_dir(tmp_path: Path) -> Path:
    d = tmp_path / "session"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_wire_file(session_dir: Path, turns: list[str]) -> Path:
    """Write a wire.jsonl with N turns, each with a TurnBegin and TurnEnd."""
    wire_path = session_dir / "wire.jsonl"
    metadata = WireFileMetadata(protocol_version=WIRE_PROTOCOL_VERSION)
    ts = time.time()

    with wire_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(metadata.model_dump(mode="json")) + "\n")
        for text in turns:
            begin = WireMessageRecord.from_wire_message(
                TurnBegin(user_input=[TextPart(text=text)]),
                timestamp=ts,
            )
            f.write(json.dumps(begin.model_dump(mode="json")) + "\n")
            end = WireMessageRecord.from_wire_message(TurnEnd(), timestamp=ts)
            f.write(json.dumps(end.model_dump(mode="json")) + "\n")
            ts += 1

    return wire_path


def _write_context_file(session_dir: Path, user_messages: list[str]) -> Path:
    """Write a context.jsonl with user messages and dummy assistant responses."""
    context_path = session_dir / "context.jsonl"
    with context_path.open("w", encoding="utf-8") as f:
        for text in user_messages:
            msg = Message(role="user", content=[TextPart(text=text)])
            f.write(msg.model_dump_json(exclude_none=True) + "\n")
            resp = Message(role="assistant", content="response")
            f.write(resp.model_dump_json(exclude_none=True) + "\n")
    return context_path


# ---------------------------------------------------------------------------
# Tests: _extract_user_text
# ---------------------------------------------------------------------------


class TestExtractUserText:
    def test_string_input(self):
        assert _extract_user_text("hello world") == "hello world"

    def test_content_parts(self):
        parts = [{"text": "hello"}, {"text": "world"}]
        assert _extract_user_text(parts) == "hello world"

    def test_empty_list(self):
        assert _extract_user_text([]) == ""

    def test_mixed_parts(self):
        parts = [{"text": "hello"}, {"type": "image", "source": "..."}]
        assert _extract_user_text(parts) == "hello"

    def test_string_parts_in_list(self):
        parts = ["hello", {"text": "world"}]
        assert _extract_user_text(parts) == "hello world"


# ---------------------------------------------------------------------------
# Tests: _is_checkpoint_user_message
# ---------------------------------------------------------------------------


class TestIsCheckpointUserMessage:
    def test_checkpoint_string(self):
        record = {"role": "user", "content": "<system>CHECKPOINT 0</system>"}
        assert _is_checkpoint_user_message(record) is True

    def test_checkpoint_content_part(self):
        record = {"role": "user", "content": [{"text": "<system>CHECKPOINT 3</system>"}]}
        assert _is_checkpoint_user_message(record) is True

    def test_normal_user_message(self):
        record = {"role": "user", "content": "hello"}
        assert _is_checkpoint_user_message(record) is False

    def test_assistant_message(self):
        record = {"role": "assistant", "content": "<system>CHECKPOINT 0</system>"}
        assert _is_checkpoint_user_message(record) is False


# ---------------------------------------------------------------------------
# Tests: enumerate_turns
# ---------------------------------------------------------------------------


class TestEnumerateTurns:
    def test_empty_file(self, session_dir: Path):
        assert enumerate_turns(session_dir / "wire.jsonl") == []

    def test_nonexistent_file(self, tmp_path: Path):
        assert enumerate_turns(tmp_path / "nonexistent.jsonl") == []

    def test_single_turn(self, session_dir: Path):
        _write_wire_file(session_dir, ["hello world"])
        turns = enumerate_turns(session_dir / "wire.jsonl")
        assert len(turns) == 1
        assert turns[0] == TurnInfo(index=0, user_text="hello world")

    def test_multiple_turns(self, session_dir: Path):
        _write_wire_file(session_dir, ["first", "second", "third"])
        turns = enumerate_turns(session_dir / "wire.jsonl")
        assert len(turns) == 3
        assert turns[0].index == 0
        assert turns[0].user_text == "first"
        assert turns[1].index == 1
        assert turns[1].user_text == "second"
        assert turns[2].index == 2
        assert turns[2].user_text == "third"


# ---------------------------------------------------------------------------
# Tests: truncate_wire_at_turn
# ---------------------------------------------------------------------------


class TestTruncateWireAtTurn:
    def test_truncate_at_first_turn(self, session_dir: Path):
        _write_wire_file(session_dir, ["first", "second", "third"])
        wire_path = session_dir / "wire.jsonl"
        lines = truncate_wire_at_turn(wire_path, 0)
        # metadata + TurnBegin + TurnEnd = 3 lines
        assert len(lines) == 3

    def test_truncate_at_last_turn(self, session_dir: Path):
        _write_wire_file(session_dir, ["first", "second"])
        wire_path = session_dir / "wire.jsonl"
        lines = truncate_wire_at_turn(wire_path, 1)
        # metadata + 2*(TurnBegin + TurnEnd) = 5 lines
        assert len(lines) == 5

    def test_out_of_range(self, session_dir: Path):
        _write_wire_file(session_dir, ["first"])
        wire_path = session_dir / "wire.jsonl"
        with pytest.raises(ValueError, match="out of range"):
            truncate_wire_at_turn(wire_path, 5)

    def test_nonexistent_file(self, tmp_path: Path):
        with pytest.raises(ValueError, match="wire.jsonl not found"):
            truncate_wire_at_turn(tmp_path / "wire.jsonl", 0)

    def test_preserves_metadata(self, session_dir: Path):
        _write_wire_file(session_dir, ["first"])
        wire_path = session_dir / "wire.jsonl"
        lines = truncate_wire_at_turn(wire_path, 0)
        first_record = json.loads(lines[0])
        assert first_record["type"] == "metadata"

    def test_metadata_only_no_turns(self, session_dir: Path):
        """wire.jsonl with only metadata and no turns should raise ValueError."""
        wire_path = session_dir / "wire.jsonl"
        metadata = WireFileMetadata(protocol_version=WIRE_PROTOCOL_VERSION)
        with wire_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(metadata.model_dump(mode="json")) + "\n")
        with pytest.raises(ValueError, match="out of range"):
            truncate_wire_at_turn(wire_path, 0)


# ---------------------------------------------------------------------------
# Tests: truncate_context_at_turn
# ---------------------------------------------------------------------------


class TestTruncateContextAtTurn:
    def test_truncate_at_first_turn(self, session_dir: Path):
        _write_context_file(session_dir, ["first msg", "second msg"])
        context_path = session_dir / "context.jsonl"
        lines = truncate_context_at_turn(context_path, 0)
        # first user + first assistant = 2 lines
        assert len(lines) == 2

    def test_truncate_at_last_turn(self, session_dir: Path):
        _write_context_file(session_dir, ["first", "second"])
        context_path = session_dir / "context.jsonl"
        lines = truncate_context_at_turn(context_path, 1)
        # all 4 lines
        assert len(lines) == 4

    def test_nonexistent_file(self, tmp_path: Path):
        result = truncate_context_at_turn(tmp_path / "context.jsonl", 0)
        assert result == []

    def test_skips_checkpoint_messages(self, session_dir: Path):
        context_path = session_dir / "context.jsonl"
        context_path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {"role": "user", "content": "first msg"},
            {"role": "assistant", "content": "response 1"},
            {"role": "user", "content": "<system>CHECKPOINT 0</system>"},
            {"role": "user", "content": "second msg"},
            {"role": "assistant", "content": "response 2"},
        ]
        with context_path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        # Turn 0 = "first msg", turn 1 = "second msg" (checkpoint skipped)
        lines = truncate_context_at_turn(context_path, 0)
        # first user + first assistant + checkpoint = 3 lines
        assert len(lines) == 3

    def test_best_effort_when_fewer_turns(self, session_dir: Path):
        _write_context_file(session_dir, ["only one"])
        context_path = session_dir / "context.jsonl"
        # Request turn_index=5 but only 1 turn exists — returns all lines
        lines = truncate_context_at_turn(context_path, 5)
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# Tests: fork_session
# ---------------------------------------------------------------------------


class TestForkSession:
    async def test_fork_at_turn(self, isolated_share_dir: Path, work_dir: HostPath):
        from pythinker_code.session import Session

        source = await Session.create(work_dir)
        _write_wire_file(source.dir, ["turn 0", "turn 1", "turn 2"])
        _write_context_file(source.dir, ["turn 0", "turn 1", "turn 2"])

        new_id = await fork_session(
            source_session_dir=source.dir,
            work_dir=work_dir,
            turn_index=1,
            title_prefix="Undo",
            source_title="My Session",
        )

        # Verify new session exists
        new_session = await Session.find(work_dir, new_id)
        assert new_session is not None

        # Verify wire was truncated
        wire_lines = (
            (new_session.dir / "wire.jsonl").read_text(encoding="utf-8").strip().split("\n")
        )
        # metadata + 2 turns * (TurnBegin + TurnEnd) = 5
        assert len(wire_lines) == 5

        # Verify context was truncated
        ctx_lines = (
            (new_session.dir / "context.jsonl").read_text(encoding="utf-8").strip().split("\n")
        )
        # 2 turns * (user + assistant) = 4
        assert len(ctx_lines) == 4

    async def test_fork_all_turns(self, isolated_share_dir: Path, work_dir: HostPath):
        from pythinker_code.session import Session

        source = await Session.create(work_dir)
        _write_wire_file(source.dir, ["turn 0", "turn 1"])
        _write_context_file(source.dir, ["turn 0", "turn 1"])

        new_id = await fork_session(
            source_session_dir=source.dir,
            work_dir=work_dir,
            turn_index=None,
            title_prefix="Fork",
            source_title="My Session",
        )

        new_session = await Session.find(work_dir, new_id)
        assert new_session is not None

        wire_lines = (
            (new_session.dir / "wire.jsonl").read_text(encoding="utf-8").strip().split("\n")
        )
        # metadata + 2*(TurnBegin + TurnEnd) = 5
        assert len(wire_lines) == 5

    async def test_fork_sets_title(self, isolated_share_dir: Path, work_dir: HostPath):
        from pythinker_code.session import Session
        from pythinker_code.session_state import load_session_state

        source = await Session.create(work_dir)
        _write_wire_file(source.dir, ["hello"])
        _write_context_file(source.dir, ["hello"])

        new_id = await fork_session(
            source_session_dir=source.dir,
            work_dir=work_dir,
            turn_index=0,
            title_prefix="Undo",
            source_title="Original Title",
        )

        new_session = await Session.find(work_dir, new_id)
        assert new_session is not None
        state = load_session_state(new_session.dir)
        assert state.custom_title == "Undo: Original Title"

    async def test_fork_reads_title_from_state(self, isolated_share_dir: Path, work_dir: HostPath):
        """When source_title is None, fork_session reads title from session state."""
        from pythinker_code.session import Session
        from pythinker_code.session_state import load_session_state, save_session_state

        source = await Session.create(work_dir)
        _write_wire_file(source.dir, ["hello"])
        _write_context_file(source.dir, ["hello"])

        # Set a custom title on the source session
        src_state = load_session_state(source.dir)
        src_state.custom_title = "Custom Source Title"
        save_session_state(src_state, source.dir)

        new_id = await fork_session(
            source_session_dir=source.dir,
            work_dir=work_dir,
            turn_index=0,
            title_prefix="Fork",
            # source_title not passed — should read from state
        )

        new_session = await Session.find(work_dir, new_id)
        assert new_session is not None
        state = load_session_state(new_session.dir)
        assert state.custom_title == "Fork: Custom Source Title"

    async def test_fork_copies_referenced_videos(
        self, isolated_share_dir: Path, work_dir: HostPath
    ):
        from pythinker_code.session import Session

        source = await Session.create(work_dir)

        # Create a fake video file
        uploads = source.dir / "uploads"
        uploads.mkdir()
        (uploads / "test.mp4").write_text("fake video")

        # Write wire that references the video
        wire_path = source.dir / "wire.jsonl"
        metadata = WireFileMetadata(protocol_version=WIRE_PROTOCOL_VERSION)
        ts = time.time()
        begin = WireMessageRecord.from_wire_message(
            TurnBegin(user_input="look at uploads/test.mp4"),
            timestamp=ts,
        )
        end = WireMessageRecord.from_wire_message(TurnEnd(), timestamp=ts)
        with wire_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(metadata.model_dump(mode="json")) + "\n")
            f.write(json.dumps(begin.model_dump(mode="json")) + "\n")
            f.write(json.dumps(end.model_dump(mode="json")) + "\n")

        _write_context_file(source.dir, ["look at video"])

        new_id = await fork_session(
            source_session_dir=source.dir,
            work_dir=work_dir,
            turn_index=0,
            source_title="Video Session",
        )

        new_session = await Session.find(work_dir, new_id)
        assert new_session is not None
        new_video = new_session.dir / "uploads" / "test.mp4"
        assert new_video.exists()
        assert new_video.read_text() == "fake video"

    async def test_fork_keeps_wire_and_context_aligned_with_pre_cut_steer(
        self, isolated_share_dir: Path, work_dir: HostPath
    ):
        """Fork at turn 1 keeps context aligned even when turn 0 has a SteerInput.

        The wire has:
          - turn 0: TurnBegin("t0") + SteerInput("t0-steer") + TurnEnd
          - turn 1: TurnBegin("t1") + TurnEnd

        The context has an extra user message for the steer follow-up:
          - user "t0", assistant "r0", user "t0-steer" (steer follow-up), assistant "r0s", user "t1", assistant "r1"

        Before the fix, truncate_context_at_turn counts user messages independently
        and stops after seeing 2 user messages (treating "t0-steer" as turn 1), so
        "t1" is dropped from context.  After the fix, the wire's authoritative count
        drives context truncation and "t1" is retained.
        """
        from pythinker_code.session import Session

        source = await Session.create(work_dir)

        # Build wire: turn 0 has a SteerInput, turn 1 is normal
        wire_path = source.dir / "wire.jsonl"
        metadata = WireFileMetadata(protocol_version=WIRE_PROTOCOL_VERSION)
        ts = time.time()
        records = [
            metadata.model_dump(mode="json"),
            WireMessageRecord.from_wire_message(
                TurnBegin(user_input=[TextPart(text="t0")]), timestamp=ts
            ).model_dump(mode="json"),
            WireMessageRecord.from_wire_message(
                SteerInput(user_input="t0-steer"), timestamp=ts + 0.1
            ).model_dump(mode="json"),
            WireMessageRecord.from_wire_message(TurnEnd(), timestamp=ts + 0.2).model_dump(
                mode="json"
            ),
            WireMessageRecord.from_wire_message(
                TurnBegin(user_input=[TextPart(text="t1")]), timestamp=ts + 1
            ).model_dump(mode="json"),
            WireMessageRecord.from_wire_message(TurnEnd(), timestamp=ts + 1.1).model_dump(
                mode="json"
            ),
        ]
        with wire_path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        # Build context: steer follow-up is an extra user message inside turn 0
        context_path = source.dir / "context.jsonl"
        context_records = [
            {"role": "user", "content": "t0"},
            {"role": "assistant", "content": "r0"},
            {"role": "user", "content": "t0-steer"},  # steer follow-up in context
            {"role": "assistant", "content": "r0s"},
            {"role": "user", "content": "t1"},
            {"role": "assistant", "content": "r1"},
        ]
        with context_path.open("w", encoding="utf-8") as f:
            for r in context_records:
                f.write(json.dumps(r) + "\n")

        new_id = await fork_session(
            source_session_dir=source.dir,
            work_dir=work_dir,
            turn_index=1,
            source_title="Steered Session",
        )

        new_session = await Session.find(work_dir, new_id)
        assert new_session is not None

        new_wire_path = new_session.dir / "wire.jsonl"
        new_context_path = new_session.dir / "context.jsonl"

        # Count TurnBegin records in the new wire
        wire_turn_begins = sum(
            1
            for line in new_wire_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("message", {}).get("type") == "TurnBegin"
        )

        # Count non-steer, non-checkpoint user messages in new context
        ctx_user_msgs: list[str] = []
        for line in new_context_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("role") == "user" and not _is_checkpoint_user_message(r):
                content = r.get("content", "")
                if isinstance(content, str) and content != "t0-steer":
                    ctx_user_msgs.append(content)
                elif isinstance(content, list):
                    ctx_user_msgs.append(str(content))

        # Wire has 2 TurnBegins (turns 0 and 1); context should have 2 real user messages
        assert wire_turn_begins == 2
        assert len(ctx_user_msgs) == 2

        # turn-1 user text must appear in both files
        new_wire_text = new_wire_path.read_text(encoding="utf-8")
        new_ctx_text = new_context_path.read_text(encoding="utf-8")
        assert "t1" in new_wire_text
        assert "t1" in new_ctx_text
