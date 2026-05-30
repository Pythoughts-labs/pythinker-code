# TUI Markdown + Report Contract-Hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Markdown + security/scan-report bug-class catalog into an aggressive, deterministic regression suite that the existing Rich + prompt_toolkit stack passes, fixing only the one structural defect (nested-report-fence promotion) the tests expose.

**Architecture:** Lead phase of `docs/superpowers/specs/2026-05-29-tui-renderer-contract-hardening-design.md`. We do **not** build a renderer. We add Tier-1 contract tests (capture + assertion) under `tests/ui_and_conv/`, characterize the existing regex repair pipeline (pin, don't refactor), ground report tests in the real 92-finding fixture, and apply exactly one source fix (AST-based report-fence extraction in `report.py`) gated by a failing test.

**Tech Stack:** Python 3.12+, Rich 15, prompt_toolkit 3, markdown-it-py, pytest (`asyncio_mode = auto`), `uv`. Run tests with `uv run pytest …` (fallback: `.venv/bin/python -m pytest …`).

**Spec reference:** `docs/superpowers/specs/2026-05-29-tui-renderer-contract-hardening-design.md` §6–§8.

**Source files in play:**
- `src/pythinker_code/ui/shell/components/report.py` — report dataclasses, `render_report`, `parse_report_block`, `render_agent_body`, `has_report_block` (the **only** file we modify, in Task 9)
- `src/pythinker_code/ui/shell/components/markdown.py` — `pythinker_markdown`, regex table-repair pipeline, `PythinkerMarkdownStream`, `markdown_commit_boundary` (characterized, **not** modified)
- `src/pythinker_code/utils/rich/markdown.py` — Rich Markdown subclass (exercised, not modified)

**Test files created:**
- `tests/ui_and_conv/_md_contract_helpers.py` — shared capture/idempotency/param helpers
- `tests/ui_and_conv/test_md_table_contract.py` — table bug classes (spec area 3)
- `tests/ui_and_conv/test_md_repair_characterization.py` — pin the regex repair pipeline
- `tests/ui_and_conv/test_md_color_contract.py` — color-bleed / ANSI (spec area 4)
- `tests/ui_and_conv/test_report_realdata.py` — report render grounded in `security-scan-findings.json`
- `tests/ui_and_conv/test_report_fence_nesting.py` — H1 (the one real fix)
- `tests/ui_and_conv/test_md_stream_idempotency.py` — H2 + H3

**Methodology note (read before starting):** This plan mixes three test kinds. Know which you're writing:
- **Characterization** (pin): the behavior already exists; the test passes on first run and locks it in. "Expected: FAIL" does **not** apply — expected is PASS, and that is the point.
- **Contract** (guard): asserts a spec requirement the stack *should* already meet; expected PASS. If it FAILS you've found a real bug — stop and surface it, don't paper over it.
- **Hypothesis** (H1/H2/H3): written to *try* to reproduce a suspected defect. H1 is expected to FAIL first (bug present) then PASS after the fix. H2/H3 may PASS immediately (non-reproduction) — record that and keep them as guards.

---

### Task 1: Shared contract-test helpers

**Files:**
- Create: `tests/ui_and_conv/_md_contract_helpers.py`
- Test: `tests/ui_and_conv/test_md_contract_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui_and_conv/test_md_contract_helpers.py
"""Smoke test for the shared Markdown/report contract helpers."""

from __future__ import annotations

from rich.text import Text

from tests.ui_and_conv._md_contract_helpers import (
    THEMES,
    WIDTHS,
    render_ansi,
    render_plain,
    render_twice_identical,
)


def test_helpers_capture_and_compare():
    assert "hello" in render_plain(Text("hello"), width=40)
    # truecolor capture keeps SGR codes; a red fg emits the 31-family sequence.
    assert "\x1b[" in render_ansi(Text("hi", style="red"), width=40)
    assert render_twice_identical(lambda: Text("stable")) is True
    assert WIDTHS and THEMES  # parametrization sources are non-empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/ui_and_conv/test_md_contract_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError: tests.ui_and_conv._md_contract_helpers`

- [ ] **Step 3: Write the helper module**

```python
# tests/ui_and_conv/_md_contract_helpers.py
"""Shared helpers for Markdown + report contract tests.

DRY home for the two capture modes the repo already uses (plain text and
ANSI-preserving) plus an idempotency comparator. Mirrors the console
configuration in tests/ui_and_conv/test_tui_render_snapshots.py and
tests/ui_and_conv/test_report.py so captured output matches the rest of the
suite.
"""

from __future__ import annotations

from typing import Callable

from rich.console import Console, RenderableType

# Widths that exercise reflow boundaries: very narrow, a normal width, and an
# exactly-typical report width. Add the exact-full-width case per test.
WIDTHS: tuple[int, ...] = (24, 40, 80)
THEMES: tuple[str, ...] = ("dark", "light")


def render_plain(renderable: RenderableType, *, width: int = 80) -> str:
    """Capture *renderable* as plain text (no color), like test_report._plain."""
    console = Console(width=width, no_color=True, legacy_windows=False)
    with console.capture() as cap:
        console.print(renderable)
    return cap.get()


def render_ansi(renderable: RenderableType, *, width: int = 80) -> str:
    """Capture *renderable* keeping ANSI escapes, like test_tui_render_snapshots._ansi."""
    console = Console(
        width=width,
        record=True,
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )
    console.print(renderable)
    return console.export_text(styles=True)


def render_twice_identical(build: Callable[[], RenderableType], *, width: int = 80) -> bool:
    """Render a freshly-built renderable twice; True iff byte-identical.

    `build` returns a NEW renderable each call so we test render determinism,
    not object identity.
    """
    return render_ansi(build(), width=width) == render_ansi(build(), width=width)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/ui_and_conv/test_md_contract_helpers.py -v`
Expected: PASS (2 lines of output, 1 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/ui_and_conv/_md_contract_helpers.py tests/ui_and_conv/test_md_contract_helpers.py
git commit -m "test(tui): add shared markdown/report contract helpers"
```

---

### Task 2: Table contract — piped inline code & escaped pipes (spec area 3)

**Files:**
- Create: `tests/ui_and_conv/test_md_table_contract.py`
- Test: same file

- [ ] **Step 1: Write the contract test**

```python
# tests/ui_and_conv/test_md_table_contract.py
"""Tier-1 contract tests for Markdown table rendering (spec area 3).

Each test names the bug class it guards. These assert the EXISTING stack
(pythinker_markdown over markdown-it + Rich) already meets the contract; a
failure is a real regression to surface, not to silence.
"""

from __future__ import annotations

import pytest

from pythinker_code.ui.shell.components.markdown import pythinker_markdown
from tests.ui_and_conv._md_contract_helpers import render_plain


def test_table_with_piped_inline_code_keeps_columns():
    """Bug class: 'tables breaking on piped inline code'."""
    md = (
        "| Expr | Meaning |\n"
        "| --- | --- |\n"
        "| `a | b` | bitwise or |\n"
        "| plain | text |\n"
    )
    out = render_plain(pythinker_markdown(md), width=80)
    # Both data rows survive as a table (cell contents present, not collapsed
    # into a single prose paragraph).
    assert "bitwise or" in out
    assert "plain" in out
    assert "text" in out


def test_table_with_escaped_pipes_keeps_literal_pipe():
    """Bug class: escaped pipe must render as a literal '|', not split a cell."""
    md = "| Col |\n| --- |\n| a \\| b |\n"
    out = render_plain(pythinker_markdown(md), width=80)
    assert "a | b" in out or "a \\| b" not in out  # literal pipe preserved
    assert "Col" in out
```

- [ ] **Step 2: Run to verify it passes (contract already met)**

Run: `uv run pytest tests/ui_and_conv/test_md_table_contract.py -v`
Expected: PASS. If either FAILS, you've found a live table bug — stop and report it against spec area 3 before continuing.

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_md_table_contract.py
git commit -m "test(tui): guard tables against piped/escaped inline code"
```

---

### Task 3: Table contract — empty headers, long cells, narrow widths (spec area 3)

**Files:**
- Modify: `tests/ui_and_conv/test_md_table_contract.py`

- [ ] **Step 1: Append the parametrized contract tests**

```python
# append to tests/ui_and_conv/test_md_table_contract.py
from tests.ui_and_conv._md_contract_helpers import WIDTHS  # noqa: E402


def test_table_empty_header_cell_does_not_mislabel():
    """Bug class: 'empty header cells mislabeled in narrow stacked layout'."""
    md = "| | Value |\n| --- | --- |\n| key | 42 |\n"
    out = render_plain(pythinker_markdown(md), width=30)
    assert "Value" in out
    assert "key" in out
    assert "42" in out


@pytest.mark.parametrize("width", WIDTHS)
def test_table_long_cell_wraps_without_dropping_content(width):
    """Bug class: very long cells at narrow widths must wrap, not truncate."""
    long_cell = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    md = f"| Name | Note |\n| --- | --- |\n| item | {long_cell} |\n"
    out = render_plain(pythinker_markdown(md), width=width)
    # Every word of the long cell survives somewhere in the wrapped output.
    for word in long_cell.split():
        assert word in out, f"word {word!r} dropped at width={width}"
```

- [ ] **Step 2: Run to verify they pass**

Run: `uv run pytest tests/ui_and_conv/test_md_table_contract.py -v`
Expected: PASS (5 tests). A FAIL on the width-parametrized test is a real reflow bug — surface it.

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_md_table_contract.py
git commit -m "test(tui): guard table empty-header and long-cell wrapping"
```

---

### Task 4: Color-bleed contract — border vs inline-code color (spec area 4)

**Files:**
- Create: `tests/ui_and_conv/test_md_color_contract.py`

- [ ] **Step 1: Write the contract test**

```python
# tests/ui_and_conv/test_md_color_contract.py
"""Tier-1 ANSI/color contract tests (spec area 4).

Uses the truecolor-preserving capture so we can assert on SGR sequences,
exactly like tests/ui_and_conv/test_tui_render_snapshots.py.
"""

from __future__ import annotations

from pythinker_code.ui.shell.components.markdown import pythinker_markdown
from pythinker_code.ui.theme import get_markdown_colors
from tests.ui_and_conv._md_contract_helpers import render_ansi


def _sgr_fg(hexcolor: str) -> str:
    """Build the truecolor foreground SGR fragment for a #rrggbb color."""
    h = hexcolor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"38;2;{r};{g};{b}"


def test_code_block_border_does_not_use_inline_code_color():
    """Bug class: 'border colors inheriting code-span color'.

    The bordered code block frame uses code_block_border; inline code uses
    inline_code. They must be distinct colors, and the captured frame must not
    paint the border in the inline-code color.
    """
    colors = get_markdown_colors("dark")
    assert colors.code_block_border != colors.inline_code, (
        "precondition: palette must distinguish border from inline code"
    )
    md = "Here is `inline` and a block:\n\n```python\nx = 1\n```\n"
    coloured = render_ansi(pythinker_markdown(md), width=60)
    # The rounded frame characters must not carry the inline-code foreground.
    inline_fg = _sgr_fg(colors.inline_code)
    for frame_char in ("╭", "╰", "─"):
        idx = coloured.find(frame_char)
        if idx == -1:
            continue
        window = coloured[max(0, idx - 24) : idx]
        assert inline_fg not in window, "border frame inherited inline-code color"
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/ui_and_conv/test_md_color_contract.py -v`
Expected: PASS. A FAIL means the frame really is bleeding the inline-code color — a genuine area-4 bug to surface.

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_md_color_contract.py
git commit -m "test(tui): guard code-block border against inline-code color bleed"
```

---

### Task 5: Streaming table commits atomically — no stale partial table (spec area 3)

**Files:**
- Create: `tests/ui_and_conv/test_md_stream_idempotency.py`

- [ ] **Step 1: Write the contract test**

```python
# tests/ui_and_conv/test_md_stream_idempotency.py
"""Streaming-boundary contract + idempotency/divergence hypotheses (H2, H3)."""

from __future__ import annotations

from pythinker_code.ui.shell.components.markdown import (
    PythinkerMarkdownStream,
    markdown_commit_boundary,
    pythinker_markdown,
)
from tests.ui_and_conv._md_contract_helpers import render_ansi, render_plain


def _drain(chunks: list[str]) -> list[str]:
    """Feed chunks to the stream; return the ordered list of committed slices."""
    stream = PythinkerMarkdownStream()
    committed: list[str] = []
    for chunk in chunks:
        ready = stream.push(chunk)
        if ready:
            committed.append(ready)
    tail = stream.flush()
    if tail:
        committed.append(tail)
    return committed


def test_streaming_table_is_not_committed_mid_row():
    """Bug class: 'stale bordered tables left in scrollback while streaming'.

    A table streamed one line at a time must not have a partial (header-only or
    header+delimiter-only) slice committed as a finished block: the committer
    keeps the last top-level block mutable until a following block begins.
    """
    full = "Intro paragraph.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nAfter.\n"
    # stream character-by-character to maximize the chance of a mid-table commit
    committed = _drain(list(full))
    # No committed slice may end in the middle of the table (i.e. contain the
    # delimiter row but not the closing blank line + following block).
    for slice_ in committed[:-1]:
        if "---" in slice_:
            assert slice_.rstrip().endswith("|") is False or "After" in "".join(committed), (
                "a partial table row was committed before the table closed"
            )
    # Reassembled stream equals the original (no loss, no duplication).
    assert "".join(committed) == full
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/ui_and_conv/test_md_stream_idempotency.py::test_streaming_table_is_not_committed_mid_row -v`
Expected: PASS. A FAIL is a real streaming-commit bug — surface it.

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_md_stream_idempotency.py
git commit -m "test(tui): guard streamed tables against mid-row commit"
```

---

### Task 6: H2 (offset divergence) + H3 (idempotency) hypotheses

**Files:**
- Modify: `tests/ui_and_conv/test_md_stream_idempotency.py`

- [ ] **Step 1: Append the hypothesis tests**

```python
# append to tests/ui_and_conv/test_md_stream_idempotency.py

# Glued prose+table that forces the regex repair pipeline to fire on a slice
# whose commit boundary was computed on the RAW (un-repaired) text.
_GLUED = "Findings Medium| # | File |\n| --- | --- |\n| 1 | a.py |\n| 2 | b.py |\n\nNext.\n"


def test_h2_stream_slices_reassemble_without_duplicate_rows():
    """H2: commit offsets are computed on raw text while the renderer transforms
    repaired text. Try to reproduce a duplicate/stale row. Expected: PASS
    (non-reproduction). If this FAILS, H2 is confirmed — capture the case.
    """
    committed = _drain(list(_GLUED))
    reassembled = "".join(committed)
    assert reassembled == _GLUED
    # Render each committed slice; 'a.py' and 'b.py' must each appear exactly
    # once across the rendered stream (no row duplicated by the repair pass).
    rendered = "".join(render_plain(pythinker_markdown(s)) for s in committed)
    assert rendered.count("a.py") == 1
    assert rendered.count("b.py") == 1


def test_h3_report_and_table_render_is_idempotent():
    """H3: rendering the same markdown twice yields byte-identical output."""
    md = "## Title\n\n| A | B |\n| --- | --- |\n| 1 | `x|y` |\n\nDone.\n"
    first = render_ansi(pythinker_markdown(md), width=70)
    second = render_ansi(pythinker_markdown(md), width=70)
    assert first == second
```

- [ ] **Step 2: Run the hypotheses**

Run: `uv run pytest tests/ui_and_conv/test_md_stream_idempotency.py -v`
Expected: PASS for both. **If `test_h2_...` FAILS**, H2 is reproduced: do NOT patch blindly — record the failing input in the spec's §12 R-notes and open a focused fix task. If it PASSES, annotate the spec: "H2 did not reproduce; kept as guard."

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_md_stream_idempotency.py
git commit -m "test(tui): add stream offset-divergence and idempotency guards"
```

---

### Task 7: Characterize the regex table-repair pipeline (pin, don't refactor)

**Files:**
- Create: `tests/ui_and_conv/test_md_repair_characterization.py`

- [ ] **Step 1: Write characterization tests (they pass on first run)**

```python
# tests/ui_and_conv/test_md_repair_characterization.py
"""Characterization tests that PIN the existing regex Markdown-repair pipeline.

These lock in current correct behavior of _repair_crammed_markdown_tables,
_normalize_markdown_tables, and the priority-matrix detector so any future
change that alters them is caught. Per the spec (§2), this pipeline is pinned,
NOT refactored. If a characterized output looks imperfect, mark it with a
`# pinned: imperfect` note and a follow-up — do not change source here.
"""

from __future__ import annotations

from pythinker_code.ui.shell.components.markdown import (
    _normalize_markdown_tables,
    _repair_crammed_markdown_tables,
    pythinker_markdown,
)
from tests.ui_and_conv._md_contract_helpers import render_plain


def test_glued_heading_and_table_header_is_split():
    """Model output that glues a section title to a table header gets split so
    the table renders as a table, not crammed prose."""
    glued = "Medium| # | File |\n| --- | --- |\n| 1 | a.py |\n"
    repaired = _repair_crammed_markdown_tables(glued)
    # The heading is separated onto its own line before the table header.
    assert repaired.splitlines()[0].strip() == "Medium"
    out = render_plain(pythinker_markdown(glued), width=60)
    assert "Medium" in out
    assert "a.py" in out
    assert "File" in out


def test_crammed_data_rows_on_delimiter_line_are_rechunked():
    """Data cells crammed onto the delimiter line are split into rows."""
    crammed = "| # | File |\n| --- | --- || 1 | a.py || 2 | b.py |\n"
    normalized = _normalize_markdown_tables(crammed)
    out = render_plain(pythinker_markdown(normalized), width=60)
    assert "a.py" in out
    assert "b.py" in out


def test_wellformed_table_is_passed_through_unchanged_in_render():
    """A clean table renders with both rows and the header intact."""
    clean = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n"
    out = render_plain(pythinker_markdown(clean), width=40)
    for token in ("A", "B", "1", "2", "3", "4"):
        assert token in out
```

- [ ] **Step 2: Run to verify they pass (pinning current behavior)**

Run: `uv run pytest tests/ui_and_conv/test_md_repair_characterization.py -v`
Expected: PASS (3 tests). If one FAILS, your understanding of current behavior is wrong — read the source in `components/markdown.py` and adjust the *assertion* to match reality (this is characterization; the source is ground truth).

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_md_repair_characterization.py
git commit -m "test(tui): pin regex markdown table-repair behavior"
```

---

### Task 8: Report rendering grounded in the real 92-finding fixture (spec area 3)

**Files:**
- Create: `tests/ui_and_conv/test_report_realdata.py`
- Read-only fixture: `security-scan-findings.json` (repo root)

- [ ] **Step 1: Write the raw→Report transform + render contract test**

```python
# tests/ui_and_conv/test_report_realdata.py
"""Report rendering grounded in the real security-scan-findings.json fixture.

The fixture is RAW scanner shape (filePath / severity UPPERCASE / vulnSlug /
title / description / lineNumbers / recommendation / confidence). report.py
consumes the Report shape (title / severity lowercase / location / body). The
transform below encodes the contract: case-fold severity, fold filePath +
lineNumbers into location, fold description + recommendation into body. If a
production transform exists (see Task 12), Task 12 asserts they agree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pythinker_code.ui.shell.components.report import (
    Report,
    ReportFinding,
    Severity,
    render_report,
)
from tests.ui_and_conv._md_contract_helpers import THEMES, WIDTHS, render_plain

_FIXTURE = Path(__file__).resolve().parents[2] / "security-scan-findings.json"
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}


def _location(raw: dict) -> str | None:
    path = raw.get("filePath")
    if not isinstance(path, str) or not path:
        return None
    lines = raw.get("lineNumbers") or []
    if isinstance(lines, list) and lines:
        return f"{path}:{lines[0]}"
    return path


def _body(raw: dict) -> str:
    parts = []
    if raw.get("description"):
        parts.append(str(raw["description"]))
    if raw.get("recommendation"):
        parts.append(f"**Fix:** {raw['recommendation']}")
    return "\n\n".join(parts)


def _to_finding(raw: dict) -> ReportFinding:
    severity = str(raw["severity"]).lower()
    assert severity in _VALID_SEVERITIES, f"unexpected severity {raw['severity']!r}"
    return ReportFinding(
        title=str(raw["title"]),
        severity=severity,  # type: ignore[arg-type]
        location=_location(raw),
        body=_body(raw),
    )


def _load_report(limit: int | None = None) -> Report:
    raw = json.loads(_FIXTURE.read_text())
    findings = tuple(_to_finding(r) for r in (raw[:limit] if limit else raw))
    return Report(title="Security Scan", scope=f"{len(findings)} findings", findings=findings)


def test_fixture_transforms_to_valid_report():
    report = _load_report()
    assert len(report.findings) == 92
    # Every transformed severity is a valid Report severity.
    seen: set[Severity] = {f.severity for f in report.findings}
    assert seen <= _VALID_SEVERITIES
    assert "critical" in seen  # the fixture contains CRITICAL findings


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_real_report_renders_across_theme_and_width(theme, width):
    out = render_plain(render_report(_load_report(limit=12), theme=theme), width=width)
    assert "Security Scan" in out
    # The summary tally line names at least one present severity.
    assert any(sev in out for sev in ("critical", "high", "medium", "low", "info"))


def test_real_report_shows_locations_and_titles():
    out = render_plain(render_report(_load_report(limit=5)), width=100)
    report = _load_report(limit=5)
    for finding in report.findings:
        assert finding.title[:20] in out
        if finding.location:
            # the file path portion of the first finding's location appears
            assert finding.location.split(":")[0].split("/")[-1] in out
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/ui_and_conv/test_report_realdata.py -v`
Expected: PASS. If `test_fixture_transforms_to_valid_report` FAILS on an unexpected severity, the fixture contains a value outside the five-severity set — extend `_VALID_SEVERITIES` mapping only if the production transform does the same; otherwise surface it.

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_report_realdata.py
git commit -m "test(tui): render reports from the real security-scan fixture"
```

---

### Task 9: H1 — nested report-fence must not be promoted (THE fix)

**Files:**
- Create: `tests/ui_and_conv/test_report_fence_nesting.py`
- Modify: `src/pythinker_code/ui/shell/components/report.py`

- [ ] **Step 1: Write the failing hypothesis test**

```python
# tests/ui_and_conv/test_report_fence_nesting.py
"""H1: a ```report block shown INSIDE an outer documentation fence must not be
promoted to a report. The flat _REPORT_FENCE_RE regex cannot see fence nesting;
an AST walk over top-level fence tokens structurally can.
"""

from __future__ import annotations

from pythinker_code.ui.shell.components.report import has_report_block, render_agent_body
from tests.ui_and_conv._md_contract_helpers import render_plain

# A 4-backtick outer fence whose body is a literal ```report example. markdown-it
# parses the outer fence as ONE token, so the inner block is documentation text,
# not a real report.
_NESTED = (
    "Here is how to emit a report:\n\n"
    "````markdown\n"
    "```report\n"
    '{"title": "Example", "findings": [{"title": "x", "severity": "high"}]}\n'
    "```\n"
    "````\n"
)


def test_nested_report_fence_is_not_detected():
    assert has_report_block(_NESTED) is False


def test_nested_report_fence_renders_as_documentation_not_report():
    out = render_plain(render_agent_body(_NESTED))
    # The inner block stays verbatim documentation; it is NOT promoted to the
    # report renderer (which would drop the JSON and print a tally).
    assert '"title": "Example"' in out
    assert "1 high" not in out  # no report tally emitted


def test_top_level_report_fence_still_promoted():
    """Regression guard: the real top-level case must keep working."""
    text = (
        "Intro.\n\n```report\n"
        '{"title": "Real", "findings": [{"title": "bug", "severity": "medium"}]}\n'
        "```\n"
    )
    out = render_plain(render_agent_body(text))
    assert "Real" in out
    assert "1 medium" in out
    assert '"severity"' not in out  # rendered as a report, not raw JSON
```

- [ ] **Step 2: Run to verify the nesting tests FAIL**

Run: `uv run pytest tests/ui_and_conv/test_report_fence_nesting.py -v`
Expected: `test_nested_report_fence_is_not_detected` and `test_nested_report_fence_renders_as_documentation_not_report` **FAIL** (the flat regex promotes the inner block). `test_top_level_report_fence_still_promoted` PASSES.

- [ ] **Step 3: Replace flat-regex extraction with an AST walk in `report.py`**

Edit `src/pythinker_code/ui/shell/components/report.py`.

3a. Add a lazy markdown-it parser and a top-level report-fence iterator near the other helpers (after `_DOT = "●"`):

```python
# A markdown-it parser is reused so report-fence extraction is fence-aware: a
# ```report block nested inside an outer fence is part of that outer fence's
# content and is therefore NOT a top-level fence token (Principle #5: parse,
# don't pattern-match).
_md_parser: Any = None


def _get_report_parser() -> Any:
    global _md_parser
    if _md_parser is None:
        from markdown_it import MarkdownIt

        _md_parser = MarkdownIt()
    return _md_parser


def _iter_report_payloads(text: str) -> list[tuple[int, int, str]]:
    """Yield (start_line, end_line, payload) for each TOP-LEVEL ```report fence.

    Line indices are 0-based half-open ([start, end)) into ``text``'s lines,
    matching markdown-it ``token.map``. Nested fences never appear as top-level
    ``fence`` tokens, so they are structurally excluded.
    """
    md = _get_report_parser()
    blocks: list[tuple[int, int, str]] = []
    for token in md.parse(text):
        if (
            token.type == "fence"
            and token.level == 0
            and token.map is not None
            and token.info.strip() == "report"
        ):
            blocks.append((token.map[0], token.map[1], token.content))
    return blocks
```

3b. Rewrite `has_report_block` to use the AST iterator:

```python
def has_report_block(text: str) -> bool:
    """Whether *text* contains at least one well-formed top-level ` ```report ` block."""
    return any(parse_report_block(payload) is not None for _, _, payload in _iter_report_payloads(text))
```

3c. Rewrite `render_agent_body` to slice by line map instead of regex cursor:

```python
def render_agent_body(text: str, *, theme: ThemeName | None = None) -> RenderableType:
    """Render assistant text, promoting top-level ` ```report ` blocks to reports.

    Non-report text renders via :func:`pythinker_markdown`; a valid top-level
    report block renders via :func:`render_report`; an invalid or nested block is
    left in place so the surrounding markdown shows it as an ordinary code block.
    """
    lines = text.splitlines(keepends=True)
    segments: list[RenderableType] = []
    cursor = 0  # line index
    for start, end, payload in _iter_report_payloads(text):
        report = parse_report_block(payload)
        if report is None:
            continue  # malformed — leave it for the markdown renderer
        before = "".join(lines[cursor:start]).strip("\n")
        if before:
            segments.append(pythinker_markdown(before))
        segments.append(render_report(report, theme=theme))
        cursor = end

    if not segments:
        return pythinker_markdown(text)

    rest = "".join(lines[cursor:]).strip("\n")
    if rest:
        segments.append(pythinker_markdown(rest))

    spaced: list[RenderableType] = []
    for i, segment in enumerate(segments):
        if i:
            spaced.append(Text(""))
        spaced.append(segment)
    return Group(*spaced)
```

3d. Delete the now-unused `_REPORT_FENCE_RE` regex and its `import re` if `re` is unused elsewhere in the file. Check first:

Run: `grep -n "re\\.\|_REPORT_FENCE_RE\|^import re" src/pythinker_code/ui/shell/components/report.py`
- Remove the `_REPORT_FENCE_RE = re.compile(...)` block.
- Remove `import re` only if `grep` shows no other `re.` usage.

- [ ] **Step 4: Run the full report suite to verify the fix and no regressions**

Run: `uv run pytest tests/ui_and_conv/test_report_fence_nesting.py tests/ui_and_conv/test_report.py -v`
Expected: ALL PASS — the two nesting tests now pass, and every pre-existing test in `test_report.py` (including `test_render_agent_body_promotes_report_fence`, `test_render_agent_body_invalid_fence_falls_back_to_markdown`, and `test_streaming_commit_keeps_report_fence_atomic_and_renders`) still passes.

- [ ] **Step 5: Type-check the modified file**

Run: `uv run pyright src/pythinker_code/ui/shell/components/report.py`
Expected: no new errors. (`token`/parser are typed `Any`; that is intentional for the untyped markdown-it surface, consistent with `components/markdown.py`.)

- [ ] **Step 6: Commit**

```bash
git add tests/ui_and_conv/test_report_fence_nesting.py src/pythinker_code/ui/shell/components/report.py
git commit -m "fix(tui): extract report fences via AST so nested blocks aren't promoted"
```

---

### Task 10: Screen-authority guard for the lead-phase modules (spec principle 1)

**Files:**
- Create: `tests/ui_and_conv/test_md_render_authority.py`

- [ ] **Step 1: Write the static guard test**

```python
# tests/ui_and_conv/test_md_render_authority.py
"""Screen-authority discipline (spec principle 1) for the lead-phase modules.

These renderers must return Rich renderables, never write to the terminal
directly. A bare print()/sys.stdout.write in a renderer bypasses the Live
screen model and causes the duplicate-scrollback / corruption bug classes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "pythinker_code" / "ui" / "shell" / "components"
_GUARDED = ["report.py", "markdown.py"]


@pytest.mark.parametrize("filename", _GUARDED)
def test_no_direct_terminal_writes_in_renderer(filename):
    tree = ast.parse((_SRC / filename).read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                offenders.append(f"print() at line {node.lineno}")
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "write"
                and isinstance(func.value, ast.Attribute)
                and func.value.attr in {"stdout", "stderr"}
            ):
                offenders.append(f"std*.write at line {node.lineno}")
    assert not offenders, f"{filename} bypasses the screen model: {offenders}"
```

- [ ] **Step 2: Run to verify it passes**

Run: `uv run pytest tests/ui_and_conv/test_md_render_authority.py -v`
Expected: PASS (2 tests). A FAIL means a renderer writes to the terminal directly — surface it.

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_md_render_authority.py
git commit -m "test(tui): forbid direct terminal writes in markdown/report renderers"
```

---

### Task 11: Bug-class → test registry doc + full-suite gate

**Files:**
- Create: `tests/ui_and_conv/README_contract_registry.md`

- [ ] **Step 1: Write the 1:1 registry mapping (spec §8 lead-phase rows)**

```markdown
# Markdown + Report contract test registry (lead phase)

Maps spec bug classes to the test that guards them. Tier 1 = deterministic
capture. See docs/superpowers/specs/2026-05-29-tui-renderer-contract-hardening-design.md §8.

| Spec area | Bug class | Test | Tier |
|---|---|---|---|
| 3 Markdown | table breaks on piped inline code | test_md_table_contract::test_table_with_piped_inline_code_keeps_columns | T1 |
| 3 Markdown | escaped pipe splits cell | test_md_table_contract::test_table_with_escaped_pipes_keeps_literal_pipe | T1 |
| 3 Markdown | empty header mislabeled | test_md_table_contract::test_table_empty_header_cell_does_not_mislabel | T1 |
| 3 Markdown | long cell wrap loss | test_md_table_contract::test_table_long_cell_wraps_without_dropping_content | T1 |
| 3 Markdown | stale streamed table | test_md_stream_idempotency::test_streaming_table_is_not_committed_mid_row | T1 |
| 3 Markdown | nested report-fence promoted | test_report_fence_nesting::* | T1 |
| 4 ANSI | border inherits code-span color | test_md_color_contract::test_code_block_border_does_not_use_inline_code_color | T1 |
| 3 Markdown | report render on real data | test_report_realdata::* | T1 |
| 1 Stability | render idempotency | test_md_stream_idempotency::test_h3_report_and_table_render_is_idempotent | T1 |
| 1 Stability | offset divergence (H2) | test_md_stream_idempotency::test_h2_stream_slices_reassemble_without_duplicate_rows | T1 |
| 1 Stability | screen-authority | test_md_render_authority::test_no_direct_terminal_writes_in_renderer | T1 |
| repair | regex pipeline pinned | test_md_repair_characterization::* | T1 |
```

- [ ] **Step 2: Run the full lead-phase suite + existing UI suite (no regressions)**

Run: `uv run pytest tests/ui_and_conv -v`
Expected: all green, including the pre-existing tests. Capture the summary line (e.g. `N passed`).

- [ ] **Step 3: Run lint + type-check on changed source**

Run: `uv run ruff check src/pythinker_code/ui/shell/components/report.py tests/ui_and_conv && uv run pyright src/pythinker_code/ui/shell/components/report.py`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add tests/ui_and_conv/README_contract_registry.md
git commit -m "docs(tui): add markdown/report contract test registry"
```

---

### Task 12: Reconcile with the production raw→Report transform (investigation)

**Files:**
- Possibly modify: `tests/ui_and_conv/test_report_realdata.py`

- [ ] **Step 1: Locate the production transform**

Run:
```bash
grep -rn "ReportFinding\|Report(" src/pythinker_code/cli/security_scan.py src/pythinker_code/cli/secscan.py packages/pythinker-review 2>/dev/null | grep -v test
grep -rn "lineNumbers\|vulnSlug\|filePath" src packages/pythinker-review 2>/dev/null | grep -iv test | head
```

- [ ] **Step 2: Decide and act (one of two concrete outcomes)**

- **If a production transform exists** (raw findings → `Report` or → ` ```report ` JSON): add ONE test to `test_report_realdata.py` that feeds the fixture through the production transform and asserts its `severity`/`location`/`body` for finding[0] match the test-local `_to_finding(raw[0])` output. This proves the test-local adapter matches production. Show the exact import and assertion once located.
- **If no production transform exists in this repo** (it lives in the external scanner that emits ` ```report ` JSON directly): add a one-line comment at the top of `test_report_realdata.py` recording that the transform is external and the test-local adapter is the documented contract. No code change beyond the comment.

This task is bounded: it ends in either a single reconciliation test or a single documenting comment. Do not expand scope.

- [ ] **Step 3: Commit**

```bash
git add tests/ui_and_conv/test_report_realdata.py
git commit -m "test(tui): reconcile report fixture with production transform"
```

---

## Self-Review

**1. Spec coverage (§6–§8 lead phase):**
- §6.1 characterization → Task 7 ✓
- §6.2 table bug classes → Tasks 2, 3, 4, 5 ✓
- §6.3 report on real data + raw→Report transform → Tasks 8, 12 ✓
- §6.4 H1 → Task 9 ✓; H2 → Task 6 ✓; H3 → Task 6 ✓
- §6.5 display-vs-copy → **intentionally deferred** (no `/copy` exists; guard documented in spec, not built — out of scope per spec non-goals) ✓
- §7 idempotency harness → Task 1 (`render_twice_identical`) + Task 6 ✓; width-boundary harness → Task 1 (`WIDTHS`) + Task 3 ✓; theme harness → Task 1 (`THEMES`) + Task 8 ✓
- §5.1 screen-authority → Task 10 ✓
- §8 registry → Task 11 ✓

**2. Placeholder scan:** No "TBD/TODO/handle edge cases". Task 12 is a bounded investigation with two concrete, enumerated outcomes (not an open placeholder). Every code step shows complete code.

**3. Type/name consistency:** helper names (`render_plain`, `render_ansi`, `render_twice_identical`, `WIDTHS`, `THEMES`) defined in Task 1 are used verbatim in Tasks 2–8. New `report.py` symbols (`_get_report_parser`, `_iter_report_payloads`) are defined in Task 9 Step 3a and used in 3b/3c. `_to_finding`/`_load_report` defined and used within Task 8/referenced in Task 12.

**Note on exact-full-width:** Task 1's `WIDTHS` covers narrow/normal; the exact-full-width stray-space case (spec area 5) is roadmap seq 2, not lead phase. Flagged here so it is not silently considered covered.

---

## Execution Handoff

Per the approved scope, the deliverable is **the plan + spec only** — do not begin executing without an explicit greenlight. When greenlit, two options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks (REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`).
2. **Inline Execution** — execute tasks in-session with checkpoints (REQUIRED SUB-SKILL: `superpowers:executing-plans`).
