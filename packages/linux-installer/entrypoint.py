"""PyInstaller entry shim for the Linux pythinker binary.

Delegates to ``pythinker_code.__main__.main`` so the frozen binary behaves
identically to ``python -m pythinker_code`` — same crash-handler install,
proxy normalization, and ``--version`` / ``--help`` short-circuits.

This is the same shim used by the Windows installer; duplicated here so the
PyInstaller spec's ``pathex`` resolution stays simple and unambiguous.
"""

from __future__ import annotations

import sys


def _entrypoint() -> int:
    from pythinker_code.__main__ import main

    result = main()
    if isinstance(result, int):
        return result
    if result is None:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(_entrypoint())
