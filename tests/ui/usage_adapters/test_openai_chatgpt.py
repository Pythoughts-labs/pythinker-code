from __future__ import annotations

import json
from pathlib import Path

from pythinker_code.ui.shell.usage_adapters.openai_chatgpt import (
    OpenAIChatGPTAdapter,
    parse_codex_usage_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_codex_usage_two_windows() -> None:
    payload = json.loads((FIXTURES / "codex_wham_usage.json").read_text())

    report = parse_codex_usage_payload(payload)

    assert report.provider_label == "ChatGPT Codex"
    assert report.summary is not None
    assert report.summary.label == "5h window"
    assert report.summary.unit == "%"
    assert report.summary.used == 73
    assert "resets in" in (report.summary.reset_hint or "")

    assert len(report.limits) == 1
    assert report.limits[0].label == "Weekly window"
    assert report.limits[0].used == 41
    assert report.limits[0].unit == "%"


def test_parse_codex_usage_humanizes_unix_reset_at() -> None:
    """The live wham/usage payload sends `reset_at` as a unix timestamp number;
    it must be humanized ("resets in …"), not dumped as a raw integer."""
    payload = {
        "rate_limit": {
            "primary_window": {
                "percent_left": 99,
                "limit_window_seconds": 18000,
                "reset_at": 4102444800,  # far-future unix seconds
            },
        }
    }
    report = parse_codex_usage_payload(payload)
    assert report.summary is not None
    hint = report.summary.reset_hint or ""
    assert "resets in" in hint
    assert "4102444800" not in hint  # raw timestamp must not leak


def test_parse_codex_usage_handles_alternative_keys() -> None:
    payload = {
        "rate_limits": {
            "five_hour": {"percent_left": 100, "limit_window_seconds": 18000},
            "weekly": {"percent_left": 100, "limit_window_seconds": 604800},
        }
    }
    report = parse_codex_usage_payload(payload)
    assert report.summary is not None
    assert report.summary.used == 100


def test_parse_codex_usage_missing_rate_limits_emits_note() -> None:
    report = parse_codex_usage_payload({})
    assert report.summary is None
    assert any("rate" in n.lower() for n in report.notes)


def test_parse_codex_usage_non_mapping_emits_note() -> None:
    report = parse_codex_usage_payload([])
    assert report.summary is None
    assert any("response" in n.lower() for n in report.notes)


def test_parse_codex_usage_fractional_window_does_not_hang() -> None:
    """_format_reset_delta with a fractional limit_window_seconds (e.g. 0.5) must not
    spin forever. int(0.5)==0, so the old while-loop added 0 and hung. The fix must
    detect step==0 and bail out immediately with reset_hint=='reset'."""
    import threading

    # reset_at in the past (epoch 0) so delta is negative → normalization loop triggers
    payload = {
        "rate_limit": {
            "primary_window": {
                "percent_left": 50,
                "limit_window_seconds": 0.5,
                "reset_at": 0,  # past unix timestamp
            },
        }
    }

    result: list = []
    exc: list = []

    def _run() -> None:
        try:
            report = parse_codex_usage_payload(payload)
            result.append(report)
        except Exception as e:  # noqa: BLE001
            exc.append(e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=3)  # 3 s is more than enough for a correct impl

    assert not thread.is_alive(), (
        "parse_codex_usage_payload hung (infinite loop in _format_reset_delta)"
    )
    assert not exc, f"Unexpected exception: {exc[0]}"
    assert result, "No result returned"
    hint = result[0].summary.reset_hint if result[0].summary else None
    assert hint == "reset", f"Expected 'reset', got {hint!r}"


def test_parse_codex_usage_naive_iso_reset_does_not_crash() -> None:
    """parse_codex_usage_payload with a tz-less ISO-8601 reset_at must not raise
    TypeError (offset-naive vs offset-aware subtraction in _format_reset_delta).
    The result should have a non-None summary whose reset_hint contains 'resets in'."""
    payload = {
        "rate_limit": {
            "primary_window": {
                "percent_left": 50,
                "limit_window_seconds": 18000,
                "reset_at": "2099-12-31T23:59:59",  # naive ISO-8601, no tz
            },
        }
    }
    report = parse_codex_usage_payload(payload)
    assert report.summary is not None
    hint = report.summary.reset_hint or ""
    assert "resets in" in hint


def test_codex_adapter_metadata() -> None:
    assert OpenAIChatGPTAdapter.platform_id == "openai-chatgpt"
    assert OpenAIChatGPTAdapter.requires_admin_key is False
