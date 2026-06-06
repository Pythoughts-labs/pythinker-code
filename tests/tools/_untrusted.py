"""Test helpers for tools that wrap their output in ``<untrusted_data>`` tags.

The ReadFile and FetchURL tools wrap external content in
``<untrusted_data id="NONCE">...</untrusted_data>`` before returning it to the
LLM, to defend against prompt injection. Tests need to:

1. Verify the wrapper is present (security property).
2. Inspect the inner content for behavioral assertions (line content, etc.).

The two helpers in this module separate those concerns so snapshot tests stay
readable and the wrap-around guarantee is exercised explicitly.
"""

from __future__ import annotations

import re

_OPEN_RE = re.compile(r'^<untrusted_data id="([0-9a-f]{8})">\n')
_CLOSE_RE = re.compile(r"\n</untrusted_data>$", re.DOTALL)


def _as_str(output: str | object) -> str:
    """Coerce ``ToolReturnValue.output`` to ``str`` with a runtime assertion."""
    assert isinstance(output, str), f"expected str output, got {type(output).__name__}"
    return output


def unwrap_untrusted(output: str | object) -> str:
    """Strip the ``<untrusted_data id="...">`` wrapper and return the inner body.

    Accepts the ``str | list[ContentPart]`` union that
    ``ToolReturnValue.output`` exposes, asserting at runtime that the value is
    a plain string.  Raises ``AssertionError`` with a clear message if the
    wrapper is missing or malformed. Tests should use this to keep snapshot
    assertions focused on the underlying file content rather than the random
    nonce.
    """
    text = _as_str(output)
    open_match = _OPEN_RE.match(text)
    assert open_match is not None, f'output is not wrapped in <untrusted_data id="...">:\n{text!r}'
    body_start = open_match.end()
    close_match = _CLOSE_RE.search(text, body_start)
    assert close_match is not None, f"output missing closing </untrusted_data>:\n{text!r}"
    body_end = close_match.start()
    return text[body_start:body_end]


def assert_wrapped(output: str | object) -> str:
    """Assert the output is wrapped in ``<untrusted_data id="...">`` tags.

    Returns the inner body for convenience so callers can chain a single
    helper call into a snapshot assertion::

        assert_wrapped(result.output) == snapshot("hello\\n")

    Raises ``AssertionError`` with a clear message if the wrapper is missing
    or malformed.
    """
    return unwrap_untrusted(output)
