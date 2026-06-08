"""The <untrusted_data> wrapper is model-facing only; it must never reach the
TUI/ACP display surfaces.

The model receives ``ToolReturnValue.output`` wrapped in
``<untrusted_data id="...">...</untrusted_data>`` (prompt-injection defense).
The single Pythinker render boundary (``_ToolCallBlock._card_result_*``) must
hand renderers the clean inner content so the tags never leak into the UI.
"""

from __future__ import annotations

from pythinker_core.tooling import ToolReturnValue

from pythinker_code.ui.shell.visualize._blocks import _ToolCallBlock
from pythinker_code.utils.trust import UntrustedData, strip_untrusted_envelope


def test_strip_untrusted_envelope_roundtrips() -> None:
    wrapped = UntrustedData("line one\nline two").render_for_prompt()
    assert strip_untrusted_envelope(wrapped) == "line one\nline two"


def test_strip_untrusted_envelope_is_noop_on_plain_output() -> None:
    assert strip_untrusted_envelope("just command output\n") == "just command output\n"


def test_strip_untrusted_envelope_unescapes_inner_closing_tag() -> None:
    wrapped = UntrustedData("before </untrusted_data> after").render_for_prompt()
    assert strip_untrusted_envelope(wrapped) == "before </untrusted_data> after"


def test_card_result_details_hides_wrapper_from_display() -> None:
    wrapped = UntrustedData("git diff output\n+ added line").render_for_prompt()
    result = ToolReturnValue(
        is_error=False, output=wrapped, message="ok", display=[], extras={}
    )
    details = _ToolCallBlock._card_result_details(result)
    assert "<untrusted_data" not in details["output"]
    assert "</untrusted_data>" not in details["output"]
    assert "git diff output" in details["output"]


def test_card_result_text_hides_wrapper_from_display() -> None:
    wrapped = UntrustedData("stderr trace").render_for_prompt()
    result = ToolReturnValue(
        is_error=True, output=wrapped, message="Command failed", display=[], extras={}
    )
    text = _ToolCallBlock._card_result_text(result)
    assert "<untrusted_data" not in text
    assert "stderr trace" in text
