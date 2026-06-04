from __future__ import annotations

import json
import os
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pythinker_code.ui.shell.stats_pricing import get_cost_usd
from pythinker_core.chat_provider import TokenUsage


@dataclass(slots=True)
class StepRecord:
    session_id: str
    timestamp: float
    model_name: str
    provider_key: str
    input_other: int
    output: int
    input_cache_read: int
    input_cache_creation: int

    @property
    def total_tokens(self) -> int:
        return self.input_other + self.output + self.input_cache_read + self.input_cache_creation

    @property
    def cost_usd(self) -> float:
        usage = TokenUsage(
            input_other=self.input_other,
            output=self.output,
            input_cache_read=self.input_cache_read,
            input_cache_creation=self.input_cache_creation,
        )
        return get_cost_usd(self.model_name, usage)


@dataclass(slots=True)
class ModelStats:
    messages: int = 0
    cost: float = 0.0
    input_other: int = 0
    output: int = 0
    input_cache_read: int = 0
    input_cache_creation: int = 0
    sessions: set[str] = field(default_factory=set)

    def add(self, step: StepRecord) -> None:
        self.messages += 1
        self.cost += step.cost_usd
        self.input_other += step.input_other
        self.output += step.output
        self.input_cache_read += step.input_cache_read
        self.input_cache_creation += step.input_cache_creation
        self.sessions.add(step.session_id)

    @property
    def tokens(self) -> int:
        return self.input_other + self.output + self.input_cache_creation


@dataclass(slots=True)
class ProviderStats:
    messages: int = 0
    cost: float = 0.0
    input_other: int = 0
    output: int = 0
    input_cache_read: int = 0
    input_cache_creation: int = 0
    sessions: set[str] = field(default_factory=set)
    models: dict[str, ModelStats] = field(default_factory=dict)

    def add(self, step: StepRecord) -> None:
        self.messages += 1
        self.cost += step.cost_usd
        self.input_other += step.input_other
        self.output += step.output
        self.input_cache_read += step.input_cache_read
        self.input_cache_creation += step.input_cache_creation
        self.sessions.add(step.session_id)
        m = self.models.setdefault(step.model_name, ModelStats())
        m.add(step)

    @property
    def tokens(self) -> int:
        return self.input_other + self.output + self.input_cache_creation


@dataclass(slots=True)
class PeriodStats:
    total_messages: int = 0
    total_cost: float = 0.0
    total_sessions: int = 0
    providers: dict[str, ProviderStats] = field(default_factory=dict)
    _sessions: set[str] = field(default_factory=set)

    def add(self, step: StepRecord) -> None:
        self.total_messages += 1
        self.total_cost += step.cost_usd
        self._sessions.add(step.session_id)
        self.total_sessions = len(self._sessions)
        p = self.providers.setdefault(step.provider_key, ProviderStats())
        p.add(step)


@dataclass(slots=True)
class Insight:
    percent: float
    headline: str
    advice: str


@dataclass(slots=True)
class PeriodInsights:
    insights: list[Insight] = field(default_factory=list)


@dataclass(slots=True)
class UsagePeriod:
    stats: PeriodStats = field(default_factory=PeriodStats)
    insights: PeriodInsights = field(default_factory=PeriodInsights)


@dataclass(slots=True)
class AllStats:
    periods: dict[str, PeriodStats]
    insights: dict[str, PeriodInsights]


def get_sessions_root() -> Path:
    """Return the path to ~/.pythinker/sessions/."""
    agent_dir = os.environ.get("PYTHINKER_DIR") or os.path.join(os.path.expanduser("~"), ".pythinker")
    return Path(agent_dir) / "sessions"


def collect_session_files(sessions_root: Path) -> list[Path]:
    """Recursively collect all wire.jsonl files under sessions_root."""
    result: list[Path] = []
    if not sessions_root.is_dir():
        return result
    for wd_dir in sessions_root.iterdir():
        if not wd_dir.is_dir():
            continue
        for sess_dir in wd_dir.iterdir():
            if not sess_dir.is_dir():
                continue
            _collect_from_session_dir(sess_dir, result)
    return sorted(result)


def _collect_from_session_dir(sess_dir: Path, result: list[Path]) -> None:
    wire = sess_dir / "wire.jsonl"
    if wire.is_file():
        result.append(wire)
    subagents = sess_dir / "subagents"
    if subagents.is_dir():
        for agent_dir in subagents.iterdir():
            if agent_dir.is_dir():
                sub_wire = agent_dir / "wire.jsonl"
                if sub_wire.is_file():
                    result.append(sub_wire)


def parse_wire_file(
    wire_path: Path,
    session_id: str,
    seen_hashes: set[str],
) -> Generator[StepRecord, None, None]:
    """Parse one wire.jsonl and yield StepRecords for each StatusUpdate."""
    try:
        with wire_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") != "StatusUpdate":
                    continue
                payload = msg.get("payload")
                if not isinstance(payload, dict):
                    continue
                tu = payload.get("token_usage")
                if not isinstance(tu, dict):
                    continue

                input_other = int(tu.get("input_other", 0))
                output = int(tu.get("output", 0))
                cache_read = int(tu.get("input_cache_read", 0))
                cache_write = int(tu.get("input_cache_creation", 0))
                total = input_other + output + cache_read + cache_write
                ts = float(obj.get("timestamp", 0))

                h = f"{ts}:{total}"
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                model_name = payload.get("model_name") or "unknown"
                provider_key = payload.get("provider_key") or "unknown"

                yield StepRecord(
                    session_id=session_id,
                    timestamp=ts,
                    model_name=model_name,
                    provider_key=provider_key,
                    input_other=input_other,
                    output=output,
                    input_cache_read=cache_read,
                    input_cache_creation=cache_write,
                )
    except OSError:
        return


def _period_boundaries() -> tuple[float, float, float]:
    """Return (today_start, week_start, last_week_start) as UTC timestamps."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_monday = now.weekday()  # Monday=0
    week_start = today_start - timedelta(days=days_since_monday)
    last_week_start = week_start - timedelta(days=7)
    return (
        today_start.timestamp(),
        week_start.timestamp(),
        last_week_start.timestamp(),
    )


def compute_period_stats(steps: list[StepRecord]) -> dict[str, PeriodStats]:
    """Bin steps into Today / This Week / Last Week / All Time."""
    today_ts, week_ts, last_week_ts = _period_boundaries()

    periods: dict[str, PeriodStats] = {
        "today": PeriodStats(),
        "this_week": PeriodStats(),
        "last_week": PeriodStats(),
        "all_time": PeriodStats(),
    }

    for step in steps:
        ts = step.timestamp
        periods["all_time"].add(step)
        if ts >= today_ts:
            periods["today"].add(step)
        if ts >= week_ts:
            periods["this_week"].add(step)
        elif ts >= last_week_ts:
            periods["last_week"].add(step)

    return periods


_PARALLEL_WINDOW_S = 120.0
_PARALLEL_SESSION_THRESHOLD = 4
_LARGE_CONTEXT_THRESHOLD = 150_000
_LARGE_UNCACHED_THRESHOLD = 100_000
_LONG_SESSION_S = 8 * 3600
_TOP_SESSION_COUNT = 5
_MIN_PERCENT = 1.0


def compute_insights(steps: list[StepRecord]) -> PeriodInsights:
    """Compute cost-weighted usage insights for a period."""
    if not steps:
        return PeriodInsights()

    total_cost = sum(s.cost_usd for s in steps)
    if total_cost <= 0:
        return PeriodInsights()

    candidates: list[Insight] = []

    # Large context
    large_ctx_cost = sum(
        s.cost_usd for s in steps
        if (s.input_other + s.input_cache_read + s.input_cache_creation) > _LARGE_CONTEXT_THRESHOLD
    )
    candidates.append(Insight(
        percent=(large_ctx_cost / total_cost) * 100,
        headline=f"of your cost was at >{_LARGE_CONTEXT_THRESHOLD // 1000}k context",
        advice=(
            "Longer sessions are more expensive even when cached. "
            "/compact mid-task, /clear when switching to new tasks."
        ),
    ))

    # Large uncached prompt
    uncached_cost = sum(
        s.cost_usd for s in steps
        if (s.input_other + s.input_cache_creation) > _LARGE_UNCACHED_THRESHOLD
    )
    candidates.append(Insight(
        percent=(uncached_cost / total_cost) * 100,
        headline=f"of your cost came from >{_LARGE_UNCACHED_THRESHOLD // 1000}k-token uncached prompts",
        advice=(
            "Uncached input is expensive. "
            "/compact before stepping away keeps the cold-start small."
        ),
    ))

    # Top-N session concentration
    session_costs: dict[str, float] = {}
    for s in steps:
        session_costs[s.session_id] = session_costs.get(s.session_id, 0.0) + s.cost_usd
    if len(session_costs) > _TOP_SESSION_COUNT:
        top_cost = sum(sorted(session_costs.values(), reverse=True)[:_TOP_SESSION_COUNT])
        candidates.append(Insight(
            percent=(top_cost / total_cost) * 100,
            headline=f"of your cost came from your top {_TOP_SESSION_COUNT} sessions",
            advice="A small number of sessions drives most of your spend.",
        ))

    insights = [i for i in candidates if i.percent >= _MIN_PERCENT]
    insights.sort(key=lambda i: i.percent, reverse=True)
    return PeriodInsights(insights=insights)


def load_all_stats() -> AllStats:
    """Load and aggregate all pythinker session usage with insights."""
    root = get_sessions_root()
    wire_files = collect_session_files(root)
    seen_hashes: set[str] = set()
    all_steps: list[StepRecord] = []

    for wire_path in wire_files:
        session_id = f"{wire_path.parent.parent.name}/{wire_path.parent.name}"
        for step in parse_wire_file(wire_path, session_id, seen_hashes):
            all_steps.append(step)

    periods = compute_period_stats(all_steps)

    today_ts, week_ts, last_week_ts = _period_boundaries()
    period_steps: dict[str, list[StepRecord]] = {
        "today": [],
        "this_week": [],
        "last_week": [],
        "all_time": list(all_steps),
    }
    for step in all_steps:
        ts = step.timestamp
        if ts >= today_ts:
            period_steps["today"].append(step)
        if ts >= week_ts:
            period_steps["this_week"].append(step)
        elif ts >= last_week_ts:
            period_steps["last_week"].append(step)

    insights = {k: compute_insights(v) for k, v in period_steps.items()}
    return AllStats(periods=periods, insights=insights)
