"use client";

import { AlertTriangle, CheckCircle2, CircleAlert } from "lucide-react";
import type { BudgetLine } from "@/lib/api";
import { formatMinor } from "@/lib/money";
import { cn } from "@/lib/utils";

/** Status in words and an icon (never colour alone). */
export function BudgetStatus({ line }: { line: BudgetLine }) {
  if (line.over) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[var(--danger-bg)] px-2 py-0.5 text-xs font-medium text-[var(--danger)]">
        <CircleAlert className="h-3.5 w-3.5" aria-hidden /> Over by {formatMinor(-line.remaining_minor)}
      </span>
    );
  }
  if (line.threshold_reached) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
        <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> Reached {line.threshold_reached}%
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-[var(--accent-bg)] px-2 py-0.5 text-xs font-medium text-[var(--accent-strong)]">
      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> On track
    </span>
  );
}

/** Spent vs available, with tick marks at each alert threshold. */
export function BudgetBar({ line, thresholds }: { line: BudgetLine; thresholds: number[] }) {
  const pct = line.available_minor > 0 ? Math.min(100, (Math.max(0, line.spent_minor) / line.available_minor) * 100) : line.spent_minor > 0 ? 100 : 0;
  const fill = line.over ? "bg-[var(--danger)]" : line.threshold_reached ? "bg-amber-500" : "bg-[var(--accent)]";
  return (
    <div
      className="relative h-2.5 rounded-full bg-[var(--muted)]"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-label={`${line.name}: ${line.percent_used ?? 0}% of the budget used`}
    >
      <div className={cn("h-2.5 rounded-full", fill)} style={{ width: `${pct}%` }} />
      {thresholds.filter((t) => t < 100).map((t) => (
        <span key={t} className="absolute top-[-2px] h-[14px] w-[2px] bg-[var(--surface)]" style={{ left: `calc(${t}% - 1px)` }} aria-hidden />
      ))}
    </div>
  );
}

export function LineFigures({ line, monthEnd }: { line: BudgetLine; monthEnd: string }) {
  return (
    <div className="space-y-1 text-sm">
      <p className="tabular">
        <span className="font-medium">{formatMinor(line.spent_minor)}</span>
        <span className="text-[var(--fg-subtle)]"> spent of {formatMinor(line.available_minor)}</span>
        {line.rollover_minor > 0 && <span className="text-[var(--fg-subtle)]"> (incl. {formatMinor(line.rollover_minor)} carried over)</span>}
      </p>
      <p className="text-xs text-[var(--fg-subtle)] tabular">
        {line.remaining_minor >= 0 ? `${formatMinor(line.remaining_minor)} left` : `${formatMinor(-line.remaining_minor)} over`}
        {line.safe_per_day_minor !== null && line.days_left > 0 && line.remaining_minor > 0 && (
          <> · about {formatMinor(line.safe_per_day_minor)} a day for {line.days_left} day{line.days_left === 1 ? "" : "s"}</>
        )}
      </p>
      {line.projected_minor !== null && line.days_left > 1 && line.spent_minor > 0 && (
        <p className={cn("text-xs", line.projected_over ? "text-[var(--danger)]" : "text-[var(--fg-subtle)]")}>
          Estimate at your current pace: {formatMinor(line.projected_minor)} by {monthEnd}
          {line.projected_over && ` (${formatMinor(line.projected_minor - line.available_minor)} over)`}
        </p>
      )}
    </div>
  );
}
