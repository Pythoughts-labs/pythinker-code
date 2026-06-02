from pythinker_code.config import Config
from pythinker_code.thinking import (
    apply_login_thinking_defaults,
    available_thinking_levels,
    effective_config_thinking_effort,
    model_uses_native_thinking,
    next_thinking_level,
)


def test_login_thinking_defaults_initialize_when_unset():
    config = Config()  # fresh config: default_thinking_effort is None
    apply_login_thinking_defaults(config, thinking=False, effort="off")
    assert config.default_thinking is False
    assert config.default_thinking_effort == "off"


def test_login_thinking_defaults_preserve_explicit_user_choice():
    config = Config(default_thinking=True, default_thinking_effort="low")
    # A re-login into a non-thinking provider must not clobber the user's pick;
    # create_llm clamps an unsupported level at use-time.
    apply_login_thinking_defaults(config, thinking=False, effort="off")
    assert config.default_thinking is True
    assert config.default_thinking_effort == "low"


def test_explicit_off_overrides_legacy_default_thinking_true():
    # explicit effort wins, even over the legacy bool
    assert effective_config_thinking_effort(True, "off") == "off"


def test_effort_wins_when_set_and_bool_fallback_when_none():
    assert effective_config_thinking_effort(True, "medium") == "medium"
    assert effective_config_thinking_effort(False, "medium") == "medium"
    assert effective_config_thinking_effort(True, None) == "high"
    assert effective_config_thinking_effort(False, None) == "off"


def test_resolver_matches_legacy_or_expression_for_reachable_states():
    # reachable states (writers keep effort<->bool in sync); resolver == old `or` expr
    assert effective_config_thinking_effort(True, "high") == "high"
    assert effective_config_thinking_effort(False, "off") == "off"
    assert effective_config_thinking_effort(True, None) == "high"
    assert effective_config_thinking_effort(False, None) == "off"


def test_cycle_from_off_on_always_thinking_lands_on_minimal():
    levels = available_thinking_levels({"thinking", "always_thinking"})
    assert "off" not in levels
    # off is unselectable here; the next press must land on the lowest valid level
    assert next_thinking_level("off", levels) == "minimal"


def test_cycle_advances_normally_from_valid_level():
    levels = available_thinking_levels({"thinking", "always_thinking"})
    assert next_thinking_level("minimal", levels) == "low"


def test_native_thinking_capability_has_no_user_effort_dial():
    capabilities = {"always_thinking"}

    assert model_uses_native_thinking(capabilities)
    assert available_thinking_levels(capabilities) == ("off",)


def test_always_thinking_with_effort_capability_remains_selectable():
    capabilities = {"thinking", "always_thinking"}

    assert not model_uses_native_thinking(capabilities)
    assert "off" not in available_thinking_levels(capabilities)
