from __future__ import annotations

from pythinker_core.message import ToolCall
from pythinker_core.tooling import ToolResult
from pythinker_core.tooling.error import ToolValidateError

from pythinker_code.soul.pythinkersoul import _malformed_empty_tool_call_summary


def _call(call_id: str, name: str, arguments: str = "") -> ToolCall:
    return ToolCall(
        id=call_id,
        function=ToolCall.FunctionBody(name=name, arguments=arguments),
    )


def _validation_result(call_id: str, field: str) -> ToolResult:
    return ToolResult(
        tool_call_id=call_id,
        return_value=ToolValidateError(
            "1 validation error for Params\n"
            f"{field}\n"
            "  Field required [type=missing, input_value={}, input_type=dict]"
        ),
    )


def test_malformed_empty_tool_call_summary_names_missing_fields() -> None:
    summary = _malformed_empty_tool_call_summary(
        [_call("a", "Grep"), _call("b", "Shell")],
        [_validation_result("a", "pattern"), _validation_result("b", "command")],
    )

    assert summary == "Grep.pattern; Shell.command"


def test_malformed_empty_tool_call_summary_ignores_non_empty_arguments() -> None:
    summary = _malformed_empty_tool_call_summary(
        [_call("a", "Grep", '{"pattern":"TODO"}')],
        [_validation_result("a", "path")],
    )

    assert summary is None
