import { useMemo } from "react";
import { type AggregateStats } from "@/lib/api";

type DailyUsage = AggregateStats["daily_usage"][number];
export type HeatmapMetric = "turns" | "sessions";

const WEEKDAYS = ["Mon", "", "Wed", "", "Fri", "", ""];
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Parse a "YYYY-MM-DD" key into a local-midnight Date (no timezone shift). */
function parseDate(key: string): Date {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function dateKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(date: Date, days: number): Date {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

/** Snap to the Monday of the given date's week. */
function startOfWeekMonday(date: Date): Date {
  const copy = new Date(date);
  const day = copy.getDay(); // 0 = Sun
  const diff = day === 0 ? -6 : 1 - day;
  copy.setDate(copy.getDate() + diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function heatmapLevelClass(level: number): string {
  switch (level) {
    case 1:
      return "bg-primary/25 dark:bg-primary/30";
    case 2:
      return "bg-primary/45 dark:bg-primary/50";
    case 3:
      return "bg-primary/70 dark:bg-primary/75";
    case 4:
      return "bg-primary";
    default:
      return "bg-muted";
  }
}

function usageLevel(value: number, max: number): number {
  if (value <= 0) return 0;
  const ratio = value / max;
  if (ratio <= 0.25) return 1;
  if (ratio <= 0.5) return 2;
  if (ratio <= 0.75) return 3;
  return 4;
}

const CELL = 15; // px

export function UsageHeatmap({
  daily,
  metric = "turns",
}: {
  daily: DailyUsage[];
  metric?: HeatmapMetric;
}) {
  const { weeks, monthLabels, byDate, maxValue, startDate, endDate } = useMemo(() => {
    const byDate = new Map<string, DailyUsage>();
    for (const d of daily) byDate.set(d.date, d);

    const dates = daily.map((d) => parseDate(d.date)).sort((a, b) => +a - +b);
    const start = dates.length ? dates[0] : new Date();
    const end = dates.length ? dates[dates.length - 1] : new Date();
    const maxValue = Math.max(1, ...daily.map((d) => d[metric]));

    const weeks: Date[][] = [];
    let cursor = startOfWeekMonday(start);
    while (cursor <= end) {
      weeks.push(Array.from({ length: 7 }, (_, i) => addDays(cursor, i)));
      cursor = addDays(cursor, 7);
    }

    const monthLabels: { label: string; col: number }[] = [];
    let prevMonth = -1;
    weeks.forEach((week, col) => {
      const month = week[0].getMonth();
      if (month !== prevMonth) {
        monthLabels.push({ label: MONTHS[month], col });
        prevMonth = month;
      }
    });

    return { weeks, monthLabels, byDate, maxValue, startDate: start, endDate: end };
  }, [daily, metric]);

  if (daily.length === 0) return null;

  return (
    <div className="inline-block">
      {/* Month labels */}
      <div className="relative ml-9 mb-1.5 h-4">
        {monthLabels.map((m) => (
          <span
            key={`${m.label}-${m.col}`}
            className="absolute text-xs text-muted-foreground"
            style={{ left: m.col * (CELL + 4) }}
          >
            {m.label}
          </span>
        ))}
      </div>

      <div className="flex gap-1.5">
        {/* Weekday labels */}
        <div className="grid grid-rows-7 gap-1 pr-1">
          {WEEKDAYS.map((day, i) => (
            <div
              key={i}
              className="flex items-center justify-end text-[10px] leading-none text-muted-foreground"
              style={{ height: CELL }}
            >
              {day}
            </div>
          ))}
        </div>

        {/* Week columns */}
        <div className="flex gap-1">
          {weeks.map((week, wi) => (
            <div key={wi} className="grid grid-rows-7 gap-1">
              {week.map((day) => {
                const key = dateKey(day);
                const outside = day < startDate || day > endDate;
                const entry = byDate.get(key);
                const value = entry?.[metric] ?? 0;
                const level = outside ? 0 : usageLevel(value, maxValue);
                const label = outside
                  ? ""
                  : `${key}: ${entry?.turns ?? 0} turns, ${entry?.sessions ?? 0} sessions`;
                return (
                  <div
                    key={key}
                    title={label || undefined}
                    aria-label={label || undefined}
                    className={`rounded-[4px] transition-shadow hover:ring-2 hover:ring-primary/30 hover:ring-offset-1 hover:ring-offset-background ${
                      outside ? "bg-transparent" : heatmapLevelClass(level)
                    }`}
                    style={{ width: CELL, height: CELL }}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
