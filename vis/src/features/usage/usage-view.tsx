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
import { UsageHeatmap } from "./usage-heatmap";

type DailyUsage = AggregateStats["daily_usage"][number];

function SummaryCard({
  label,
  value,
  helper,
  icon: Icon,
}: {
  label: string;
  value: string;
  helper?: string;
  icon: typeof Activity;
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
        <p className="mt-3 truncate text-[11px] text-muted-foreground">{helper}</p>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Turn trend (compact single-series area)                            */
/* ------------------------------------------------------------------ */

const W = 600;
const H = 150;
const PAD_X = 8;
const PAD_TOP = 10;
const PAD_BOTTOM = 8;

function UsageTrendChart({ daily }: { daily: DailyUsage[] }) {
  if (daily.length === 0) return null;

  const maxTurns = Math.max(1, ...daily.map((d) => d.turns));
  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_TOP - PAD_BOTTOM;

  const toX = (i: number) =>
    PAD_X + (daily.length > 1 ? (i / (daily.length - 1)) * innerW : innerW / 2);
  const toY = (v: number) => PAD_TOP + (1 - v / maxTurns) * innerH;

  const line = daily
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(d.turns)}`)
    .join(" ");
  const area =
    line + ` L ${toX(daily.length - 1)} ${toY(0)} L ${toX(0)} ${toY(0)} Z`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      style={{ maxHeight: H }}
      role="img"
      aria-label="Turn volume over the last 30 days"
      preserveAspectRatio="none"
    >
      <path d={area} className="fill-foreground/[0.06]" />
      <path
        d={line}
        className="stroke-foreground"
        strokeWidth={1.5}
        fill="none"
        strokeLinejoin="round"
      />
    </svg>
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
    const peak = daily.reduce<DailyUsage | null>(
      (best, d) => (best === null || d.turns > best.turns ? d : best),
      null,
    );
    return { daily, totalTurns, totalSessions, activeDays, peak };
  }, [stats]);

  if (loading) {
    return (
      <div className="flex-1 overflow-auto p-4">
        <div className="mx-auto w-full max-w-[1400px] space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-[92px] animate-pulse rounded-xl border bg-muted/30" />
            ))}
          </div>
          <div className="h-[220px] animate-pulse rounded-xl border bg-muted/30" />
          <div className="h-[200px] animate-pulse rounded-xl border bg-muted/30" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-destructive/30 bg-destructive/5 p-6 text-center">
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
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-4 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Activity size={22} />
        </div>
        <p className="text-base font-semibold">No usage in the last 30 days</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          Activity appears here once sessions record turns. Run{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono">pythinker</code>{" "}
          to get started.
        </p>
      </div>
    );
  }

  const peakLabel = derived.peak
    ? `${derived.peak.turns.toLocaleString()} on ${derived.peak.date.slice(5)}`
    : "No peak yet";

  return (
    <div className="flex-1 overflow-auto p-4">
      <div className="mx-auto w-full max-w-[1400px] space-y-4">
        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <SummaryCard
            label="Turns (30d)"
            value={derived.totalTurns.toLocaleString()}
            helper="Conversation turns"
            icon={MessagesSquare}
          />
          <SummaryCard
            label="Sessions (30d)"
            value={derived.totalSessions.toLocaleString()}
            helper="Sessions started"
            icon={CalendarDays}
          />
          <SummaryCard
            label="Active Days"
            value={`${derived.activeDays} / ${derived.daily.length}`}
            helper="Days with activity"
            icon={Activity}
          />
          <SummaryCard
            label="Peak Day"
            value={derived.peak ? derived.peak.turns.toLocaleString() : "0"}
            helper={peakLabel}
            icon={Flame}
          />
        </div>

        {/* Heatmap */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Activity Heatmap</CardTitle>
              <CardDescription>
                Daily turn activity over the last 30 days
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="pt-3">
            <UsageHeatmap daily={derived.daily} />
          </CardContent>
        </Card>

        {/* Trend */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Turn Trend</CardTitle>
              <CardDescription>Turn volume per day, last 30 days</CardDescription>
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
