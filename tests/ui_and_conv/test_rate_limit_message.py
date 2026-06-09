from __future__ import annotations

from pythinker_core.chat_provider import APIStatusError

from pythinker_code.ui.shell import _extract_429_detail, _render_429_message


def test_429_console_message_escapes_provider_markup():
    """Provider 429 text is escaped before going to Rich, so a message containing
    ``[...]`` renders literally instead of being silently swallowed as invalid markup
    (the sibling error branches escape provider text the same way)."""
    msg = _render_429_message({"summary": "Rate limit [tier-1] exceeded", "hint": "retry [soon]"})
    assert r"\[tier-1]" in msg  # bracketed provider text preserved (escaped), not dropped
    assert r"\[soon]" in msg


def test_usage_limit_429_renders_human_friendly_summary_and_reset_window():
    """A ChatGPT usage-limit 429 must read as plain English with a concrete reset
    window, not a raw stringified JSON body."""
    body = {
        "error": {
            "type": "usage_limit_reached",
            "message": "The usage limit has been reached",
            "plan_type": "plus",
            "resets_in_seconds": 7320,  # 2h 2m
        }
    }
    exc = APIStatusError(429, "Error code: 429 - {'error': {...}}", body=body)

    detail = _extract_429_detail(exc)

    assert detail["summary"] == "Usage limit reached on your Plus plan."
    # No raw exception dump leaks into the user-facing text.
    assert "Error code: 429" not in detail["summary"]
    assert "{" not in detail["summary"]
    # The concrete reset window is its own field (own line in the rendered message).
    assert "Resets in 2h 2m" in detail["reset_window"]
    # The raw server detail (type + original message) is preserved for the trail.
    assert "usage_limit_reached" in detail["server_detail"]
    assert "The usage limit has been reached" in detail["server_detail"]


def test_usage_limit_429_recovers_detail_from_stringified_exception():
    """Even when the parsed body is dropped (body=None), the structured detail is
    recovered from the ``Error code: 429 - {...}`` string so the plan + reset
    window + server trail still render."""
    raw = (
        "Error code: 429 - {'error': {'type': 'usage_limit_reached', "
        "'message': 'The usage limit has been reached', 'plan_type': 'plus', "
        "'eligible_promo': None, 'resets_in_seconds': 7320}}"
    )
    exc = APIStatusError(429, raw, body=None)

    detail = _extract_429_detail(exc)

    assert detail["summary"] == "Usage limit reached on your Plus plan."
    assert "Resets in 2h 2m" in detail["reset_window"]
    assert "usage_limit_reached" in detail["server_detail"]
    assert "{" not in detail["summary"]


def test_render_429_message_includes_full_trail():
    """The rendered console message shows summary, reset window, and a dim
    Server: detail line."""
    detail = _extract_429_detail(
        APIStatusError(
            429,
            "Error code: 429",
            body={
                "error": {
                    "type": "usage_limit_reached",
                    "message": "The usage limit has been reached",
                    "plan_type": "plus",
                    "resets_in_seconds": 7320,
                }
            },
        )
    )
    rendered = _render_429_message(detail)

    assert "Usage limit reached on your Plus plan." in rendered
    assert "Resets in 2h 2m" in rendered
    assert "Server:" in rendered
    assert "usage_limit_reached" in rendered


def test_429_without_structured_body_falls_back_to_server_message():
    """Providers that don't ship a structured body still get a clean message
    (the server text), never a truncated traceback."""
    exc = APIStatusError(429, "Too many requests, slow down", body=None)

    detail = _extract_429_detail(exc)

    assert detail["summary"] == "Too many requests, slow down"
    assert detail["hint"]


def test_generic_429_with_body_uses_server_message_not_usage_limit_text():
    """A non-usage-limit 429 keeps the provider's own message rather than being
    rewritten as a usage-limit error."""
    body = {"error": {"type": "rate_limit_exceeded", "message": "Rate limit exceeded"}}
    exc = APIStatusError(429, "Error code: 429", body=body)

    detail = _extract_429_detail(exc)

    assert detail["summary"] == "Rate limit exceeded"
