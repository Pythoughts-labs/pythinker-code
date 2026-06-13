import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Clock, Coins, FolderGit2, MessagesSquare } from "lucide-react";
import { type AggregateStats, getAggregateStats } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { MetricCard } from "@/components/metric-card";

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
/*  Daily Usage Chart (SVG line chart)                                 */
/* ------------------------------------------------------------------ */

const DU_HEIGHT = 220;
const DU_PAD_L = 34;
const DU_PAD_R = 16;
const DU_PAD_T = 16;
const DU_PAD_B = 28;
const DU_GRID_STEPS = 4;

function DailyUsageChart({ daily }: { daily: AggregateStats["daily_usage"] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (daily.length === 0) return null;

  const maxSessions = Math.max(1, ...daily.map((d) => d.sessions));
  const maxTurns = Math.max(1, ...daily.map((d) => d.turns));

  const plotW = Math.max(1, width - DU_PAD_L - DU_PAD_R);
  const plotH = DU_HEIGHT - DU_PAD_T - DU_PAD_B;

  const toX = (i: number) =>
    DU_PAD_L + (daily.length > 1 ? (i / (daily.length - 1)) * plotW : plotW / 2);
  const toYSessions = (v: number) => DU_PAD_T + (1 - v / maxSessions) * plotH;
  const toYTurns = (v: number) => DU_PAD_T + (1 - v / maxTurns) * plotH;

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

  const labelStep = Math.max(1, Math.ceil(daily.length / 6));

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Daily Usage</CardTitle>
          <CardDescription>Sessions and turns over the last 30 days</CardDescription>
        </div>
        <div className="flex items-center gap-3 pt-0.5">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded bg-primary" />
            <span className="text-[10px] text-muted-foreground">Sessions</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-3 border-t border-dashed border-muted-foreground" />
            <span className="text-[10px] text-muted-foreground">Turns</span>
          </span>
        </div>
      </CardHeader>
      <CardContent className="pt-3">
        <div ref={ref} className="w-full" style={{ height: DU_HEIGHT }}>
          <svg
            width={width}
            height={DU_HEIGHT}
            role="img"
            aria-label="Daily sessions and turns over the last 30 days"
          >
            {/* Horizontal gridlines + sessions Y labels */}
            {Array.from({ length: DU_GRID_STEPS + 1 }, (_, i) => {
              const v = (maxSessions / DU_GRID_STEPS) * i;
              const y = toYSessions(v);
              return (
                <g key={i}>
                  <line
                    x1={DU_PAD_L}
                    y1={y}
                    x2={width - DU_PAD_R}
                    y2={y}
                    className="stroke-border"
                    strokeWidth={1}
                    strokeDasharray={i === 0 ? undefined : "4 4"}
                  />
                  <text
                    x={DU_PAD_L - 6}
                    y={y + 3}
                    className="fill-muted-foreground"
                    fontSize={9}
                    textAnchor="end"
                  >
                    {Math.round(v)}
                  </text>
                </g>
              );
            })}

            {/* Sessions area + line (accent) */}
            <path d={sessionsArea} className="fill-primary/[0.08]" />
            <path
              d={sessionsPath}
              className="stroke-primary"
              strokeWidth={2}
              fill="none"
              strokeLinejoin="round"
              strokeLinecap="round"
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

            {/* X-axis date labels */}
            {daily.map((d, i) =>
              i % labelStep === 0 || i === daily.length - 1 ? (
                <text
                  key={i}
                  x={toX(i)}
                  y={DU_HEIGHT - 8}
                  className="fill-muted-foreground"
                  fontSize={9}
                  textAnchor="middle"
                >
                  {d.date.slice(5)}
                </text>
              ) : null,
            )}

            {/* Session dots */}
            {daily.map((d, i) =>
              d.sessions > 0 ? (
                <circle
                  key={i}
                  cx={toX(i)}
                  cy={toYSessions(d.sessions)}
                  r={2}
                  className="fill-primary"
                />
              ) : null,
            )}
          </svg>
        </div>
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

          return (
            <div key={tool.name} className="space-y-1">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="truncate font-medium">{tool.name}</span>
                <span className="flex shrink-0 items-center gap-1.5 tabular-nums text-muted-foreground">
                  {tool.error_count > 0 && (
                    <span className="rounded-full border border-border/60 bg-muted px-1.5 py-0 text-[10px] font-medium text-muted-foreground">
                      {tool.error_count}{" "}
                      {tool.error_count === 1 ? "error" : "errors"}
                    </span>
                  )}
                  {tool.count.toLocaleString()}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${barPct}%` }}
                />
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
      <div className="flex flex-1 items-center justify-center bg-muted/30 p-6">
        <div className="max-w-sm rounded-2xl border border-destructive/30 bg-destructive/5 p-6 text-center">
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
      <div className="flex flex-1 flex-col items-center justify-center gap-2 bg-muted/30 p-6 text-center">
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
    <div className="flex-1 overflow-auto bg-muted/30 p-6">
      <div className="mx-auto w-full max-w-[1400px] space-y-6">
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
