"""Which subagent types get the git-context prompt prefix.

Reviewer-class agents need branch/dirty/merge-base orientation as much as
explore does — without it every review run burns turns rediscovering its
diff scope from a bare prompt.
"""

from __future__ import annotations

from pythinker_code.subagents.core import GIT_CONTEXT_AGENT_TYPES


def test_explore_and_reviewer_types_receive_git_context() -> None:
    assert {"explore", "review", "code_reviewer", "security_reviewer"} <= GIT_CONTEXT_AGENT_TYPES


def test_write_capable_types_do_not() -> None:
    assert {"coder", "implementer", "agent"}.isdisjoint(GIT_CONTEXT_AGENT_TYPES)
