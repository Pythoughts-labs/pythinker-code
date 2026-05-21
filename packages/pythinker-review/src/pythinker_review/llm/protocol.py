"""Minimal LLM contract the review engine depends on."""

from __future__ import annotations

from typing import Protocol


class ReviewLLM(Protocol):
    model_display_name: str

    async def complete_json(self, *, system: str, user: str, timeout_s: float) -> str: ...
