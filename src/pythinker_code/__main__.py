from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO


def _prog_name() -> str:
    return Path(sys.argv[0]).name or "pythinker"


def _maybe_enable_asyncio_tracing() -> None:
    """Diagnostic, off by default. Set ``PYTHINKER_TRACE_ASYNCIO=1`` to start
    tracemalloc early and mirror every RuntimeWarning (e.g. "coroutine ... was
    never awaited") — *with* its allocation traceback — to
    ``~/.pythinker/asyncio-warnings.log``.

    Started here, before any event loop runs, so the allocation site of every
    later coroutine is traced. Capturing to a file makes the traceback survive
    terminal scrollback and stderr redirection.
    """
    import os

    if not os.getenv("PYTHINKER_TRACE_ASYNCIO"):
        return

    import tracemalloc
    import warnings

    tracemalloc.start(25)
    # Make "coroutine ... was never awaited" warnings carry their *creation*
    # stack ("Coroutine created at ...") rather than just the GC site.  This
    # routes through warnings.showwarning below, so the leaked coroutine's
    # origin lands in the log file.  tracemalloc alone does not surface it.
    sys.set_coroutine_origin_tracking_depth(30)
    warnings.simplefilter("always", RuntimeWarning)

    log_path = Path.home() / ".pythinker" / "asyncio-warnings.log"
    _orig_showwarning = warnings.showwarning

    def _showwarning(
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        file: TextIO | None = None,
        line: str | None = None,
    ) -> None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(warnings.formatwarning(message, category, filename, lineno, line))
                fh.write("\n")
        except Exception:
            pass
        return _orig_showwarning(message, category, filename, lineno, file, line)

    warnings.showwarning = _showwarning


def main(argv: Sequence[str] | None = None) -> int | str | None:
    _maybe_enable_asyncio_tracing()
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) == 1 and args[0] in {"--version", "-V"}:
        from pythinker_code.constant import ORGANIZATION, get_version

        print(f"pythinker, version {get_version()} — by {ORGANIZATION}")
        return 0

    from pythinker_code.telemetry.crash import install_crash_handlers, set_phase
    from pythinker_code.utils.proxy import normalize_proxy_env

    # Install excepthook before anything else so startup-phase crashes are captured.
    install_crash_handlers()
    normalize_proxy_env()

    from pythinker_code.cli import cli

    try:
        return cli(args=args, prog_name=_prog_name())
    except SystemExit as exc:
        return exc.code
    finally:
        set_phase("shutdown")


if __name__ == "__main__":
    raise SystemExit(main())
