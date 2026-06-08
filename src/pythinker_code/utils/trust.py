"""Trust-wrapping primitive for external, untrusted data entering LLM prompts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

# Zero-width and bidi-override characters used to smuggle hidden instructions past a
# human reviewer (the highest-confidence injection signal). Stripped from all untrusted
# content before it reaches the model. Shared with the memory scanner, which BLOCKS on
# them when deciding what to persist; tool-output ingress only STRIPS them.
INVISIBLE_CHARS = frozenset(
    chr(c)
    for c in (
        0x200B,
        0x200C,
        0x200D,
        0x2060,
        0xFEFF,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
    )
)
_INVISIBLE_TRANSLATION = dict.fromkeys((ord(c) for c in INVISIBLE_CHARS), None)


@dataclass(frozen=True)
class UntrustedData:
    """Marks a string as originating from an external, untrusted source.

    Call render_for_prompt() before injecting the content into any LLM prompt.
    The runtime nonce prevents the model from constructing a matching opening
    tag. The closing-tag escape prevents content from breaking out of the block.
    """

    raw_content: str

    def render_for_prompt(self) -> str:
        nonce = uuid.uuid4().hex[:8]
        # Neutralize invisible/bidi unicode before wrapping. Strip, do not block:
        # legitimate external content (security advisories, this repo's own test
        # fixtures) may contain visible "injection-like" prose, which the wrapper
        # marks as data — only the invisible smuggling vector is removed outright.
        cleaned = self.raw_content.translate(_INVISIBLE_TRANSLATION)
        safe_content = cleaned.replace("</untrusted_data>", "&lt;/untrusted_data&gt;")
        return f'<untrusted_data id="{nonce}">\n{safe_content}\n</untrusted_data>'
