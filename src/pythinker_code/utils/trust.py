"""Trust-wrapping primitive for external, untrusted data entering LLM prompts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


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
        safe_content = self.raw_content.replace("</untrusted_data>", "&lt;/untrusted_data&gt;")
        return f'<untrusted_data id="{nonce}">\n{safe_content}\n</untrusted_data>'
