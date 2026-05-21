"""`pythinker secscan` — active-model wrapper for pythinker-secscan."""

from __future__ import annotations

from pythinker_review.cli import secscan as upstream_secscan

# Importing review installs the active-model resolver used by secscan.
from pythinker_code.cli import review as review_wrapper

_REVIEW_CLI = review_wrapper.cli
cli = upstream_secscan.app
