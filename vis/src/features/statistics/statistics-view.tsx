import { useEffect, useState } from "react";
import {
  Clock,
  Coins,
  FolderGit2,
  MessagesSquare,
  type LucideIcon,
} from "lucide-react";
import { type AggregateStats, getAggregateStats } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/* ------------------------------------------------------------------ */
/*  Formatting helpers                                                 */
/* ------------------------------------------------------------------ */

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(0)}s`;
  if (sec < 3600) return `${(sec / 60).toFixed(1)}min`;
  return `${(sec / 3600).toFixed(1)}h`;
}

/* ------------------------------------------------------------------ */
/*  Summary Cards                                                      */
/* ------------------------------------------------------------------ */

function MetricCard({
  label,
  value,
  helper,
  icon: Icon,
}: {
  label: string;
  value: string;
  helper?: string;
  icon: LucideIcon;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">
            {value}
          </p>
        </div>
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon size={16} />
        </div>
      </div>
      {helper && (
        <p className="mt-3 truncate text-[11px] text-muted-foreground">
          {helper}
        </p>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Daily Usage Chart (SVG line chart)                                 */
/* ------------------------------------------------------------------ */

const CHART_WIDTH = 600;
const CHART_HEIGHT = 140;
const CHART_PAD_X = 36;
const CHART_PAD_TOP = 14;
const CHART_PAD_BOTTOM = 26;

function DailyUsageChart({ daily }: { daily: AggregateStats["daily_usage"] }) {
  if (daily.length === 0) return null;

  const maxSessions = Math.max(1, ...daily.map((d) => d.sessions));
  const maxTurns = Math.max(1, ...daily.map((d) => d.turns));

  const innerW = CHART_WIDTH - CHART_PAD_X * 2;
  const innerH = CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM;

  const toX = (i: number) =>
    CHART_PAD_X +
    (daily.length > 1 ? (i / (daily.length - 1)) * innerW : innerW / 2);
  const toYSessions = (v: number) =>
    CHART_PAD_TOP + (1 - v / maxSessions) * innerH;
  const toYTurns = (v: number) => CHART_PAD_TOP + (1 - v / maxTurns) * innerH;

  const sessionsPath = daily
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toYSessions(d.sessions)}`)
    .join(" ");
  const turnsPath = daily
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toYTurns(d.turns)}`)
    .join(" ");
  const sessionsArea =
    sessionsPath +
    ` L ${toX(daily.length - 1)} ${toYSessions(0)}` +
    ` L ${toX(0)} ${toYSessions(0)} Z`;

  const baselineY = CHART_PAD_TOP + innerH;

  // X-axis labels: ~5 evenly spaced dates
  const labelCount = Math.min(5, daily.length);
  const labelIndices: number[] = [];
  if (labelCount <= 1) {
    if (daily.length > 0) labelIndices.push(0);
  } else {
    for (let i = 0; i < labelCount; i++) {
      labelIndices.push(Math.round((i / (labelCount - 1)) * (daily.length - 1)));
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Daily Usage</CardTitle>
          <CardDescription>Sessions and turns over the last 30 days</CardDescription>
        </div>
        <div className="flex items-center gap-3 pt-0.5">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded bg-foreground" />
            <span className="text-[10px] text-muted-foreground">Sessions</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-3 border-t border-dashed border-muted-foreground" />
            <span className="text-[10px] text-muted-foreground">Turns</span>
          </span>
        </div>
      </CardHeader>
      <CardContent className="pt-2">
        <svg
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          className="w-full"
          style={{ maxHeight: CHART_HEIGHT }}
          role="img"
          aria-label="Daily sessions and turns over the last 30 days"
        >
          {/* Baseline */}
          <line
            x1={CHART_PAD_X}
            y1={baselineY}
            x2={CHART_WIDTH - CHART_PAD_X}
            y2={baselineY}
            className="stroke-border"
            strokeWidth={1}
          />

          {/* Sessions area + line (ink) */}
          <path d={sessionsArea} className="fill-foreground/[0.06]" />
          <path
            d={sessionsPath}
            className="stroke-foreground"
            strokeWidth={1.5}
            fill="none"
            strokeLinejoin="round"
          />

          {/* Turns line (muted dashed) */}
          <path
            d={turnsPath}
            className="stroke-muted-foreground"
            strokeWidth={1.5}
            fill="none"
            strokeDasharray="4 3"
            strokeLinejoin="round"
          />

          {/* Y-axis bounds */}
          <text
            x={CHART_PAD_X - 6}
            y={CHART_PAD_TOP + 4}
            className="fill-muted-foreground"
            fontSize={8}
            textAnchor="end"
          >
            {maxSessions}
          </text>
          <text
            x={CHART_PAD_X - 6}
            y={baselineY + 3}
            className="fill-muted-foreground"
            fontSize={8}
            textAnchor="end"
          >
            0
          </text>

          {/* X-axis date labels */}
          {labelIndices.map((idx) => (
            <text
              key={idx}
              x={toX(idx)}
              y={CHART_HEIGHT - 6}
              className="fill-muted-foreground"
              fontSize={8}
              textAnchor="middle"
            >
              {daily[idx].date.slice(5)}
            </text>
          ))}

          {/* Session dots */}
          {daily.map((d, i) =>
            d.sessions > 0 ? (
              <circle
                key={i}
                cx={toX(i)}
                cy={toYSessions(d.sessions)}
                r={1.8}
                className="fill-foreground"
              />
            ) : null,
          )}
        </svg>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Tool Usage Bar Chart                                               */
/* ------------------------------------------------------------------ */

function ToolUsageChart({ tools }: { tools: AggregateStats["tool_usage"] }) {
  if (tools.length === 0) return null;

  const maxCount = tools[0].count;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Tool Usage</CardTitle>
          <CardDescription>Most-used tools across all sessions</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2.5 pt-3">
        {tools.map((tool) => {
          const barPct = maxCount > 0 ? (tool.count / maxCount) * 100 : 0;
          const errorPct =
            tool.count > 0 ? (tool.error_count / tool.count) * 100 : 0;
          const successPct = 100 - errorPct;

          return (
            <div key={tool.name} className="space-y-1">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="truncate font-medium">{tool.name}</span>
                <span className="flex shrink-0 items-center gap-1.5 tabular-nums text-muted-foreground">
                  {tool.count.toLocaleString()}
                  {tool.error_count > 0 && (
                    <span className="rounded-full bg-destructive/10 px-1.5 py-0 text-[10px] font-medium text-destructive">
                      {tool.error_count} err
                    </span>
                  )}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="flex h-full" style={{ width: `${barPct}%` }}>
                  <div className="h-full bg-primary" style={{ width: `${successPct}%` }} />
                  {tool.error_count > 0 && (
                    <div
                      className="h-full bg-destructive"
                      style={{ width: `${errorPct}%` }}
                    />
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Per-Project Table                                                  */
/* ------------------------------------------------------------------ */

function ProjectTable({ projects }: { projects: AggregateStats["per_project"] }) {
  if (projects.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Top Projects</CardTitle>
          <CardDescription>Projects with the most activity</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="pt-3">
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Project</th>
                <th className="w-20 px-3 py-2 text-right font-medium">Sessions</th>
                <th className="w-16 px-3 py-2 text-right font-medium">Turns</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => {
                const segments = p.work_dir.split("/");
                const shortName = segments[segments.length - 1] || p.work_dir;
                return (
                  <tr
                    key={p.work_dir}
                    className="border-t transition-colors hover:bg-muted/40"
                  >
                    <td className="max-w-0 px-3 py-2">
                      <div className="truncate font-medium" title={p.work_dir}>
                        {shortName}
                      </div>
                      <div
                        className="truncate font-mono text-[10px] text-muted-foreground"
                        title={p.work_dir}
                      >
                        {p.work_dir}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {p.sessions}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {p.turns}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Main StatisticsView                                                */
/* ------------------------------------------------------------------ */

export function StatisticsView() {
  const [stats, setStats] = useState<AggregateStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getAggregateStats()
      .then(setStats)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex-1 overflow-auto p-4">
        <div className="mx-auto w-full max-w-[1400px] space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="space-y-3 rounded-xl border p-4 shadow-sm">
                <div className="flex items-start justify-between">
                  <div className="space-y-2">
                    <div className="h-3 w-16 animate-pulse rounded bg-muted" />
                    <div className="h-6 w-20 animate-pulse rounded bg-muted" />
                  </div>
                  <div className="size-9 animate-pulse rounded-lg bg-muted" />
                </div>
              </div>
            ))}
          </div>
          <div className="h-[200px] animate-pulse rounded-xl border bg-muted/30" />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="h-[260px] animate-pulse rounded-xl border bg-muted/30" />
            <div className="h-[260px] animate-pulse rounded-xl border bg-muted/30" />
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p className="text-sm font-medium text-destructive">
            Failed to load statistics
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{error}</p>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const totalTokens = stats.total_tokens.input + stats.total_tokens.output;
  const isEmpty = stats.total_sessions === 0;

  if (isEmpty) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-4 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <MessagesSquare size={22} />
        </div>
        <p className="text-base font-semibold">No activity yet</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          Run{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono">
            pythinker
          </code>{" "}
          to create sessions, then come back to see aggregate statistics.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="mx-auto w-full max-w-[1400px] space-y-4">
        {/* Summary Cards */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard
            label="Total Sessions"
            value={String(stats.total_sessions)}
            helper="Tracked agent runs"
            icon={FolderGit2}
          />
          <MetricCard
            label="Total Turns"
            value={stats.total_turns.toLocaleString()}
            helper="Conversation turns"
            icon={MessagesSquare}
          />
          <MetricCard
            label="Total Tokens"
            value={formatTokens(totalTokens)}
            helper={`${formatTokens(stats.total_tokens.input)} in / ${formatTokens(stats.total_tokens.output)} out`}
            icon={Coins}
          />
          <MetricCard
            label="Total Duration"
            value={formatDuration(stats.total_duration_sec)}
            helper="Runtime across sessions"
            icon={Clock}
          />
        </div>

        {/* Daily Usage Chart */}
        <DailyUsageChart daily={stats.daily_usage} />

        {/* Tool Usage + Project Table */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ToolUsageChart tools={stats.tool_usage} />
          <ProjectTable projects={stats.per_project} />
        </div>
      </div>
    </div>
  );
}
