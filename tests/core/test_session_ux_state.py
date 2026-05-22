from __future__ import annotations

from pythinker_code.session_state import (
    AccessibilityStateData,
    SessionState,
    TrustStateData,
    load_session_state,
    save_session_state,
)


def test_session_state_defaults_to_untrusted_and_normal_accessibility() -> None:
    state = SessionState()

    assert state.trust == TrustStateData()
    assert state.accessibility == AccessibilityStateData()
    assert state.trust.safe_mode is True
    assert state.accessibility.plain_output is False


def test_session_state_persists_trust_and_accessibility(tmp_path) -> None:
    state = SessionState()
    state.trust.trusted = True
    state.trust.safe_mode = False
    state.accessibility.plain_output = True
    state.accessibility.animations = False
    state.accessibility.symbols = "ascii"

    save_session_state(state, tmp_path)
    loaded = load_session_state(tmp_path)

    assert loaded.trust.trusted is True
    assert loaded.trust.safe_mode is False
    assert loaded.accessibility.plain_output is True
    assert loaded.accessibility.animations is False
    assert loaded.accessibility.symbols == "ascii"
