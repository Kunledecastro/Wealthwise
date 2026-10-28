"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { BalanceStatusBadge, Money } from "@/components/money";
import { TransactionForm } from "@/components/transaction-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Sheet } from "@/components/ui/sheet";
import { ACCOUNT_TYPE_LABEL, type Summary } from "@/lib/api";
import { formatDate, formatMinor } from "@/lib/money";
import { useLoad } from "@/lib/use-load";

export default function HomePage() {
  return (
    <AppShell>
      <Home />
    </AppShell>
  );
}

function Stat({ label, minor, hint, tone }: { label: string; minor: number; hint?: string; tone?: "good" | "bad" }) {
  return (
    <Card className="p-4 sm:p-5">
      <p className="text-sm text-[var(--fg-subtle)]">{label}</p>
      <p className={`mt-1 text-xl font-semibold sm:text-2xl ${tone === "bad" ? "text-[var(--danger)]" : tone === "good" ? "text-[var(--accent-strong)]" : ""}`}>
        <Money minor={minor} />
      </p>
      {hint && <p className="mt-1 text-xs text-[var(--fg-subtle)]">{hint}</p>}
    </Card>
  );
}

function Home() {
  const { me } = useAuth();
  const { data, error, reload } = useLoad<Summary>("/api/ledger/summary");
  const [adding, setAdding] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  if (!me) return null;

  const s = data?.summaries.find((x) => x.currency === "NGN");
  const monthName = data ? new Date(data.date_from + "T00:00:00Z").toLocaleString("en-NG", { month: "long", year: "numeric", timeZone: "UTC" }) : "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Welcome, {me.display_name}</h1>
          <p className="text-[var(--fg-subtle)]">{monthName || "Spend wisely. Grow steadily."}</p>
        </div>
        {data && data.accounts.length > 0 && (
          <Button className="ml-auto" onClick={() => setAdding(true)}><Plus className="h-4 w-4" aria-hidden /> Add transaction</Button>
        )}
      </div>
      {flash && <Alert kind="success">{flash}</Alert>}
      {error && <Alert>{error}</Alert>}
      {!data && !error && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}

      {data && data.accounts.length === 0 && (
        <Card>
          <h2 className="font-semibold">Start by adding your accounts</h2>
          <p className="mt-1 text-sm text-[var(--fg-subtle)]">
            Add your bank accounts, wallets and cash with today&apos;s balance. Then record income and spending as it happens.
          </p>
          <Link href="/accounts" className="mt-4 inline-flex min-h-10 items-center rounded-md bg-[var(--accent)] px-4 text-sm font-medium text-[var(--accent-fg)] hover:bg-[var(--accent-hover)]">
            Add an account
          </Link>
        </Card>
      )}

      {data && data.accounts.length > 0 && (
        <>
          <section aria-labelledby="month-h" className="space-y-3">
            <h2 id="month-h" className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">
              This month · {formatDate(data.date_from)} – {formatDate(data.date_to)}
            </h2>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Income" minor={s?.income ?? 0} />
              <Stat label="Spending" minor={s?.net_spending ?? 0} hint={s && s.refunds > 0 ? `After refunds of ${formatMinor(s.refunds)}` : s && s.fees > 0 ? "Includes bank fees" : undefined} />
              <Stat label="Net cash flow" minor={s?.net_cash_flow ?? 0} tone={s ? (s.net_cash_flow < 0 ? "bad" : s.net_cash_flow > 0 ? "good" : undefined) : undefined} />
              <Stat label="Pending" minor={(s?.pending_in ?? 0) - (s?.pending_out ?? 0)} hint={s && (s.pending_in || s.pending_out) ? "Not yet counted above" : "Nothing pending"} />
            </div>
            <p className="text-xs text-[var(--fg-subtle)]">Transfers between your own accounts and balance adjustments are not counted as income or spending.</p>
          </section>

          <section aria-labelledby="acct-h" className="space-y-3">
            <div className="flex items-center gap-2">
              <h2 id="acct-h" className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">Balances</h2>
              <Link href="/accounts" className="ml-auto text-sm text-[var(--accent)] hover:underline">Manage</Link>
            </div>
            <Card className="p-0 sm:p-0">
              <ul className="divide-y divide-[var(--border)]">
                {data.accounts.map((a) => (
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
                <li className="flex items-center gap-3 bg-[var(--muted)] px-4 py-3">
                  <p className="flex-1 font-semibold">Total</p>
                  <Money minor={data.balance_totals.NGN ?? 0} className="font-semibold" />
                </li>
              </ul>
            </Card>
          </section>
        </>
      )}

      <Sheet title="Add transaction" open={adding} onClose={() => setAdding(false)}>
        {adding && data && (
          <TransactionForm accounts={data.accounts} onDone={(msg) => { setAdding(false); setFlash(msg); reload(); }} />
        )}
      </Sheet>
    </div>
  );
}
