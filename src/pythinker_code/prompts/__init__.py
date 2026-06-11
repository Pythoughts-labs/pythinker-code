from __future__ import annotations

from pathlib import Path

INIT = (Path(__file__).parent / "init.md").read_text(encoding="utf-8")
COMPACT = (Path(__file__).parent / "compact.md").read_text(encoding="utf-8")
BEST_PRACTICES = (Path(__file__).parent / "best_practices.md").read_text(encoding="utf-8")
GOAL_SET = (Path(__file__).parent / "goal_set.md").read_text(encoding="utf-8")
GOAL_CONTINUATION = (Path(__file__).parent / "goal_continuation.md").read_text(encoding="utf-8")
