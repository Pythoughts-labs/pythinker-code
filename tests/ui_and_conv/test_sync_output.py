"""Tests for DEC mode 2026 synchronized-update frame bracketing."""

from __future__ import annotations

from io import StringIO

from prompt_toolkit.data_structures import Size
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.vt100 import Vt100_Output

from pythinker_code.ui.shell.sync_output import (
    BEGIN_SYNCHRONIZED_UPDATE,
    END_SYNCHRONIZED_UPDATE,
    install_synchronized_output,
)
from pythinker_code.ui.terminal_capabilities import synchronized_output_enabled


def _vt100_output(stdout: StringIO) -> Vt100_Output:
    return Vt100_Output(stdout, get_size=lambda: Size(rows=24, columns=80), term="xterm-256color")


def test_flush_brackets_frame_in_synchronized_update_marks():
    stdout = StringIO()
    output = _vt100_output(stdout)
    assert install_synchronized_output(output)

    output.write_raw("\x1b[2K")
    output.write("hello")
    output.flush()

    written = stdout.getvalue()
    assert written.startswith(BEGIN_SYNCHRONIZED_UPDATE)
    assert written.endswith(END_SYNCHRONIZED_UPDATE)
    assert "hello" in written


def test_empty_flush_emits_no_marks():
    stdout = StringIO()
    output = _vt100_output(stdout)
    install_synchronized_output(output)

    output.flush()

    assert stdout.getvalue() == ""


def test_each_flush_is_bracketed_independently():
    stdout = StringIO()
    output = _vt100_output(stdout)
    install_synchronized_output(output)

    output.write("frame1")
    output.flush()
    output.write("frame2")
    output.flush()

    assert stdout.getvalue().count(BEGIN_SYNCHRONIZED_UPDATE) == 2
    assert stdout.getvalue().count(END_SYNCHRONIZED_UPDATE) == 2


def test_install_is_idempotent():
    stdout = StringIO()
    output = _vt100_output(stdout)
    assert install_synchronized_output(output)
    assert install_synchronized_output(output)

    output.write("frame")
    output.flush()

    assert stdout.getvalue().count(BEGIN_SYNCHRONIZED_UPDATE) == 1
    assert stdout.getvalue().count(END_SYNCHRONIZED_UPDATE) == 1


def test_output_without_vt100_buffer_is_left_alone():
    assert not install_synchronized_output(DummyOutput())


def test_synchronized_output_enabled_by_default():
    assert synchronized_output_enabled({"TERM": "xterm-256color"})


def test_synchronized_output_kill_switch():
    assert not synchronized_output_enabled(
        {"TERM": "xterm-256color", "PYTHINKER_NO_SYNC_OUTPUT": "1"}
    )


def test_synchronized_output_disabled_on_dumb_term():
    assert not synchronized_output_enabled({"TERM": "dumb"})
