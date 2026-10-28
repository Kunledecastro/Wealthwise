"use client";

import Link from "next/link";
import { Card } from "@/components/ui/card";
import type { BudgetPage } from "@/lib/api";
import { formatMinor } from "@/lib/money";
import { monthEnd, monthName } from "@/lib/periods";
import { useLoad } from "@/lib/use-load";
import { BudgetBar, BudgetStatus } from "./budget-ui";

const linkCls = "text-sm text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] rounded";

/** This month's budget at a glance: the overall limit (if any) and the lines needing attention. */
export function BudgetCard({ refreshKey }: { refreshKey?: string | number }) {
  const { data } = useLoad<BudgetPage>(`/api/budgets?v=${refreshKey ?? 0}`);
  if (!data) return null;
  const b = data.budget;
  const name = monthName(data.month, { year: false });
  if (!b || (b.lines.length === 0 && !b.overall)) {
    return (
      <Card className="flex flex-wrap items-center gap-3">
        <div className="flex-1">
          <h2 className="font-semibold">No budget for {name}</h2>
          <p className="text-sm text-[var(--fg-subtle)]">Set monthly amounts per category and get warned before you overspend.</p>
        </div>
        <Link href="/budgets" className="inline-flex min-h-10 items-center rounded-md border border-[var(--border)] px-4 text-sm font-medium hover:bg-[var(--muted)]">Set a budget</Link>
      </Card>
    );
  }
  const attention = [...b.lines].filter((l) => l.status !== "ok").sort((x, y) => (y.percent_used ?? 0) - (x.percent_used ?? 0)).slice(0, 4);
  const end = `${Number(monthEnd(data.month).slice(8))} ${monthName(data.month, { short: true, year: false })}`;
  return (
    <Card>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="font-semibold">Budget · {name}</h2>
        <Link href="/budgets" className={`ml-auto ${linkCls}`}>Open</Link>
      </div>
      {b.overall ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-baseline gap-2 text-sm">
            <span>Overall</span>
            <BudgetStatus line={b.overall} />
            <span className="ml-auto font-medium tabular">{formatMinor(b.overall.spent_minor)} of {formatMinor(b.overall.available_minor)}</span>
          </div>
          <BudgetBar line={b.overall} thresholds={b.alert_thresholds} />
          {b.overall.projected_minor !== null && b.overall.days_left > 1 && (
            <p className={b.overall.projected_over ? "text-xs text-[var(--danger)]" : "text-xs text-[var(--fg-subtle)]"}>
              Estimate at your current pace: {formatMinor(b.overall.projected_minor)} by {end}
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm tabular">
          <span className="font-medium">{formatMinor(b.budgeted_spending)}</span>
          <span className="text-[var(--fg-subtle)]"> spent of {formatMinor(b.total_planned)} budgeted across {b.lines.length} categor{b.lines.length === 1 ? "y" : "ies"}</span>
        </p>
      )}
      {attention.length > 0 ? (
        <ul className="mt-4 space-y-3">
          {attention.map((l) => (
            <li key={l.id} className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} aria-hidden />
                <span className="min-w-0 flex-1 truncate">{l.name}</span>
                <BudgetStatus line={l} />
              </div>
              <BudgetBar line={l} thresholds={b.alert_thresholds} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-[var(--fg-subtle)]">Every category is within its alert levels.</p>
      )}
    </Card>
  );
}
