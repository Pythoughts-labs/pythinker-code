"""memory-3: re-arm recall on a working-set / topic shift, throttled."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from pythinker_core.message import Message, TextPart, ToolCall

import pythinker_code.memory.recall as recall_mod
from pythinker_code.memory.recall import (
    RecallInjectionProvider,
    _assistant_turns,
    _jaccard,
    _working_set,
)


def _call(name: str, args: dict[str, Any]) -> ToolCall:
    return ToolCall(id="c", function=ToolCall.FunctionBody(name=name, arguments=json.dumps(args)))


def _assistant_calls(*calls: ToolCall) -> Message:
    return Message(role="assistant", content=[], tool_calls=list(calls))


def test_working_set_extracts_touched_dirs() -> None:
    history = [
        _assistant_calls(
            _call("ReadFile", {"path": "src/auth/login.py"}),
            _call("Grep", {"path": "src/auth"}),
            _call("Shell", {"command": "ls"}),  # non-file tool ignored
        )
    ]
    ws = _working_set(history)
    assert "src/auth" in ws  # parent dir of login.py and the grep path
    assert all("command" not in d for d in ws)


def test_working_set_ignores_unparseable_args() -> None:
    bad = Message(
        role="assistant",
        content=[],
        tool_calls=[
            ToolCall(id="c", function=ToolCall.FunctionBody(name="ReadFile", arguments="{"))
        ],
    )
    assert _working_set([bad]) == frozenset()


def test_jaccard() -> None:
    assert _jaccard(frozenset(), frozenset()) == 1.0
    assert _jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0
    assert _jaccard(frozenset({"a", "b"}), frozenset({"a"})) == 0.5


def test_assistant_turns_counts_assistant_messages() -> None:
    history = [
        Message(role="user", content=[TextPart(text="hi")]),
        Message(role="assistant", content=[TextPart(text="a")]),
        Message(role="assistant", content=[TextPart(text="b")]),
    ]
    assert _assistant_turns(history) == 2


def _make_provider(monkeypatch: pytest.MonkeyPatch) -> RecallInjectionProvider:
    # Isolate the re-arm trigger from content/ranking: distinct block per call so the
    # content-dedup never masks a genuine re-fire.
    counter = {"n": 0}

    async def fake_block(**_kw: Any) -> str:
        counter["n"] += 1
        return f"recall-block-{counter['n']}"

    async def fake_candidates(_store: Any, _wd: Any) -> list[Any]:
        return []

    monkeypatch.setattr(recall_mod, "build_recall_block", fake_block)
    monkeypatch.setattr(recall_mod, "gather_candidates", fake_candidates)
    monkeypatch.setattr(recall_mod, "find_recent_open_root_todos", lambda *a, **k: [])

    session = cast(
        Any,
        type(
            "_Sess",
            (),
            {
                "work_dir": cast(Any, "wd"),
                "id": "cur",
                "title": "t",
                "work_dir_meta": type("_M", (), {"sessions_dir": "x"})(),
            },
        )(),
    )
    return RecallInjectionProvider(cast(Any, object()), session)


def _history_touching(path: str, *, assistant_turns: int) -> list[Message]:
    history: list[Message] = [_assistant_calls(_call("ReadFile", {"path": path}))]
    history += [
        Message(role="assistant", content=[TextPart(text="step")]) for _ in range(assistant_turns)
    ]
    return history


async def test_recall_rearms_on_working_set_shift(monkeypatch: pytest.MonkeyPatch) -> None:
    prov = _make_provider(monkeypatch)

    # First fire (empty history) — the existing one-shot behavior.
    assert await prov.get_injections([], cast(Any, None))
    # No working set / no shift -> no re-fire.
    assert await prov.get_injections([], cast(Any, None)) == []

    # Pivot into src/auth with enough assistant turns -> re-fires.
    history = _history_touching("src/auth/login.py", assistant_turns=5)
    assert await prov.get_injections(history, cast(Any, None))

    # Same working set, no new turns -> throttled.
    assert await prov.get_injections(history, cast(Any, None)) == []


async def test_recall_rearm_is_throttled_until_enough_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prov = _make_provider(monkeypatch)
    assert await prov.get_injections([], cast(Any, None))  # first fire

    # Shifted working set but only 1 assistant turn since -> throttled (needs >= 3).
    history = _history_touching("src/payments/charge.py", assistant_turns=1)
    assert await prov.get_injections(history, cast(Any, None)) == []
