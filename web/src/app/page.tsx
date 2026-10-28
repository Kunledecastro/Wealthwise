"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { BarChart3, Plus } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { BalanceStatusBadge, Money } from "@/components/money";
import { BalancesNote, Kpis, PeriodFilters, RankedBars, categoryBars, merchantBars, pageQuery, useOverview, useReportParams } from "@/components/reports/report-bits";
import { TrendChart } from "@/components/reports/trend-chart";
import { TransactionForm } from "@/components/transaction-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Sheet } from "@/components/ui/sheet";
import { ACCOUNT_TYPE_LABEL, KIND_LABEL, type Account, type TransactionPage } from "@/lib/api";
import { formatDate } from "@/lib/money";
import { periodLabel } from "@/lib/periods";
import { useLoad } from "@/lib/use-load";

export default function HomePage() {
  return (
    <AppShell>
      <Suspense fallback={<p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}>
        <Home />
      </Suspense>
    </AppShell>
  );
}

const linkCls = "text-sm text-[var(--accent)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] rounded";

function Home() {
  const { me } = useAuth();
  const tz = me?.preferences.timezone ?? "Africa/Lagos";
  const { period, account, today } = useReportParams(tz);
  const accounts = useLoad<Account[]>("/api/accounts");
  const { data: o, error, reload } = useOverview(period, account);
  const recent = useLoad<TransactionPage>(`/api/transactions?page_size=5${account ? `&account_id=${account}` : ""}&v=${o?.summary.transaction_count ?? 0}`);
  const [adding, setAdding] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  if (!me) return null;

  const noAccounts = accounts.data && accounts.data.length === 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Welcome, {me.display_name}</h1>
          <p className="text-[var(--fg-subtle)]">{o ? periodLabel(o.date_from, o.date_to) : "Spend wisely. Grow steadily."}</p>
        </div>
        {accounts.data && accounts.data.length > 0 && (
          <Button className="ml-auto" onClick={() => setAdding(true)}><Plus className="h-4 w-4" aria-hidden /> Add transaction</Button>
        )}
      </div>
      {flash && <Alert kind="success">{flash}</Alert>}
      {error && <Alert>{error}</Alert>}

      {noAccounts && (
        <Card>
          <h2 className="font-semibold">Start by adding your accounts</h2>
          <p className="mt-1 text-sm text-[var(--fg-subtle)]">
            Add your bank accounts, wallets and cash with today&apos;s balance. Then record income and spending as it happens, or import a bank statement.
          </p>
          <Link href="/accounts" className="mt-4 inline-flex min-h-10 items-center rounded-md bg-[var(--accent)] px-4 text-sm font-medium text-[var(--accent-fg)] hover:bg-[var(--accent-hover)]">
            Add an account
          </Link>
        </Card>
      )}

      {accounts.data && accounts.data.length > 0 && (
        <>
          <PeriodFilters period={period} account={account} today={today} accounts={accounts.data} />

          {o && o.needs_review_count > 0 && (
            <Alert kind="info">
              {o.needs_review_count} transaction{o.needs_review_count === 1 ? " needs" : "s need"} a category, so the category breakdown may be incomplete.{" "}
              <Link href="/review" className="font-medium underline">Review now</Link>
            </Alert>
          )}
          {o && o.other_currencies.length > 0 && (
            <Alert kind="info">Figures are in {o.currency} only. You also have activity in {o.other_currencies.join(", ")}, which is never added to naira totals.</Alert>
          )}
          {!o && !error && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}

          {o && (
            <>
              <section aria-label="Totals for the period" className="space-y-2">
                <Kpis o={o} />
                <p className="text-xs text-[var(--fg-subtle)]">Transfers between your own accounts and balance adjustments are not counted as income or spending.</p>
              </section>

              <Card>
                <TrendChart key={`${o.date_from}-${o.granularity}`} series={o.series} granularity={o.granularity} title={o.granularity === "day" ? "Spending by day" : "Income and spending"} />
                <div className="mt-3 text-right">
                  <Link href={`/reports?${pageQuery(period, account)}`} className={`${linkCls} inline-flex items-center gap-1`}>
                    <BarChart3 className="h-4 w-4" aria-hidden /> Full report, CSV and print
                  </Link>
                </div>
              </Card>

              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <div className="mb-4 flex items-center gap-2">
                    <h2 className="font-semibold">Top categories</h2>
                    <Link href={`/reports?${pageQuery(period, account)}#categories`} className={`ml-auto ${linkCls}`}>All</Link>
                  </div>
                  <RankedBars rows={categoryBars(o, account, 6)} currency={o.currency} empty="No spending in this period." />
                </Card>
                <Card>
                  <div className="mb-4 flex items-center gap-2">
                    <h2 className="font-semibold">Top merchants</h2>
                    <Link href={`/reports?${pageQuery(period, account)}#merchants`} className={`ml-auto ${linkCls}`}>All</Link>
                  </div>
                  <RankedBars rows={merchantBars(o, account, 6)} currency={o.currency} empty="No merchants recognised in this period." />
                </Card>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <section aria-labelledby="acct-h" className="space-y-3">
                  <div className="flex items-center gap-2">
                    <h2 id="acct-h" className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">Balances today</h2>
                    <Link href="/accounts" className={`ml-auto ${linkCls}`}>Manage</Link>
                  </div>
                  <Card className="p-0 sm:p-0">
                    <ul className="divide-y divide-[var(--border)]">
                      {o.accounts.map((a) => (
                        <li key={a.id}>
                          <Link href={`/transactions?account=${a.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-[var(--muted)] focus-visible:bg-[var(--muted)] focus-visible:outline-none">
                            <div className="min-w-0 flex-1">
                              <p className="truncate font-medium">{a.display_name}</p>
                              <p className="text-sm text-[var(--fg-subtle)]">{ACCOUNT_TYPE_LABEL[a.type]}{a.mask && ` · ••${a.mask}`}</p>
                              <div className="mt-1"><BalanceStatusBadge balance={a.balance} currency={a.currency} /></div>
                            </div>
                            <Money minor={a.balance.posted_minor} currency={a.currency} className="font-semibold" />
                          </Link>
                        </li>
                      ))}
                      {Object.entries(o.balance_totals).map(([cur, total]) => (
                        <li key={cur} className="flex items-center gap-3 bg-[var(--muted)] px-4 py-3">
                          <p className="flex-1 font-semibold">Total{Object.keys(o.balance_totals).length > 1 ? ` (${cur})` : ""}</p>
                          <Money minor={total} currency={cur} className="font-semibold" />
                        </li>
                      ))}
                    </ul>
                  </Card>
                  <BalancesNote o={o} />
                </section>

                <section aria-labelledby="recent-h" className="space-y-3">
                  <div className="flex items-center gap-2">
                    <h2 id="recent-h" className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">Recent transactions</h2>
                    <Link href="/transactions" className={`ml-auto ${linkCls}`}>All</Link>
                  </div>
                  <Card className="p-0 sm:p-0">
                    {recent.data && recent.data.items.length === 0 && <p className="p-4 text-sm text-[var(--fg-subtle)]">No transactions yet.</p>}
                    <ul className="divide-y divide-[var(--border)]">
                      {recent.data?.items.map((t) => (
                        <li key={t.id} className="flex items-center gap-3 px-4 py-3">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">{t.merchant || t.narration || KIND_LABEL[t.kind]}</p>
                            <p className="text-xs text-[var(--fg-subtle)]">
                              {formatDate(t.transaction_date)} · {t.category_name ?? KIND_LABEL[t.kind]}
                              {t.status !== "posted" && ` · ${t.status}`}
                            </p>
                          </div>
                          <Money minor={t.direction === "debit" ? -t.amount_minor : t.amount_minor} currency={t.currency} className="text-sm font-medium" />
                        </li>
                      ))}
                    </ul>
                  </Card>
                </section>
              </div>
            </>
          )}
        </>
      )}

      <Sheet title="Add transaction" open={adding} onClose={() => setAdding(false)}>
        {adding && accounts.data && (
          <TransactionForm
            accounts={accounts.data}
            onDone={(msg) => {
              setAdding(false);
              setFlash(msg);
              reload();
              accounts.reload();
            }}
          />
        )}
      </Sheet>
    </div>
  );
}
