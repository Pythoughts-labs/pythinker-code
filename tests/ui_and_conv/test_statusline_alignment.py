from __future__ import annotations

import pytest
from prompt_toolkit.utils import get_cwidth

from pythinker_code.config import StatusLineConfig
from pythinker_code.soul import StatusSnapshot
from tests.ui_and_conv.test_statusline import _make_session, _render_card


def _w(line: str) -> int:
    return sum(get_cwidth(c) for c in line)


@pytest.mark.parametrize("width", [120, 80, 50, 36])
def test_card_footer_reserves_last_column(monkeypatch, width):
    """Every footer row stops at columns-1, matching the separator rule, so the
    final cell never wraps on terminals like Windows conhost / PowerShell."""
    session = _make_session(StatusLineConfig())
    session._status_provider = lambda: StatusSnapshot(context_usage=0.297)
    rows = _render_card(session, monkeypatch, width=width).split("\n")
    rule, _line1, line2 = rows[0], rows[1], rows[2]
    assert _w(rule) == width - 1
    # Right-aligned row fills up to (but not past) the reserved last column.
    assert _w(line2) <= width - 1
    assert line2.rstrip() == line2  # flush right: no trailing pad past content
