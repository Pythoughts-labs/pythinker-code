from __future__ import annotations

import contextlib
import os
from pathlib import Path


def get_share_dir(*, create: bool = True) -> Path:
    """Get the share directory path.

    Creates and hardens the directory by default. Pass ``create=False`` to
    resolve the path without any filesystem side effect — needed by read-only
    callers (e.g. ``pythinker info``) that must not materialize ``~/.pythinker``
    just to look something up.
    """
    if share_dir := os.getenv("PYTHINKER_SHARE_DIR"):
        share_dir = Path(share_dir)
    else:
        share_dir = Path.home() / ".pythinker"
    if not create:
        return share_dir
    share_dir.mkdir(parents=True, exist_ok=True)
    # Harden unconditionally: an older version may have left the dir at 0755, so
    # only tightening on first-create would leave that secret-bearing dir traversable.
    with contextlib.suppress(OSError):
        os.chmod(share_dir, 0o700)
    return share_dir
