"use client";

import Link from "next/link";
import { Suspense } from "react";
import { Download, Printer } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { BalancesNote, Kpis, PeriodFilters, RankedBars, categoryBars, merchantBars, overviewQuery, pageQuery, useOverview, useReportParams, useSetReportParams } from "@/components/reports/report-bits";
import { TrendChart } from "@/components/reports/trend-chart";
import { Alert } from "@/components/ui/alert";
import { Card } from "@/components/ui/card";
import type { Account, Granularity } from "@/lib/api";
import { formatMinor } from "@/lib/money";
import { periodLabel } from "@/lib/periods";
import { useLoad } from "@/lib/use-load";
import { useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";

export default function ReportsPage() {
  return (
    <AppShell>
      <Suspense fallback={<p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}>
        <Reports />
      </Suspense>
    </AppShell>
  );
}

const btn = "inline-flex min-h-9 items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-sm font-medium hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]";

const GRANS: { id: "auto" | Granularity; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "day", label: "Daily" },
  { id: "week", label: "Weekly" },
  { id: "month", label: "Monthly" },
];

function Reports() {
  const { me } = useAuth();
  const { period, account, today } = useReportParams(me?.preferences.timezone ?? "Africa/Lagos");
  const params = useSearchParams();
  const set = useSetReportParams();
  const g = (params.get("g") as "auto" | Granularity | null) ?? "auto";
  const gran = GRANS.some((x) => x.id === g) ? g : "auto";
  const accounts = useLoad<Account[]>("/api/accounts");
  const { data: o, error } = useOverview(period, account, { granularity: gran });
  const csv = (report: string) => `/api/reports/export.csv?${overviewQuery(period, account, { report, granularity: gran })}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="text-[var(--fg-subtle)]">{o ? periodLabel(o.date_from, o.date_to) : " "}</p>
        </div>
        <Link href={`/reports/print?${pageQuery(period, account, gran === "auto" ? {} : { g: gran })}`} className={cn(btn, "ml-auto")}>
          <Printer className="h-4 w-4" aria-hidden /> Printable summary
        </Link>
      </div>

      {accounts.data && <PeriodFilters period={period} account={account} today={today} accounts={accounts.data} />}
      {error && <Alert>{error}</Alert>}
      {!o && !error && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}

      {o && (
        <>
          {o.needs_review_count > 0 && (
            <Alert kind="info">
              {o.needs_review_count} transaction{o.needs_review_count === 1 ? " is" : "s are"} waiting for a category. <Link href="/review" className="font-medium underline">Review</Link>
            </Alert>
          )}
          <Kpis o={o} />

          <Card>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <div role="group" aria-label="Group by" className="inline-flex rounded-md border border-[var(--border)] p-0.5">
                {GRANS.map((x) => (
                  <button key={x.id} type="button" aria-pressed={gran === x.id} onClick={() => set({ extra: { g: x.id === "auto" ? null : x.id } })} className={cn("min-h-8 rounded px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]", gran === x.id ? "bg-[var(--muted)] text-[var(--fg)]" : "text-[var(--fg-subtle)] hover:text-[var(--fg)]")}>
                    {x.label}
                  </button>
                ))}
              </div>
              <a href={csv("period")} className={cn(btn, "ml-auto")}><Download className="h-4 w-4" aria-hidden /> CSV</a>
            </div>
            <TrendChart key={`${o.date_from}-${o.date_to}-${o.granularity}`} series={o.series} granularity={o.granularity} defaultMode="both" title="Income and spending" />
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <div id="categories" className="mb-4 flex items-center gap-2 scroll-mt-24">
                <h2 className="font-semibold">Spending by category</h2>
                <a href={csv("categories")} className={cn(btn, "ml-auto")}><Download className="h-4 w-4" aria-hidden /> CSV</a>
              </div>
              <RankedBars rows={categoryBars(o, account)} currency={o.currency} empty="No spending in this period." />
              {o.income_by_category.length > 0 && (
                <>
                  <h3 className="mt-6 mb-2 text-sm font-semibold">Income by category</h3>
                  <ul className="divide-y divide-[var(--border)] text-sm">
                    {o.income_by_category.map((c) => (
                      <li key={c.category_id ?? "none"} className="flex items-center gap-2 py-1.5">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.color }} aria-hidden />
                        <span className="flex-1">{c.name}</span>
                        <span className="text-xs text-[var(--fg-subtle)]">{c.transaction_count}×</span>
                        <span className="font-medium tabular">{formatMinor(c.income, o.currency)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>
            <Card>
              <div id="merchants" className="mb-4 flex items-center gap-2 scroll-mt-24">
                <h2 className="font-semibold">Top merchants</h2>
                <a href={csv("merchants")} className={cn(btn, "ml-auto")}><Download className="h-4 w-4" aria-hidden /> CSV</a>
              </div>
              <RankedBars
                rows={merchantBars(o, account)}
                currency={o.currency}
                empty="No merchants recognised in this period."
                footer={
                  o.other_merchants && (
                    <p className="mt-4 flex justify-between border-t border-[var(--border)] pt-3 text-sm text-[var(--fg-subtle)]">
                      <span>Everything else ({o.other_merchants.transaction_count}×, including spending with no merchant)</span>
                      <span className="tabular">{formatMinor(o.other_merchants.net_spending, o.currency)}</span>
                    </p>
                  )
                }
              />
            </Card>
          </div>

          <BalancesNote o={o} />
          <p className="text-xs text-[var(--fg-subtle)]">
            Every figure here is calculated from your recorded transactions: posted income and spending only, refunds deducted from spending, transfers between your own accounts and adjustments excluded. The full transaction list is available as a CSV on the <Link href="/transactions" className="underline">Transactions</Link> page.
          </p>
        </>
      )}
    </div>
  );
}
