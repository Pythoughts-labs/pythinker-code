from __future__ import annotations

from rich.console import Console

from pythinker_code.ui.shell.stats_collector import AllStats, PeriodStats


def _make_all_stats(total_cost: float, messages: int) -> AllStats:
    p = PeriodStats()
    p.total_cost = total_cost
    p.total_messages = messages
    return AllStats(
        periods={
            "today": p,
            "this_week": p,
            "last_week": PeriodStats(),
            "all_time": p,
        },
        insights={},
    )


def _render_panel(panel) -> str:
    console = Console(force_terminal=False, width=80)
    with console.capture() as cap:
        console.print(panel)
    return cap.get()


def test_build_cost_panel_shows_cost():
    from pythinker_code.ui.shell.usage import _build_cost_panel

    stats = _make_all_stats(total_cost=1.23, messages=5)
    panel = _build_cost_panel(stats)
    rendered = _render_panel(panel)
    assert "$1.23" in rendered


def test_build_cost_panel_shows_today_and_week():
    from pythinker_code.ui.shell.usage import _build_cost_panel

    stats = _make_all_stats(total_cost=0.05, messages=3)
    panel = _build_cost_panel(stats)
    rendered = _render_panel(panel)
    assert "Today" in rendered
    assert "Week" in rendered


def test_build_cost_panel_title():
    from pythinker_code.ui.shell.usage import _build_cost_panel

    stats = _make_all_stats(total_cost=0.01, messages=1)
    panel = _build_cost_panel(stats)
    assert "Session Cost" in str(panel.title)


async def test_usage_prints_cost_panel_when_data_exists(monkeypatch):
    from rich.panel import Panel

    from pythinker_code.ui.shell import usage as usage_module

    stats = _make_all_stats(total_cost=2.50, messages=10)
    monkeypatch.setattr(usage_module, "_load_cost_stats", lambda: stats)

    printed = []
    monkeypatch.setattr(usage_module.console, "print", lambda *a, **kw: printed.append(a))

    await usage_module._maybe_print_cost_panel()

    panels = [item[0] for item in printed if item and isinstance(item[0], Panel)]
    assert any(p.title == "Session Cost" for p in panels)


async def test_usage_omits_cost_panel_when_no_data(monkeypatch):
    from pythinker_code.ui.shell import usage as usage_module

    monkeypatch.setattr(usage_module, "_load_cost_stats", lambda: None)

    printed = []
    monkeypatch.setattr(usage_module.console, "print", lambda *a, **kw: printed.append(a))

    await usage_module._maybe_print_cost_panel()

    assert not printed


async def test_usage_omits_cost_panel_on_exception(monkeypatch):
    from pythinker_code.ui.shell import usage as usage_module

    def _raise():
        raise RuntimeError("disk error")

    monkeypatch.setattr(usage_module, "_load_cost_stats", _raise)

    printed = []
    monkeypatch.setattr(usage_module.console, "print", lambda *a, **kw: printed.append(a))

    # Must not raise
    await usage_module._maybe_print_cost_panel()

    assert not printed
