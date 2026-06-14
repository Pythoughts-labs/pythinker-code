import asyncio
from typing import cast

from openai import AsyncStream
from openai.types.chat import ChatCompletionChunk

from pythinker_core.chat_provider.pythinker import (
    PythinkerStreamedMessage,
    extract_usage_from_chunk,
)


def test_pythinker_extracts_choice_usage_in_stream_chunk() -> None:
    chunk = ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl-6970b5d02fa474c1767e8767",
            "object": "chat.completion.chunk",
            "created": 1768994256,
            "model": "pythinker-ai",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                    "usage": {
                        "prompt_tokens": 8,
                        "completion_tokens": 11,
                        "total_tokens": 19,
                        "cached_tokens": 8,
                    },
                }
            ],
            "system_fingerprint": "fpv0_10a6da87",
        }
    )
    usage = extract_usage_from_chunk(chunk)
    assert usage is not None
    assert usage.prompt_tokens == 8
    assert usage.completion_tokens == 11
    assert usage.total_tokens == 19


def test_pythinker_stream_captures_length_finish_reason() -> None:
    """The streamed message surfaces the provider's finish_reason ('length' == output cap)."""
    chunk = ChatCompletionChunk.model_validate(
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "pythinker-ai",
            "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": "length"}],
        }
    )

    async def _chunks():
        yield chunk

    async def _run() -> str | None:
        # _convert_stream_response only needs an async iterable of chunks.
        stream = PythinkerStreamedMessage(cast(AsyncStream[ChatCompletionChunk], _chunks()))
        async for _ in stream:
            pass
        return stream.finish_reason

    assert asyncio.run(_run()) == "length"
