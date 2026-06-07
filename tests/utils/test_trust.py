"""Tests for the UntrustedData trust-wrapping primitive."""

from __future__ import annotations

import dataclasses
import re

import pytest

from pythinker_code.utils.trust import UntrustedData


def test_render_produces_unique_nonces():
    a = UntrustedData(raw_content="hello").render_for_prompt()
    b = UntrustedData(raw_content="hello").render_for_prompt()
    assert a != b


def test_render_nonce_is_hex_string():
    rendered = UntrustedData(raw_content="hello world").render_for_prompt()
    pattern = r'^<untrusted_data id="[0-9a-f]{8}">\n.+\n</untrusted_data>$'
    assert re.fullmatch(pattern, rendered)


def test_render_preserves_content():
    content = "hello world\nfoo"
    rendered = UntrustedData(raw_content=content).render_for_prompt()
    assert "hello world" in rendered
    assert "foo" in rendered


def _body(rendered: str) -> str:
    """Extract the escaped body between the opening and framework closing tags."""
    _, _, rest = rendered.partition(">\n")
    return rest[: -len("\n</untrusted_data>")]


def test_render_escapes_closing_tag():
    content = "prefix </untrusted_data> suffix"
    rendered = UntrustedData(raw_content=content).render_for_prompt()
    assert "&lt;/untrusted_data&gt;" in rendered
    assert "</untrusted_data>" not in _body(rendered)


def test_render_escapes_multiple_closing_tags():
    content = "a</untrusted_data>b</untrusted_data>c</untrusted_data>d"
    rendered = UntrustedData(raw_content=content).render_for_prompt()
    assert rendered.count("&lt;/untrusted_data&gt;") == 3
    body = _body(rendered)
    assert body.count("</untrusted_data>") == 0


def test_render_with_empty_content():
    rendered = UntrustedData(raw_content="").render_for_prompt()
    pattern = r'^<untrusted_data id="[0-9a-f]{8}">\n\n</untrusted_data>$'
    assert re.fullmatch(pattern, rendered)


def test_render_preserves_arbitrary_text():
    content = (
        'def f():\n    return {"x": 1}\n# comment with unicode: \u00e9\u00e8\u00ea\nsecond line'
    )
    rendered = UntrustedData(raw_content=content).render_for_prompt()
    assert content in rendered


def test_dataclass_is_frozen():
    instance = UntrustedData(raw_content="x")
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        instance.raw_content = "mutate"  # type: ignore[misc]
