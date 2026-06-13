import { useEffect, useMemo, useState } from "react";
import { Activity, CalendarDays, Flame, MessagesSquare } from "lucide-react";
import { type AggregateStats, getAggregateStats } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { MetricCard } from "@/components/metric-card";
import {
  type HeatmapMetric,
  UsageHeatmap,
  heatmapLevelClass,
} from "./usage-heatmap";
import { UsageTrendChart } from "./usage-trend-chart";

type DailyUsage = AggregateStats["daily_usage"][number];

/* ------------------------------------------------------------------ */
/*  Heatmap card (with metric toggle + legend)                         */
/* ------------------------------------------------------------------ */

function HeatmapLegend() {
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span>Less</span>
      {[0, 1, 2, 3, 4].map((lvl) => (
        <span
          key={lvl}
          className={`size-3.5 rounded-[4px] ${heatmapLevelClass(lvl)}`}
        />
      ))}
      <span>More</span>
    </div>
  );
}

function SegmentedToggle({
  value,
  onChange,
}: {
  value: HeatmapMetric;
  onChange: (v: HeatmapMetric) => void;
}) {
  const options: { key: HeatmapMetric; label: string }[] = [
    { key: "turns", label: "Turns" },
    { key: "sessions", label: "Sessions" },
  ];
  return (
    <div className="flex rounded-lg bg-muted p-0.5">
      {options.map((opt) => (
        <button
          key={opt.key}
          onClick={() => onChange(opt.key)}
          aria-pressed={value === opt.key}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            value === opt.key
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function ActivityHeatmapCard({ daily }: { daily: DailyUsage[] }) {
  const [metric, setMetric] = useState<HeatmapMetric>("turns");

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div>
          <CardTitle>Activity Heatmap</CardTitle>
          <CardDescription>
            Daily {metric} over the last 30 days
          </CardDescription>
        </div>
        <SegmentedToggle value={metric} onChange={setMetric} />
      </CardHeader>
      <CardContent className="flex flex-1 items-center justify-center overflow-x-auto py-6">
        <UsageHeatmap daily={daily} metric={metric} />
      </CardContent>
      <div className="flex items-center justify-between gap-2 border-t border-border/60 px-4 py-3">
        <p className="text-xs text-muted-foreground">
          Shown in your local timezone
        </p>
        <HeatmapLegend />
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Insights panel                                                     */
/* ------------------------------------------------------------------ */

function InsightRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/60 pb-3 last:border-0 last:pb-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold tabular-nums">{value}</span>
    </div>
  );
}

function UsageInsightsCard({
  peak,
  activeDays,
  quietDays,
  avgActiveTurns,
}: {
  peak: DailyUsage | null;
  activeDays: number;
  quietDays: number;
  avgActiveTurns: number;
}) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Usage Insights</CardTitle>
          <CardDescription>Summary for the last 30 days</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-3">
        <InsightRow
          label="Most active day"
          value={peak && peak.turns > 0 ? peak.date.slice(5) : "None"}
        />
        <InsightRow
          label="Peak turns"
          value={peak ? peak.turns.toLocaleString() : "0"}
        />
        <InsightRow
          label="Avg active day"
          value={`${avgActiveTurns.toLocaleString()} turns`}
        />
        <InsightRow label="Quiet days" value={String(quietDays)} />
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Main UsageView                                                     */
/* ------------------------------------------------------------------ */

export function UsageView() {
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

  const derived = useMemo(() => {
    const daily = stats?.daily_usage ?? [];
    const totalTurns = daily.reduce((s, d) => s + d.turns, 0);
    const totalSessions = daily.reduce((s, d) => s + d.sessions, 0);
    const activeDays = daily.filter((d) => d.turns > 0).length;
    const quietDays = daily.length - activeDays;
    const avgActiveTurns = activeDays > 0 ? Math.round(totalTurns / activeDays) : 0;
    const peak = daily.reduce<DailyUsage | null>(
      (best, d) => (best === null || d.turns > best.turns ? d : best),
      null,
    );
    return {
      daily,
      totalTurns,
      totalSessions,
      activeDays,
      quietDays,
      avgActiveTurns,
      peak,
    };
  }, [stats]);

  if (loading) {
    return (
      <div className="flex-1 overflow-auto bg-muted/30 p-6">
        <div className="mx-auto w-full max-w-[1500px] space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-[124px] animate-pulse rounded-2xl border border-border/60 bg-card" />
            ))}
          </div>
          <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
            <div className="h-[320px] animate-pulse rounded-2xl border border-border/60 bg-card" />
            <div className="h-[320px] animate-pulse rounded-2xl border border-border/60 bg-card" />
          </div>
          <div className="h-[360px] animate-pulse rounded-2xl border border-border/60 bg-card" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center bg-muted/30 p-6">
        <div className="max-w-sm rounded-2xl border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p className="text-sm font-medium text-destructive">
            Failed to load usage data
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{error}</p>
        </div>
      </div>
    );
  }

  if (!stats || derived.totalTurns === 0) {
    return (
      <div className="flex flex-1 items-center justify-center bg-muted/30 p-6">
        <div className="flex min-h-[280px] w-full max-w-md flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card p-8 text-center">
          <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Activity size={24} />
          </div>
          <h3 className="text-base font-semibold">No usage recorded yet</h3>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Activity will appear here once sessions record turns. Run{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono">
              pythinker
            </code>{" "}
            to get started.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-auto bg-muted/30 p-6">
      <div className="mx-auto w-full max-w-[1500px] space-y-6">
        {/* Summary cards */}
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Turns"
            value={derived.totalTurns.toLocaleString()}
            helper="Conversation turns in the last 30 days"
            icon={MessagesSquare}
          />
          <MetricCard
            label="Sessions"
            value={derived.totalSessions.toLocaleString()}
            helper="Sessions started in the last 30 days"
            icon={CalendarDays}
          />
          <MetricCard
            label="Active Days"
            value={`${derived.activeDays} / ${derived.daily.length}`}
            helper="Days with recorded activity"
            icon={Activity}
          />
          <MetricCard
            label="Peak Day"
            value={derived.peak ? derived.peak.turns.toLocaleString() : "0"}
            helper={
              derived.peak && derived.peak.turns > 0
                ? `Highest usage on ${derived.peak.date.slice(5)}`
                : "No peak yet"
            }
            icon={Flame}
          />
        </section>

        {/* Heatmap + Insights */}
        <section className="grid gap-6 xl:grid-cols-[1fr_320px]">
          <ActivityHeatmapCard daily={derived.daily} />
          <UsageInsightsCard
            peak={derived.peak}
            activeDays={derived.activeDays}
            quietDays={derived.quietDays}
            avgActiveTurns={derived.avgActiveTurns}
          />
        </section>

        {/* Trend */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Turn Trend</CardTitle>
              <CardDescription>
                Turn volume per day across the last 30 days
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="pt-3">
            <UsageTrendChart daily={derived.daily} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
