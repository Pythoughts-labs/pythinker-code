"""`pythinker debug` — active-model wrapper for pythinker-debug."""

from __future__ import annotations

from pythinker_review.cli import debug as upstream_debug

# Importing review installs the active-model resolver used by debug.
from pythinker_code.cli import review as review_wrapper

_REVIEW_CLI = review_wrapper.cli
cli = upstream_debug.app
