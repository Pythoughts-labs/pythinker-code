"""Project-wide Rich configuration helpers."""

from __future__ import annotations

import re
from typing import Final

from rich import _wrap

# Regex used by Rich to compute break opportunities during wrapping.
_DEFAULT_WRAP_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s*\S+\s*")
_CHAR_WRAP_PATTERN: Final[re.Pattern[str]] = re.compile(r".", re.DOTALL)


def enable_character_wrap() -> None:
    """Switch Rich's wrapping logic to break on every character.

    Kept for narrow renderers that explicitly prefer hard folding. Normal TUI
    prose should use Rich's default word-aware wrapping so paragraphs retain
    clean margins and don't split ordinary words mid-line.
    """

    _wrap.re_word = _CHAR_WRAP_PATTERN


def restore_word_wrap() -> None:
    """Restore Rich's default word-based wrapping."""

    _wrap.re_word = _DEFAULT_WRAP_PATTERN


# Keep Rich's default word-aware wrapping globally. Long unbroken tokens still
# fold, but ordinary prose and markdown lists wrap on word boundaries.
restore_word_wrap()
