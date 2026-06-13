import { useMemo } from "react";
import { type AggregateStats } from "@/lib/api";

type DailyUsage = AggregateStats["daily_usage"][number];

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

function levelClass(level: number): string {
  switch (level) {
    case 1:
      return "bg-primary/20";
    case 2:
      return "bg-primary/40";
    case 3:
      return "bg-primary/65";
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

const CELL = 13; // px, including the 1px gap handled by grid gap

export function UsageHeatmap({ daily }: { daily: DailyUsage[] }) {
  const { weeks, monthLabels, byDate, maxTurns, startDate, endDate } =
    useMemo(() => {
      const byDate = new Map<string, DailyUsage>();
      for (const d of daily) byDate.set(d.date, d);

      const dates = daily.map((d) => parseDate(d.date)).sort((a, b) => +a - +b);
      const start = dates.length ? dates[0] : new Date();
      const end = dates.length ? dates[dates.length - 1] : new Date();
      const maxTurns = Math.max(1, ...daily.map((d) => d.turns));

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

      return {
        weeks,
        monthLabels,
        byDate,
        maxTurns,
        startDate: start,
        endDate: end,
      };
    }, [daily]);

  if (daily.length === 0) return null;

  return (
    <div className="overflow-x-auto pb-1">
      <div className="min-w-max">
        {/* Month labels */}
        <div className="relative ml-8 mb-1 h-4">
          {monthLabels.map((m) => (
            <span
              key={`${m.label}-${m.col}`}
              className="absolute text-[10px] text-muted-foreground"
              style={{ left: m.col * (CELL + 4) }}
            >
              {m.label}
            </span>
          ))}
        </div>

        <div className="flex gap-1">
          {/* Weekday labels */}
          <div className="grid grid-rows-7 gap-1 pr-1">
            {WEEKDAYS.map((day, i) => (
              <div
                key={i}
                className="flex items-center justify-end text-[9px] leading-none text-muted-foreground"
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
                  const turns = entry?.turns ?? 0;
                  const level = outside ? 0 : usageLevel(turns, maxTurns);
                  const label = outside
                    ? ""
                    : `${key}: ${turns} turn${turns !== 1 ? "s" : ""}, ${entry?.sessions ?? 0} session${(entry?.sessions ?? 0) !== 1 ? "s" : ""}`;
                  return (
                    <div
                      key={key}
                      title={label || undefined}
                      aria-label={label || undefined}
                      className={`rounded-[3px] ${outside ? "bg-transparent" : levelClass(level)}`}
                      style={{ width: CELL, height: CELL }}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="mt-3 flex items-center justify-end gap-1.5 text-[10px] text-muted-foreground">
          <span>Less</span>
          {[0, 1, 2, 3, 4].map((lvl) => (
            <span
              key={lvl}
              className={`rounded-[3px] ${levelClass(lvl)}`}
              style={{ width: CELL, height: CELL }}
            />
          ))}
          <span>More</span>
        </div>
      </div>
    </div>
  );
}
