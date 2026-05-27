from __future__ import annotations


def test_memory_command_is_registered():
    from pythinker_code.ui.shell import slash

    assert slash.registry.find_command("memory") is not None
    assert slash.registry.find_command("mem") is not None
