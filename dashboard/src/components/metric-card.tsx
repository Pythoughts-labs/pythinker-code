import { type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface MetricCardProps {
  label: string;
  value: string;
  helper?: string;
  icon: LucideIcon;
  className?: string;
}

/** Premium stat card: label, large value, helper line, and an accent icon tile. */
export function MetricCard({
  label,
  value,
  helper,
  icon: Icon,
  className,
}: MetricCardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border/60 bg-card p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
            {value}
          </p>
        </div>
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Icon size={18} />
        </div>
      </div>
      {helper && (
        <p className="mt-4 truncate text-sm text-muted-foreground">{helper}</p>
      )}
    </div>
  );
}
