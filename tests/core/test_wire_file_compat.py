"""Backward-compatibility tests for the wire-file protocol version header.

Pins the version-detection behaviour of `WireFile`: files written before the
metadata header existed (legacy, headerless) must still be readable and must
report `WIRE_PROTOCOL_LEGACY_VERSION`. A regression here would silently break
old `wire.jsonl` files for every frontend (Shell, Web, Vis, ACP).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from pythinker_code.wire.file import (
    WireFile,
    WireFileMetadata,
    WireMessageRecord,
    _load_protocol_version,
    parse_wire_file_metadata,
)
from pythinker_code.wire.protocol import (
    WIRE_PROTOCOL_LEGACY_VERSION,
    WIRE_PROTOCOL_VERSION,
)
from pythinker_code.wire.types import TextPart, TurnBegin


def _record_line() -> str:
    """A single wire record serialized as one jsonl line (no metadata header)."""
    record = WireMessageRecord.from_wire_message(
        TurnBegin(user_input=[TextPart(text="hello")]),
        timestamp=time.time(),
    )
    return json.dumps(record.model_dump(mode="json")) + "\n"


def test_headerless_file_reports_legacy_version(tmp_path: Path) -> None:
    """A pre-header wire file (records only) is detected as the legacy version.

    `WireFile.append_record` always emits a metadata header, so a legacy file
    can only be produced by writing the record line directly.
    """
    path = tmp_path / "wire.jsonl"
    path.write_text(_record_line(), encoding="utf-8")

    assert WireFile(path).version == WIRE_PROTOCOL_LEGACY_VERSION


async def test_headerless_records_still_parse(tmp_path: Path) -> None:
    """Legacy (headerless) files remain readable end-to-end."""
    path = tmp_path / "wire.jsonl"
    path.write_text(_record_line(), encoding="utf-8")

    records = [r async for r in WireFile(path).iter_records()]
    assert len(records) == 1
    assert isinstance(records[0].to_wire_message(), TurnBegin)


def test_explicit_version_header_round_trips(tmp_path: Path) -> None:
    """A file whose header pins a version reports exactly that version."""
    path = tmp_path / "wire.jsonl"
    metadata = WireFileMetadata(protocol_version="1.4")
    path.write_text(
        json.dumps(metadata.model_dump(mode="json")) + "\n" + _record_line(),
        encoding="utf-8",
    )

    assert WireFile(path).version == "1.4"


def test_new_file_uses_current_version(tmp_path: Path) -> None:
    """A not-yet-existing wire file defaults to the current protocol version."""
    path = tmp_path / "does-not-exist.jsonl"
    assert WireFile(path).version == WIRE_PROTOCOL_VERSION


def test_load_protocol_version_none_for_headerless(tmp_path: Path) -> None:
    """The low-level loader returns None when the first line is not metadata."""
    path = tmp_path / "wire.jsonl"
    path.write_text(_record_line(), encoding="utf-8")
    assert _load_protocol_version(path) is None


async def test_concurrent_append_writes_single_metadata_header(tmp_path: Path) -> None:
    """Concurrent append_message calls must produce exactly one metadata header.

    Without the asyncio.Lock guard in append_record, two coroutines can each
    observe an empty file before either writes the header and both emit one,
    producing two metadata lines. The lock makes the check-and-write atomic.
    """
    path = tmp_path / "wire.jsonl"
    wire_file = WireFile(path)

    msg = TurnBegin(user_input=[TextPart(text="hello")])

    N = 8
    await asyncio.gather(*[wire_file.append_message(msg) for _ in range(N)])

    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    metadata_count = sum(1 for line in lines if parse_wire_file_metadata(line) is not None)

    assert metadata_count == 1, (
        f"Expected exactly 1 metadata header, got {metadata_count}. "
        "Concurrent appends must not write duplicate headers."
    )
