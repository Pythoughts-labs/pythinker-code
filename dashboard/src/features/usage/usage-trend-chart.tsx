import { useLayoutEffect, useRef, useState } from "react";
import { type AggregateStats } from "@/lib/api";

type DailyUsage = AggregateStats["daily_usage"][number];

const HEIGHT = 260;
const PAD_L = 34;
const PAD_R = 14;
const PAD_T = 16;
const PAD_B = 26;
const GRID_STEPS = 4;

function niceMax(value: number): number {
  if (value <= 4) return Math.max(1, value);
  const pow = Math.pow(10, Math.floor(Math.log10(value)));
  const norm = value / pow;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return step * pow;
}

export function UsageTrendChart({ daily }: { daily: DailyUsage[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);

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

  const max = niceMax(Math.max(1, ...daily.map((d) => d.turns)));
  const plotW = Math.max(1, width - PAD_L - PAD_R);
  const plotH = HEIGHT - PAD_T - PAD_B;

  const toX = (i: number) =>
    PAD_L + (daily.length > 1 ? (i / (daily.length - 1)) * plotW : plotW / 2);
  const toY = (v: number) => PAD_T + (1 - v / max) * plotH;

  const line = daily.map((d, i) => `${i === 0 ? "M" : "L"} ${toX(i)} ${toY(d.turns)}`).join(" ");
  const area = `${line} L ${toX(daily.length - 1)} ${toY(0)} L ${toX(0)} ${toY(0)} Z`;

  const labelStep = Math.max(1, Math.ceil(daily.length / 6));

  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - PAD_L;
    const ratio = plotW > 0 ? x / plotW : 0;
    const idx = Math.round(ratio * (daily.length - 1));
    setHover(Math.min(daily.length - 1, Math.max(0, idx)));
  };

  const hovered = hover !== null ? daily[hover] : null;

  return (
    <div ref={ref} className="relative w-full" style={{ height: HEIGHT }}>
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        aria-label="Turn volume per day over the last 30 days"
      >
        <defs>
          <linearGradient id="turnsGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.22} />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* Horizontal gridlines + Y labels */}
        {Array.from({ length: GRID_STEPS + 1 }, (_, i) => {
          const v = (max / GRID_STEPS) * i;
          const y = toY(v);
          return (
            <g key={i}>
              <line
                x1={PAD_L}
                y1={y}
                x2={width - PAD_R}
                y2={y}
                className="stroke-border"
                strokeWidth={1}
                strokeDasharray={i === 0 ? undefined : "4 4"}
              />
              <text
                x={PAD_L - 6}
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

        {/* X date labels */}
        {daily.map((d, i) =>
          i % labelStep === 0 || i === daily.length - 1 ? (
            <text
              key={i}
              x={toX(i)}
              y={HEIGHT - 8}
              className="fill-muted-foreground"
              fontSize={9}
              textAnchor="middle"
            >
              {d.date.slice(5)}
            </text>
          ) : null,
        )}

        <path d={area} fill="url(#turnsGradient)" />
        <path
          d={line}
          className="stroke-primary"
          strokeWidth={2}
          fill="none"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Hover guide + dot */}
        {hovered && (
          <g>
            <line
              x1={toX(hover!)}
              y1={PAD_T}
              x2={toX(hover!)}
              y2={PAD_T + plotH}
              className="stroke-border"
              strokeWidth={1}
            />
            <circle
              cx={toX(hover!)}
              cy={toY(hovered.turns)}
              r={4}
              className="fill-primary stroke-background"
              strokeWidth={2}
            />
          </g>
        )}

        {/* Hover capture */}
        <rect
          x={PAD_L}
          y={PAD_T}
          width={plotW}
          height={plotH}
          fill="transparent"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        />
      </svg>

      {hovered && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-lg border border-border/60 bg-popover px-2.5 py-1.5 text-xs shadow-md"
          style={{
            left: Math.min(width - 60, Math.max(60, toX(hover!))),
            top: 4,
          }}
        >
          <div className="font-medium">{hovered.date.slice(5)}</div>
          <div className="text-muted-foreground tabular-nums">
            {hovered.turns} turns · {hovered.sessions} sessions
          </div>
        </div>
      )}
    </div>
  );
}
