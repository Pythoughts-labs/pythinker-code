from __future__ import annotations

import contextlib
import os
from pathlib import Path


def get_share_dir() -> Path:
    """Get the share directory path."""
    if share_dir := os.getenv("PYTHINKER_SHARE_DIR"):
        share_dir = Path(share_dir)
    else:
        share_dir = Path.home() / ".pythinker"
    share_dir.mkdir(parents=True, exist_ok=True)
    # Harden unconditionally: an older version may have left the dir at 0755, so
    # only tightening on first-create would leave that secret-bearing dir traversable.
    with contextlib.suppress(OSError):
        os.chmod(share_dir, 0o700)
    return share_dir
