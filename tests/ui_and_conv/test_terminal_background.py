"""Tests for OSC 11 background probing and ``theme = "auto"`` resolution."""

from __future__ import annotations

import pytest

import pythinker_code.ui.terminal_background as terminal_background


@pytest.fixture(autouse=True)
def _reset_probe_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(terminal_background, "_cached_bg", None)
    monkeypatch.setattr(terminal_background, "_probe_attempted", False)


def test_parse_osc11_four_digit_components() -> None:
    parse = terminal_background.parse_osc11_response
    assert parse("\x1b]11;rgb:ffff/ffff/ffff\x1b\\") == (255, 255, 255)
    assert parse("\x1b]11;rgb:0000/0000/0000\x07") == (0, 0, 0)


def test_parse_osc11_two_digit_components() -> None:
    assert terminal_background.parse_osc11_response("\x1b]11;rgb:1e/1e/2e\x07") == (30, 30, 46)


def test_parse_osc11_scales_mixed_width_components() -> None:
    # XParseColor scaling: "8000"/0xffff ≈ 128, single digit "8"/0xf ≈ 136.
    assert terminal_background.parse_osc11_response("]11;rgb:8000/8000/8000") == (128, 128, 128)
    assert terminal_background.parse_osc11_response("]11;rgb:8/8/8") == (136, 136, 136)


def test_parse_osc11_rejects_garbage() -> None:
    parse = terminal_background.parse_osc11_response
    assert parse("") is None
    assert parse("\x1b]11;?\x1b\\") is None
    assert parse("]10;rgb:ff/ff/ff") is None
    assert parse("]11;rgb:gg/00/00") is None


def test_probe_returns_none_outside_a_tty() -> None:
    # pytest's captured stdin/stdout are not ttys, so the probe must bail
    # immediately instead of writing escape sequences or blocking.
    assert terminal_background.probe_terminal_background(timeout=0.01) is None


def test_probe_respects_opt_out_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHINKER_NO_BG_PROBE", "1")
    assert terminal_background._probe_uncached(0.01) is None


def test_probe_result_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []

    def fake_probe(timeout: float) -> tuple[int, int, int]:
        calls.append(timeout)
        return (1, 2, 3)

    monkeypatch.setattr(terminal_background, "_probe_uncached", fake_probe)
    assert terminal_background.probe_terminal_background() == (1, 2, 3)
    assert terminal_background.probe_terminal_background() == (1, 2, 3)
    assert len(calls) == 1


def test_failed_probe_is_cached_too(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[float] = []

    def fake_probe(timeout: float) -> None:
        calls.append(timeout)
        return None

    monkeypatch.setattr(terminal_background, "_probe_uncached", fake_probe)
    assert terminal_background.probe_terminal_background() is None
    assert terminal_background.probe_terminal_background() is None
    assert len(calls) == 1


def test_resolve_theme_name_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(terminal_background, "detect_background_theme", lambda: None)
    assert terminal_background.resolve_theme_name("dark") == "dark"
    assert terminal_background.resolve_theme_name("light") == "light"
    # Failed/unsupported probe falls back to dark.
    assert terminal_background.resolve_theme_name("auto") == "dark"


def test_resolve_theme_name_auto_uses_probed_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        terminal_background, "probe_terminal_background", lambda timeout=0.1: (250, 250, 250)
    )
    assert terminal_background.resolve_theme_name("auto") == "light"
    monkeypatch.setattr(
        terminal_background, "probe_terminal_background", lambda timeout=0.1: (10, 10, 20)
    )
    assert terminal_background.resolve_theme_name("auto") == "dark"


def test_unknown_configured_value_falls_back_to_dark() -> None:
    assert terminal_background.resolve_theme_name("neon") == "dark"
