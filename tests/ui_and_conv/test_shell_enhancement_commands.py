from __future__ import annotations

from pythinker_code.ui.shell.slash import registry


def test_enhancement_commands_are_registered() -> None:
    for name in ("restore", "trust", "worklog", "context", "tools", "accessibility"):
        assert registry.find_command(name) is not None
