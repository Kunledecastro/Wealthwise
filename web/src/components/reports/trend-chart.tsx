"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Granularity, SeriesPoint } from "@/lib/api";
import { formatMinor } from "@/lib/money";
import { bucketLabel, bucketTitle, compactMinor } from "@/lib/periods";
import { cn } from "@/lib/utils";
import { useChartTheme } from "./chart-theme";

export type TrendMode = "spending" | "both";

type Row = SeriesPoint & { label: string; title: string };

function Toggle<T extends string>({ value, options, onChange, label }: { value: T; options: { id: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-[var(--border)] p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          aria-pressed={value === o.id}
          onClick={() => onChange(o.id)}
          className={cn(
            "min-h-8 rounded px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
            value === o.id ? "bg-[var(--muted)] text-[var(--fg)]" : "text-[var(--fg-subtle)] hover:text-[var(--fg)]",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ChartTooltip({ active, payload, mode }: { active?: boolean; payload?: { payload: Row }[]; mode: TrendMode }) {
  const theme = useChartTheme();
  const r = payload?.[0]?.payload;
  if (!active || !r) return null;
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-semibold">{r.title}</p>
      <dl className="grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5 tabular">
        {mode === "both" && (
          <>
            <dt className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: theme.income }} aria-hidden />Income</dt>
            <dd className="text-right">{formatMinor(r.income)}</dd>
          </>
        )}
        <dt className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: theme.spending }} aria-hidden />Spending</dt>
        <dd className="text-right">{formatMinor(r.net_spending)}</dd>
        {r.refunds > 0 && (
          <>
            <dt className="pl-3.5 text-[var(--fg-subtle)]">Refunds (already deducted)</dt>
            <dd className="text-right text-[var(--fg-subtle)]">{formatMinor(r.refunds)}</dd>
          </>
        )}
        {mode === "both" && (
          <>
            <dt className="pl-3.5">Net cash flow</dt>
            <dd className="text-right">{formatMinor(r.net_cash_flow)}</dd>
          </>
        )}
        <dt className="pl-3.5 text-[var(--fg-subtle)]">Transactions</dt>
        <dd className="text-right text-[var(--fg-subtle)]">{r.transaction_count}</dd>
      </dl>
    </div>
  );
}

/** Spending (and optionally income) per day/week/month, with a table view. One y-axis only. */
export function TrendChart({ series, granularity, defaultMode, title }: { series: SeriesPoint[]; granularity: Granularity; defaultMode?: TrendMode; title: string }) {
  const theme = useChartTheme();
  const [mode, setMode] = useState<TrendMode>(defaultMode ?? (granularity === "day" ? "spending" : "both"));
  const [view, setView] = useState<"chart" | "table">("chart");
  const rows: Row[] = series.map((p) => ({ ...p, label: bucketLabel(p.date_from, p.date_to, granularity), title: bucketTitle(p.date_from, p.date_to, granularity) }));
  const empty = rows.every((r) => r.transaction_count === 0 && r.net_spending === 0 && r.income === 0);
  const hasNegative = rows.some((r) => r.net_spending < 0 || (mode === "both" && r.income < 0));
  const unit = granularity === "day" ? "Daily" : granularity === "week" ? "Weekly" : "Monthly";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{title}</h3>
        <span className="text-sm text-[var(--fg-subtle)]">{unit}</span>
        <div className="ml-auto flex flex-wrap gap-2 print:hidden">
          <Toggle label="What to show" value={mode} onChange={setMode} options={[{ id: "spending", label: "Spending" }, { id: "both", label: "Income vs spending" }]} />
          <Toggle label="View" value={view} onChange={setView} options={[{ id: "chart", label: "Chart" }, { id: "table", label: "Table" }]} />
        </div>
      </div>

      {mode === "both" && view === "chart" && (
        <ul className="flex gap-4 text-xs text-[var(--fg-subtle)]" aria-label="Legend">
          <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: theme.income }} aria-hidden />Income</li>
          <li className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: theme.spending }} aria-hidden />Spending</li>
        </ul>
      )}

      {view === "chart" ? (
        empty ? (
          <p className="flex h-56 items-center justify-center rounded-lg bg-[var(--muted)] text-sm text-[var(--fg-subtle)]">No income or spending in this period.</p>
        ) : (
          <div className="h-56 sm:h-64" role="img" aria-label={`${unit} ${mode === "both" ? "income and spending" : "spending"} chart. Use the Table view for exact figures.`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barGap={2} barCategoryGap={rows.length > 20 ? 1 : "20%"}>
                <CartesianGrid vertical={false} stroke={theme.grid} />
                <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: theme.grid }} tick={{ fill: theme.axis, fontSize: 11 }} interval="preserveStartEnd" minTickGap={16} />
                <YAxis tickFormatter={compactMinor} tickLine={false} axisLine={false} tick={{ fill: theme.axis, fontSize: 11 }} width={56} allowDecimals={false} />
                {hasNegative && <ReferenceLine y={0} stroke={theme.axis} />}
                <Tooltip content={<ChartTooltip mode={mode} />} cursor={{ fill: theme.cursor }} isAnimationActive={false} />
                {mode === "both" && <Bar dataKey="income" name="Income" fill={theme.income} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />}
                <Bar dataKey="net_spending" name="Spending" fill={theme.spending} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )
      ) : (
        <SeriesTable rows={rows} />
      )}
    </div>
  );
}

function SeriesTable({ rows }: { rows: Row[] }) {
  return (
    <div className="max-h-80 overflow-auto rounded-lg border border-[var(--border)]">
      <table className="w-full text-sm tabular">
        <thead className="sticky top-0 bg-[var(--muted)] text-left text-xs text-[var(--fg-subtle)]">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">Period</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Income</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Spending</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Net</th>
            <th scope="col" className="hidden px-3 py-2 text-right font-medium sm:table-cell">Count</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {rows.map((r) => (
            <tr key={r.date_from}>
              <th scope="row" className="px-3 py-1.5 text-left font-normal">{r.title}</th>
              <td className="px-3 py-1.5 text-right">{formatMinor(r.income)}</td>
              <td className="px-3 py-1.5 text-right">{formatMinor(r.net_spending)}</td>
              <td className="px-3 py-1.5 text-right">{formatMinor(r.net_cash_flow)}</td>
              <td className="hidden px-3 py-1.5 text-right sm:table-cell">{r.transaction_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
