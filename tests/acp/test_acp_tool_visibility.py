"""ACP toolset adaptation: tools a client cannot service are hidden up front.

The session loop already degrades a stray ``AskUserQuestion`` call gracefully
(``QuestionNotSupported`` → textual fallback), but advertising the tool to the
model invites a wasted step per question. ``replace_tools`` hides it instead;
the tool stays registered so a hallucinated call still hits the graceful path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import acp
from pythinker_host.local import local_host

import pythinker_code.acp.tools as acp_tools
from pythinker_code.acp.tools import replace_tools
from pythinker_code.soul.toolset import PythinkerToolset
from pythinker_code.tools.ask_user import AskUserQuestion


def _capabilities(*, terminal: bool = False) -> acp.schema.ClientCapabilities:
    return acp.schema.ClientCapabilities(terminal=terminal)


def _make_toolset() -> PythinkerToolset:
    toolset = PythinkerToolset()
    toolset.add(AskUserQuestion())
    return toolset


class TestReplaceToolsHidesQuestionTool:
    def test_ask_user_question_is_hidden_from_model(self, monkeypatch) -> None:
        monkeypatch.setattr(acp_tools, "get_current_host", lambda: local_host)
        toolset = _make_toolset()

        replace_tools(_capabilities(), MagicMock(), "sid", toolset, MagicMock())

        visible = [tool.name for tool in toolset.tools]
        assert "AskUserQuestion" not in visible

    def test_ask_user_question_remains_registered_for_graceful_fallback(self, monkeypatch) -> None:
        monkeypatch.setattr(acp_tools, "get_current_host", lambda: local_host)
        toolset = _make_toolset()

        replace_tools(_capabilities(), MagicMock(), "sid", toolset, MagicMock())

        assert toolset.find(AskUserQuestion) is not None
