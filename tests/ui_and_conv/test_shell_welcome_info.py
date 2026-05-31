from rich.console import Console
from rich.text import Text

from pythinker_code.ui import shell as shell_module


def test_shell_welcome_uses_pythinker_code_copy(monkeypatch):
    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    shell_module._print_welcome_info("Pythinker Code", [])

    output = console.export_text()
    assert "Pythinker Code v9.9.9" in output
    assert "Welcome to Pythinker" in output
    assert "think first" in output


def test_directory_label_uses_brand_info_token():
    from pythinker_code.ui.shell import WelcomeInfoItem, _value_style_for_label
    from pythinker_code.ui.theme import get_tui_tokens, set_active_theme

    set_active_theme("dark")
    style = _value_style_for_label("Directory", WelcomeInfoItem.Level.INFO)
    assert get_tui_tokens("dark").info in style  # "#AFE3F1"


def test_welcome_banner_chip_shown_in_output(monkeypatch):
    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    chip = Text("↑ Update available — v1.0.0 · /update")
    shell_module._print_welcome_info("Pythinker Code", [], banner=chip)

    output = console.export_text()
    assert "Update available" in output
    assert "/update" in output
    assert "Welcome to Pythinker" in output


def test_welcome_banner_chip_update_wins_over_whats_new(monkeypatch):
    monkeypatch.setattr(shell_module, "consume_whats_new", lambda: "0.25.0")
    monkeypatch.setattr(shell_module, "welcome_update_target", lambda: "0.26.0")

    chip = shell_module._welcome_banner_chip()

    assert chip is not None
    text = chip.plain
    assert "Update available" in text
    assert "0.26.0" in text
    assert "What's new" not in text


def test_welcome_banner_no_chip_unchanged(monkeypatch):
    console_with = Console(record=True, width=120, color_system=None)
    console_without = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "get_version", lambda: "0.26.0")

    monkeypatch.setattr(shell_module, "console", console_without)
    shell_module._print_welcome_info("Pythinker Code", [])
    out_without = console_without.export_text()

    monkeypatch.setattr(shell_module, "console", console_with)
    shell_module._print_welcome_info("Pythinker Code", [], banner=None)
    out_with = console_with.export_text()

    # Both paths produce the same output when banner is None.
    assert out_without == out_with
    assert "Welcome to Pythinker" in out_without


def test_welcome_chip_renders_in_footer_not_header(monkeypatch):
    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    chip = Text("✦ What's new in v9.9.9 · /changelog")
    shell_module._print_welcome_info("Pythinker Code", [], banner=chip)

    lines = [ln for ln in console.export_text().splitlines() if ln.strip()]
    # Chip sits on the bottom border (footer), not in the header.
    assert "changelog" in lines[-1]
    assert all("changelog" not in ln for ln in lines[:3])


def test_welcome_info_grid_has_no_pipe_separator(monkeypatch):
    from pythinker_code.ui.shell import WelcomeInfoItem

    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    items = [WelcomeInfoItem(name="Directory", value="/tmp/proj")]
    shell_module._print_welcome_info("Pythinker Code", items)

    out = console.export_text()
    dir_line = next(ln for ln in out.splitlines() if "Directory" in ln)
    # Only the two panel-edge pipes remain; the separator column is gone.
    assert dir_line.count("│") == 2
    assert "/tmp/proj" in dir_line


def test_welcome_strapline_and_help_on_separate_lines(monkeypatch):
    console = Console(record=True, width=120, color_system=None)
    monkeypatch.setattr(shell_module, "console", console)
    monkeypatch.setattr(shell_module, "get_version", lambda: "9.9.9")

    shell_module._print_welcome_info("Pythinker Code", [])

    out = console.export_text()
    assert "then Create." in out
    assert "Send /help for help." in out
    # The strapline and the help line must not share one rendered line.
    assert not any(
        "then Create." in ln and "Send /help" in ln for ln in out.splitlines()
    )
