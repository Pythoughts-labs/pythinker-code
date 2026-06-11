"""Tests for full-terminal clearing on /clear and /reload."""

from __future__ import annotations

from unittest.mock import patch

from pythinker_code.cli import Reload
from pythinker_code.ui.shell.console import clear_terminal_screen, console


class TestReloadClearScreenFlag:
    def test_defaults_to_false(self):
        assert Reload().clear_screen is False

    def test_flag_carried(self):
        assert Reload(clear_screen=True).clear_screen is True

    def test_flag_survives_session_id_rewrap(self):
        """cli._run rewraps Reload to attach the session id — the rewrap must
        preserve clear_screen (mirrors the construction at cli/__init__.py)."""
        e = Reload(clear_screen=True)
        r = Reload(session_id="abc", prefill_text=e.prefill_text, clear_screen=e.clear_screen)
        assert r.clear_screen is True


class TestClearTerminalScreen:
    def test_noop_when_not_a_terminal(self):
        with (
            patch.object(type(console), "is_terminal", property(lambda self: False)),
            patch.object(console, "clear") as mock_clear,
        ):
            clear_terminal_screen()
        mock_clear.assert_not_called()

    def test_clears_screen_and_scrollback(self):
        writes: list[str] = []
        with (
            patch.object(type(console), "is_terminal", property(lambda self: True)),
            patch.object(console, "clear") as mock_clear,
            patch.object(console.file, "write", side_effect=writes.append),
            patch.object(console.file, "flush"),
        ):
            clear_terminal_screen()
        mock_clear.assert_called_once_with()
        assert "\x1b[3J" in writes
