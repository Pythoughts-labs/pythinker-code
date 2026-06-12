"""Tests for InlineCommandReminderProvider."""

from __future__ import annotations

from unittest.mock import MagicMock

from pythinker_core.message import Message, TextPart

from pythinker_code.soul.dynamic_injections.inline_commands import (
    _INLINE_COMMANDS_TYPE,
    InlineCommandReminderProvider,
)
from pythinker_code.utils.slashcmd import SlashCommand


def _cmd(name: str, aliases: list[str] | None = None) -> SlashCommand:
    return SlashCommand(name=name, description="", func=lambda: None, aliases=aliases or [])


def _mock_soul(is_subagent: bool = False) -> MagicMock:
    soul = MagicMock()
    soul.is_subagent = is_subagent
    soul.available_slash_commands = [
        _cmd("best-practices", aliases=["bp"]),
        _cmd("clear"),
        _cmd("goal"),
    ]
    return soul


def _user(text: str) -> Message:
    return Message(role="user", content=[TextPart(text=text)])


async def test_injects_for_inline_known_command() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("create a landing page and use /best-practices for it")]
    result = await provider.get_injections(history, _mock_soul())
    assert len(result) == 1
    assert result[0].type == _INLINE_COMMANDS_TYPE
    assert "/best-practices" in result[0].content
    assert "NOT execute" in result[0].content


async def test_injects_for_alias() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("apply /bp while you build it")]
    result = await provider.get_injections(history, _mock_soul())
    assert len(result) == 1
    assert "/bp" in result[0].content


async def test_injects_for_skill_reference_even_when_unknown() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("then use /skill:design-taste-frontend to build the page")]
    result = await provider.get_injections(history, _mock_soul())
    assert len(result) == 1
    assert "/skill:design-taste-frontend" in result[0].content
    assert "ReadSkill" in result[0].content


async def test_leading_command_not_flagged_but_later_refs_are() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("/best-practices and afterwards run /clear")]
    result = await provider.get_injections(history, _mock_soul())
    assert len(result) == 1
    # The leading command is excluded from the flagged refs; only /clear is listed.
    assert "commands inline: /clear." in result[0].content


async def test_leading_command_alone_not_flagged() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("/best-practices")]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_unknown_tokens_and_paths_ignored() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("look in /usr/local/bin and /tmp for the binary")]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_known_name_followed_by_slash_is_a_path_not_a_command() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("the config lives in /clear/cache today")]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_mid_word_slash_not_flagged() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("see tests/clear for the fixtures")]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_case_insensitive_match() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("please use /Best-Practices here")]
    result = await provider.get_injections(history, _mock_soul())
    assert len(result) == 1
    assert "/Best-Practices" in result[0].content


async def test_one_shot_per_message() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("use /best-practices please")]
    soul = _mock_soul()
    first = await provider.get_injections(history, soul)
    second = await provider.get_injections(history, soul)
    assert len(first) == 1
    assert second == []


async def test_new_message_fires_again() -> None:
    provider = InlineCommandReminderProvider()
    soul = _mock_soul()
    first = await provider.get_injections([_user("use /best-practices please")], soul)
    second = await provider.get_injections(
        [_user("use /best-practices please"), _user("now also apply /goal here")], soul
    )
    assert len(first) == 1
    assert len(second) == 1
    assert "/goal" in second[0].content


async def test_duplicate_refs_listed_once() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("use /clear then /clear again")]
    result = await provider.get_injections(history, _mock_soul())
    assert len(result) == 1
    assert result[0].content.count("/clear") == 1


async def test_skips_when_last_message_not_user() -> None:
    provider = InlineCommandReminderProvider()
    history = [
        _user("use /best-practices please"),
        Message(role="assistant", content=[TextPart(text="on it")]),
    ]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_skips_notification_message() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user('<notification id="n1">task done, /clear suggested</notification>')]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_skips_system_reminder_only_user_message() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("<system-reminder>\nplan mode mentions /clear here\n</system-reminder>")]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_reminder_span_inside_user_message_not_scanned() -> None:
    provider = InlineCommandReminderProvider()
    history = [
        _user(
            "just say hi\n<system-reminder>\nthe /best-practices command exists\n</system-reminder>"
        )
    ]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []


async def test_subagent_gets_nothing() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("use /best-practices please")]
    result = await provider.get_injections(history, _mock_soul(is_subagent=True))
    assert result == []


async def test_empty_history() -> None:
    provider = InlineCommandReminderProvider()
    result = await provider.get_injections([], _mock_soul())
    assert result == []


async def test_compaction_resets_processed_messages() -> None:
    provider = InlineCommandReminderProvider()
    history = [_user("use /best-practices please")]
    soul = _mock_soul()
    first = await provider.get_injections(history, soul)
    assert len(first) == 1
    await provider.on_context_compacted()
    again = await provider.get_injections(history, soul)
    assert len(again) == 1


async def test_reminder_glued_before_command_still_flagged() -> None:
    """A stripped reminder block must not promote a mid-message ref to 'leading'.

    The original message starts with '<', so slash dispatch never ran it; the
    reference must be flagged even though it sits at position 0 after the
    reminder block is removed.
    """
    provider = InlineCommandReminderProvider()
    history = [_user("<system-reminder>plan mode is active</system-reminder>/best-practices")]
    result = await provider.get_injections(history, _mock_soul())
    assert len(result) == 1
    assert "commands inline: /best-practices." in result[0].content


async def test_whitespace_leading_command_not_flagged() -> None:
    """Slash dispatch strips leading whitespace, so '  /cmd' did run."""
    provider = InlineCommandReminderProvider()
    history = [_user("  /best-practices")]
    result = await provider.get_injections(history, _mock_soul())
    assert result == []
