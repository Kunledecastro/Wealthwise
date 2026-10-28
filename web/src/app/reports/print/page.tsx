"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ArrowLeft, Printer } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { Brand } from "@/components/brand";
import { pageQuery, useOverview, useReportParams } from "@/components/reports/report-bits";
import { Alert } from "@/components/ui/alert";
import { ACCOUNT_TYPE_LABEL, type Granularity, type Overview } from "@/lib/api";
import { formatDate, formatMinor } from "@/lib/money";
import { bucketTitle, periodLabel } from "@/lib/periods";

export default function PrintPage() {
  return (
    <AppShell>
      <Suspense fallback={<p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}>
        <PrintSummary />
      </Suspense>
    </AppShell>
  );
}

function share(part: number, whole: number): string {
  if (whole <= 0 || part <= 0) return "";
  const p = Math.round((part / whole) * 100);
  return p === 0 ? "<1%" : `${p}%`;
}

function pct(p: number | null): string {
  return p === null ? "—" : p === 0 ? "0%" : `${p > 0 ? "+" : "−"}${Math.abs(p)}%`;
}

function PrintSummary() {
  const { me } = useAuth();
  const { period, account } = useReportParams(me?.preferences.timezone ?? "Africa/Lagos");
  const g = useSearchParams().get("g");
  const gran = g === "day" || g === "week" || g === "month" ? g : "auto";
  const { data: o, error } = useOverview(period, account, { granularity: gran });

  return (
    <div className="print-sheet space-y-6">
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <Link href={`/reports?${pageQuery(period, account, g ? { g } : {})}`} className="inline-flex min-h-9 items-center gap-1.5 rounded-md px-3 text-sm hover:bg-[var(--muted)]">
          <ArrowLeft className="h-4 w-4" aria-hidden /> Back to reports
        </Link>
        <button type="button" onClick={() => window.print()} disabled={!o} className="ml-auto inline-flex min-h-10 items-center gap-2 rounded-md bg-[var(--accent)] px-4 text-sm font-medium text-[var(--accent-fg)] hover:bg-[var(--accent-hover)] disabled:opacity-50">
          <Printer className="h-4 w-4" aria-hidden /> Print or save as PDF
        </button>
      </div>
      {error && <Alert>{error}</Alert>}
      {!o && !error && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}
      {o && <Sheet o={o} name={me?.display_name ?? ""} filtered={Boolean(account)} />}
    </div>
  );
}

function Row({ label, value, sub, strong }: { label: string; value: string; sub?: string; strong?: boolean }) {
  return (
    <tr className="border-b border-[var(--border)]">
      <th scope="row" className={`py-1.5 pr-4 text-left ${strong ? "font-semibold" : "font-normal"}`}>{label}</th>
      <td className={`py-1.5 text-right tabular ${strong ? "font-semibold" : ""}`}>{value}</td>
      <td className="py-1.5 pl-4 text-right text-xs text-[var(--fg-subtle)] tabular">{sub}</td>
    </tr>
  );
}

function Sheet({ o, name, filtered }: { o: Overview; name: string; filtered: boolean }) {
  const s = o.summary;
  const p = o.previous.summary;
  const cur = o.currency;
  const m = (v: number) => formatMinor(v, cur);
  const cats = o.spending_by_category.filter((c) => c.net_spending !== 0);
  const g: Granularity = o.granularity;
  const acctName = filtered && o.accounts.length === 1 ? o.accounts[0]!.display_name : null;

  return (
    <article className="mx-auto max-w-3xl rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm print:max-w-none print:rounded-none print:border-0 print:p-0">
      <header className="flex flex-wrap items-start gap-4 border-b border-[var(--border)] pb-4">
        <div>
          <Brand />
          <h1 className="mt-3 text-xl font-semibold">Money summary · {periodLabel(o.date_from, o.date_to)}</h1>
          <p className="text-[var(--fg-subtle)]">
            {name} · {acctName ?? "All accounts"} · {cur}
          </p>
        </div>
        <p className="ml-auto text-right text-xs text-[var(--fg-subtle)]">
          Generated {formatDate(o.generated_on)}
          <br />
          Compared with {periodLabel(o.previous.date_from, o.previous.date_to)}
        </p>
      </header>

      <section className="mt-5 break-inside-avoid">
        <h2 className="mb-2 font-semibold">Totals</h2>
        <table className="w-full">
          <thead className="sr-only">
            <tr><th>Measure</th><th>This period</th><th>Change vs comparison period</th></tr>
          </thead>
          <tbody>
            <Row label="Income" value={m(s.income)} sub={`${pct(o.changes.income)} (was ${m(p.income)})`} />
            <Row label="Spending (after refunds)" value={m(s.net_spending)} sub={`${pct(o.changes.net_spending)} (was ${m(p.net_spending)})`} />
            {s.refunds > 0 && <Row label="  of which refunds deducted" value={m(s.refunds)} />}
            {s.fees > 0 && <Row label="  of which bank fees" value={m(s.fees)} />}
            <Row label="Net cash flow" value={m(s.net_cash_flow)} sub={`was ${m(p.net_cash_flow)}`} strong />
            {(s.pending_in > 0 || s.pending_out > 0) && <Row label="Pending (not counted above)" value={`+${m(s.pending_in)} / −${m(s.pending_out)}`} />}
            <Row label="Posted transactions" value={String(s.transaction_count)} sub={pct(o.changes.transaction_count)} />
          </tbody>
        </table>
      </section>

      <div className="mt-5 grid gap-6 sm:grid-cols-2 print:grid-cols-2">
        <section className="break-inside-avoid">
          <h2 className="mb-2 font-semibold">Spending by category</h2>
          {cats.length === 0 ? <p className="text-[var(--fg-subtle)]">No spending.</p> : (
            <table className="w-full">
              <tbody>
                {cats.map((c) => (
                  <tr key={c.category_id ?? "none"} className="border-b border-[var(--border)]">
                    <th scope="row" className="py-1 pr-2 text-left font-normal">{c.name}</th>
                    <td className="py-1 text-right tabular">{m(c.net_spending)}</td>
                    <td className="py-1 pl-2 text-right text-xs text-[var(--fg-subtle)] tabular">{share(c.net_spending, s.net_spending)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="break-inside-avoid">
          <h2 className="mb-2 font-semibold">Top merchants</h2>
          {o.top_merchants.length === 0 ? <p className="text-[var(--fg-subtle)]">None recognised.</p> : (
            <table className="w-full">
              <tbody>
                {o.top_merchants.map((x) => (
                  <tr key={x.merchant ?? "none"} className="border-b border-[var(--border)]">
                    <th scope="row" className="py-1 pr-2 text-left font-normal">{x.merchant}</th>
                    <td className="py-1 text-right tabular">{m(x.net_spending)}</td>
                  </tr>
                ))}
                {o.other_merchants && (
                  <tr className="border-b border-[var(--border)] text-[var(--fg-subtle)]">
                    <th scope="row" className="py-1 pr-2 text-left font-normal">Everything else</th>
                    <td className="py-1 text-right tabular">{m(o.other_merchants.net_spending)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </section>
      </div>

      <section className="mt-5">
        <h2 className="mb-2 font-semibold">{g === "day" ? "By day" : g === "week" ? "By week" : "By month"}</h2>
        <table className="w-full tabular">
          <thead>
            <tr className="border-b border-[var(--border)] text-xs text-[var(--fg-subtle)]">
              <th scope="col" className="py-1 text-left font-medium">Period</th>
              <th scope="col" className="py-1 text-right font-medium">Income</th>
              <th scope="col" className="py-1 text-right font-medium">Spending</th>
              <th scope="col" className="py-1 text-right font-medium">Net</th>
            </tr>
          </thead>
          <tbody>
            {o.series.filter((r) => g !== "day" || r.transaction_count > 0 || r.net_spending !== 0).map((r) => (
              <tr key={r.date_from} className="border-b border-[var(--border)] break-inside-avoid">
                <th scope="row" className="py-1 text-left font-normal">{bucketTitle(r.date_from, r.date_to, g)}</th>
                <td className="py-1 text-right">{m(r.income)}</td>
                <td className="py-1 text-right">{m(r.net_spending)}</td>
                <td className="py-1 text-right">{m(r.net_cash_flow)}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <th scope="row" className="py-1.5 text-left">Total</th>
              <td className="py-1.5 text-right">{m(s.income)}</td>
              <td className="py-1.5 text-right">{m(s.net_spending)}</td>
              <td className="py-1.5 text-right">{m(s.net_cash_flow)}</td>
            </tr>
          </tbody>
        </table>
        {g === "day" && <p className="mt-1 text-xs text-[var(--fg-subtle)]">Days with no activity are left out.</p>}
      </section>

      <section className="mt-5 break-inside-avoid">
        <h2 className="mb-2 font-semibold">Balances on {formatDate(o.generated_on)}</h2>
        <table className="w-full">
          <tbody>
            {o.accounts.map((a) => (
              <tr key={a.id} className="border-b border-[var(--border)]">
                <th scope="row" className="py-1 pr-2 text-left font-normal">
                  {a.display_name} <span className="text-xs text-[var(--fg-subtle)]">{ACCOUNT_TYPE_LABEL[a.type]}{a.mask ? ` ••${a.mask}` : ""}</span>
                </th>
                <td className="py-1 text-right text-xs text-[var(--fg-subtle)]">
                  {a.balance.status === "reconciled" ? "Matches statement" : a.balance.status === "unreconciled" ? "Differs from statement" : "Estimated"}
                </td>
                <td className="py-1 pl-4 text-right tabular">{formatMinor(a.balance.posted_minor, a.currency)}</td>
              </tr>
            ))}
            {Object.entries(o.balance_totals).map(([c, t]) => (
              <tr key={c} className="font-semibold">
                <th scope="row" className="py-1.5 text-left">Total {c}</th>
                <td />
                <td className="py-1.5 pl-4 text-right tabular">{formatMinor(t, c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <footer className="mt-6 space-y-1 border-t border-[var(--border)] pt-3 text-xs text-[var(--fg-subtle)]">
        <p>
          {o.balances_are_estimated
            ? "Some balances are estimated: they are calculated from transactions recorded in Wealthwise and have not been confirmed against a bank statement."
            : "Every balance matched a recorded bank statement balance when this summary was generated."}
        </p>
        <p>Income and spending count posted transactions only. Refunds are deducted from spending. Transfers between your own accounts and balance adjustments are excluded.{o.other_currencies.length > 0 ? ` Activity in ${o.other_currencies.join(", ")} is not included.` : ""}{o.needs_review_count > 0 ? ` ${o.needs_review_count} transaction(s) were still waiting for a category.` : ""}</p>
        <p>Wealthwise does not connect to your bank. This summary is not a bank statement.</p>
      </footer>
    </article>
  );
}
