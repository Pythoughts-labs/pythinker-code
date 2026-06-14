"""AnthropicStreamedMessage must surface a ``finish_reason`` so the agent loop's
output-token-truncation recovery (the GenerateResult.truncated signal) works for the
Anthropic provider, not only the OpenAI-compatible ones.

Without this mapping, ``getattr(stream, "finish_reason", None)`` returns ``None`` for every
Anthropic response and a reply cut off by ``max_tokens`` is silently treated as complete.
"""

from __future__ import annotations

from anthropic.types import Message as AnthropicMessage
from anthropic.types import Usage

from pythinker_core.contrib.chat_provider.anthropic import AnthropicStreamedMessage


def _message(stop_reason: str | None) -> AnthropicMessage:
    return AnthropicMessage(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-x",
        content=[],
        stop_reason=stop_reason,  # type: ignore[arg-type]
        usage=Usage(input_tokens=1, output_tokens=1),
    )


async def test_anthropic_max_tokens_maps_to_length() -> None:
    """Native ``stop_reason='max_tokens'`` (output cap) maps to ``finish_reason='length'`` so
    the loop detects truncation and recovers instead of accepting a half-finished answer."""
    stream = AnthropicStreamedMessage(_message("max_tokens"))
    async for _ in stream:
        pass
    assert stream.finish_reason == "length"


async def test_anthropic_clean_stop_is_not_length() -> None:
    """A clean completion (``stop_reason='end_turn'``) must not look truncated."""
    stream = AnthropicStreamedMessage(_message("end_turn"))
    async for _ in stream:
        pass
    assert stream.finish_reason != "length"
