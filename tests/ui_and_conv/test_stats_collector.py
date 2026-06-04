from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pythinker_code.ui.shell.stats_collector import (
    StepRecord,
    UsagePeriod,
    collect_session_files,
    compute_period_stats,
    compute_insights,
    get_sessions_root,
    parse_wire_file,
)


def _make_wire(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "wire.jsonl"
    lines = [json.dumps({"type": "metadata", "protocol_version": "1.9"})]
    for r in records:
        lines.append(json.dumps(r))
    p.write_text("\n".join(lines))
    return p


def _status_update(ts: float, input_other: int, output: int,
                   cache_read: int = 0, cache_write: int = 0,
                   model_name: str | None = None,
                   provider_key: str | None = None) -> dict:
    return {
        "timestamp": ts,
        "message": {
            "type": "StatusUpdate",
            "payload": {
                "token_usage": {
                    "input_other": input_other,
                    "output": output,
                    "input_cache_read": cache_read,
                    "input_cache_creation": cache_write,
                },
                "model_name": model_name,
                "provider_key": provider_key,
            },
        },
    }


def test_parse_wire_extracts_steps(tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    wire = _make_wire(tmp_path, [
        _status_update(now, 1000, 200),
        _status_update(now + 1, 2000, 400),
    ])
    session_id = "test-session"
    seen = set()
    steps = list(parse_wire_file(wire, session_id, seen))
    assert len(steps) == 2
    assert steps[0].input_other == 1000
    assert steps[1].output == 400


def test_parse_wire_deduplicates(tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    # Same timestamp and total_tokens → duplicate
    record = _status_update(now, 1000, 200)
    wire = _make_wire(tmp_path, [record, record])
    seen = set()
    steps = list(parse_wire_file(wire, "s", seen))
    assert len(steps) == 1


def test_parse_wire_unknown_model_defaults(tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    wire = _make_wire(tmp_path, [_status_update(now, 500, 100)])
    seen = set()
    steps = list(parse_wire_file(wire, "s", seen))
    assert steps[0].model_name == "unknown"
    assert steps[0].provider_key == "unknown"


def test_compute_period_stats_today(tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    steps = [
        StepRecord(session_id="s1", timestamp=now, model_name="claude-sonnet-4-5",
                   provider_key="anthropic", input_other=1000, output=200,
                   input_cache_read=0, input_cache_creation=0),
    ]
    stats = compute_period_stats(steps)
    assert stats["all_time"].total_messages == 1
    assert stats["today"].total_messages == 1
    assert "anthropic" in stats["all_time"].providers


def test_compute_period_stats_excludes_old(tmp_path):
    old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    now = datetime.now(timezone.utc).timestamp()
    steps = [
        StepRecord(session_id="s1", timestamp=old_ts, model_name="m",
                   provider_key="p", input_other=100, output=50,
                   input_cache_read=0, input_cache_creation=0),
        StepRecord(session_id="s2", timestamp=now, model_name="m",
                   provider_key="p", input_other=200, output=100,
                   input_cache_read=0, input_cache_creation=0),
    ]
    stats = compute_period_stats(steps)
    assert stats["all_time"].total_messages == 2
    assert stats["today"].total_messages == 1


def test_get_sessions_root_exists():
    root = get_sessions_root()
    assert root is not None  # may not exist yet, but path should be computed


def test_collect_session_files_finds_wires(tmp_path):
    # Structure: tmp/sessions/wdhash/sessid/wire.jsonl
    sess_dir = tmp_path / "sessions" / "abc123" / "sess1"
    sess_dir.mkdir(parents=True)
    w = sess_dir / "wire.jsonl"
    w.write_text('{"type":"metadata","protocol_version":"1.9"}\n')
    # Subagent wire
    sub_dir = sess_dir / "subagents" / "agent1"
    sub_dir.mkdir(parents=True)
    sw = sub_dir / "wire.jsonl"
    sw.write_text('{"type":"metadata","protocol_version":"1.9"}\n')
    files = collect_session_files(tmp_path / "sessions")
    assert w in files
    assert sw in files


def test_load_all_stats_returns_all_stats(tmp_path, monkeypatch):
    from pythinker_code.ui.shell.stats_collector import AllStats, load_all_stats
    monkeypatch.setattr(
        "pythinker_code.ui.shell.stats_collector.get_sessions_root",
        lambda: tmp_path / "sessions",
    )
    result = load_all_stats()
    assert isinstance(result, AllStats)
    assert "all_time" in result.periods
    assert "all_time" in result.insights
