"""Contract test for the ACP model-switch thinking-effort resolution (Finding 4).

`AcpServer.set_model` derives `thinking_effort` from the selected model's
`thinking` flag. The regression was forcing `"high"` and discarding the user's
configured effort; the fix preserves the configured effort and only defaults to
high when thinking was previously off. This mirrors that logic against the shared
resolver so the contract is pinned even though the server method itself needs a
live ACP session to exercise end-to-end.
"""

import pytest

from pythinker_code.thinking import DEFAULT_THINKING_EFFORT, effective_config_thinking_effort


def _resolve_acp_effort(thinking: bool, default_thinking: bool, default_effort: str | None) -> str:
    if thinking:
        current = effective_config_thinking_effort(default_thinking, default_effort)  # type: ignore[arg-type]
        return current if current != "off" else DEFAULT_THINKING_EFFORT
    return "off"


@pytest.mark.parametrize(
    "default_thinking,default_effort,expected",
    [
        (True, "medium", "medium"),  # preserve configured medium
        (True, "low", "low"),  # preserve configured low
        (False, "off", "high"),  # was off -> default to high when model wants thinking
        (True, None, "high"),  # legacy bool true, no effort -> high
    ],
)
def test_acp_thinking_model_preserves_effort(
    default_thinking: bool, default_effort: str | None, expected: str
) -> None:
    assert _resolve_acp_effort(True, default_thinking, default_effort) == expected


def test_acp_non_thinking_model_is_off() -> None:
    assert _resolve_acp_effort(False, True, "high") == "off"
