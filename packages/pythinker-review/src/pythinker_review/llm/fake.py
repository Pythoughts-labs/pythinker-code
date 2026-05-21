"""Deterministic FakeReviewLLM for unit/e2e tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable


class FakeReviewLLM:
    model_display_name = "fake:test-model"

    def __init__(
        self,
        *,
        responder: Callable[[str, str], str] | None = None,
        scripted: Iterable[str] | None = None,
    ) -> None:
        self._responder = responder
        self._scripted = list(scripted) if scripted is not None else None
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, *, system: str, user: str, timeout_s: float) -> str:
        self.calls.append((system, user))
        if self._responder is not None:
            return self._responder(system, user)
        if self._scripted:
            return self._scripted.pop(0)
        return '{"findings": []}'
