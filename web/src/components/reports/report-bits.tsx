"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { useState } from "react";
import { Money } from "@/components/money";
import { Card } from "@/components/ui/card";
import type { Account, MerchantRow, Overview, ReportCategoryRow } from "@/lib/api";
import { formatMinor, todayIn } from "@/lib/money";
import { PRESETS, isIsoDate, periodFromParams, periodLabel, periodToParams, type Period, type PresetId } from "@/lib/periods";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";
import { useChartTheme } from "./chart-theme";

/** Period + account, kept in the URL so views can be bookmarked, shared with yourself, and printed. */
export function useReportParams(timezone: string) {
  const params = useSearchParams();
  const today = todayIn(timezone);
  const period = periodFromParams(new URLSearchParams(params.toString()), today);
  const account = params.get("account") ?? "";
  return { period, account, today };
}

export function useSetReportParams() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  return (next: { period?: Period; account?: string; extra?: Record<string, string | null> }) => {
    const p = new URLSearchParams(params.toString());
    if (next.period) {
      ["period", "from", "to"].forEach((k) => p.delete(k));
      Object.entries(periodToParams(next.period)).forEach(([k, v]) => p.set(k, v));
    }
    if (next.account !== undefined) {
      if (next.account) p.set("account", next.account);
      else p.delete("account");
    }
    Object.entries(next.extra ?? {}).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)));
    router.replace(`${pathname}?${p}`, { scroll: false });
  };
}

export function overviewQuery(period: Period, account: string, extra: Record<string, string> = {}): string {
  const q = new URLSearchParams({ date_from: period.from, date_to: period.to, ...extra });
  if (account) q.set("account_id", account);
  return q.toString();
}

/** Same filters, as a query string for the app's own pages (reports, print). */
export function pageQuery(period: Period, account: string, extra: Record<string, string> = {}): string {
  const q = new URLSearchParams({ ...periodToParams(period), ...extra });
  if (account) q.set("account", account);
  return q.toString();
}

export function PeriodFilters({ period, account, today, accounts }: { period: Period; account: string; today: string; accounts: Account[] }) {
  const set = useSetReportParams();

  function choose(id: PresetId) {
    if (id === "custom") set({ period: { preset: "custom", from: period.from, to: period.to } });
    else set({ period: periodFromParams(new URLSearchParams({ period: id }), today) });
  }

  return (
    <div className="flex flex-wrap items-end gap-2 print:hidden">
      <div role="group" aria-label="Period" className="flex flex-wrap gap-1">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            aria-pressed={period.preset === p.id}
            onClick={() => choose(p.id)}
            className={cn(
              "min-h-9 rounded-full border px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
              period.preset === p.id ? "border-[var(--fg)] bg-[var(--fg)] font-medium text-[var(--bg)]" : "border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--muted)]",
            )}
          >
            {p.label}
          </button>
        ))}
      </div>
      {period.preset === "custom" && <CustomRange key={`${period.from}|${period.to}`} period={period} />}
      {accounts.length > 1 && (
        <label className="ml-auto text-xs text-[var(--fg-subtle)]">
          <span className="sr-only sm:not-sr-only">Account</span>
          <select value={account} onChange={(e) => set({ account: e.target.value })} className="mt-1 block min-h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 text-sm text-[var(--fg)]">
            <option value="">All accounts</option>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
          </select>
        </label>
      )}
    </div>
  );
}

function CustomRange({ period }: { period: Period }) {
  const set = useSetReportParams();
  const [from, setFrom] = useState(period.from);
  const [to, setTo] = useState(period.to);
  const customValid = isIsoDate(from) && isIsoDate(to) && from <= to;
  return (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (customValid) set({ period: { preset: "custom", from, to } });
          }}
        >
          <label className="text-xs text-[var(--fg-subtle)]">
            From
            <input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} className="mt-1 block min-h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 text-sm text-[var(--fg)]" />
          </label>
          <label className="text-xs text-[var(--fg-subtle)]">
            To
            <input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} className="mt-1 block min-h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 text-sm text-[var(--fg)]" />
          </label>
          <button type="submit" disabled={!customValid} className="min-h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-sm font-medium hover:bg-[var(--muted)] disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
            Apply
          </button>
        </form>
  );
}

export function useOverview(period: Period, account: string, extra: Record<string, string> = {}) {
  return useLoad<Overview>(`/api/reports/overview?${overviewQuery(period, account, extra)}`);
}

/** "▲ 12% vs 1–28 Sep" — words and an arrow, never colour alone. */
export function Change({ pct, prevFrom, prevTo, goodWhenUp }: { pct: number | null; prevFrom: string; prevTo: string; goodWhenUp?: boolean }) {
  const vs = `vs ${periodLabel(prevFrom, prevTo)}`;
  if (pct === null) return <span className="text-xs text-[var(--fg-subtle)]">No comparison for {periodLabel(prevFrom, prevTo)}</span>;
  const Icon = pct > 0 ? ArrowUpRight : pct < 0 ? ArrowDownRight : ArrowRight;
  const word = pct > 0 ? "up" : pct < 0 ? "down" : "no change";
  const good = goodWhenUp === undefined || pct === 0 ? null : (pct > 0) === goodWhenUp;
  return (
    <span className={cn("inline-flex items-center gap-0.5 text-xs", good === false ? "text-[var(--danger)]" : good ? "text-[var(--accent-strong)]" : "text-[var(--fg-subtle)]")}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      <span>
        <span className="sr-only">{word} </span>
        {pct === 0 ? "No change" : `${Math.abs(pct)}%`} <span className="text-[var(--fg-subtle)]">{vs}</span>
      </span>
    </span>
  );
}

export function Kpis({ o }: { o: Overview }) {
  const s = o.summary;
  const prev = o.previous;
  const tile = (label: string, minor: number, change: React.ReactNode, hint?: string, tone?: "good" | "bad") => (
    <Card className="p-4 sm:p-5 print:border-0 print:p-2">
      <p className="text-sm text-[var(--fg-subtle)]">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold tabular sm:text-2xl", tone === "bad" && "text-[var(--danger)]", tone === "good" && "text-[var(--accent-strong)]")}>
        <Money minor={minor} currency={o.currency} />
      </p>
      <div className="mt-1">{change}</div>
      {hint && <p className="mt-0.5 text-xs text-[var(--fg-subtle)]">{hint}</p>}
    </Card>
  );
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 print:grid-cols-4">
      {tile("Income", s.income, <Change pct={o.changes.income} prevFrom={prev.date_from} prevTo={prev.date_to} goodWhenUp />)}
      {tile(
        "Spending",
        s.net_spending,
        <Change pct={o.changes.net_spending} prevFrom={prev.date_from} prevTo={prev.date_to} goodWhenUp={false} />,
        s.refunds > 0 ? `After refunds of ${formatMinor(s.refunds, o.currency)}` : s.fees > 0 ? `Includes ${formatMinor(s.fees, o.currency)} bank fees` : undefined,
      )}
      {tile(
        "Net cash flow",
        s.net_cash_flow,
        <span className="text-xs text-[var(--fg-subtle)]">{formatMinor(prev.summary.net_cash_flow, o.currency)} {`in ${periodLabel(prev.date_from, prev.date_to)}`}</span>,
        "Income minus spending",
        s.net_cash_flow < 0 ? "bad" : s.net_cash_flow > 0 ? "good" : undefined,
      )}
      {tile(
        "Pending",
        s.pending_in - s.pending_out,
        <span className="text-xs text-[var(--fg-subtle)]">{s.pending_in || s.pending_out ? "Not yet counted above" : "Nothing pending"}</span>,
        `${s.transaction_count} posted transaction${s.transaction_count === 1 ? "" : "s"}`,
      )}
    </div>
  );
}

type BarRow = { key: string; label: string; amount: number; count: number; href?: string; swatch?: string };

/** Ranked horizontal bars. The label carries identity; one hue carries magnitude. */
export function RankedBars({ rows, currency, empty, footer }: { rows: BarRow[]; currency: string; empty: string; footer?: React.ReactNode }) {
  const theme = useChartTheme();
  const max = Math.max(1, ...rows.map((r) => r.amount));
  if (rows.length === 0) return <p className="py-6 text-center text-sm text-[var(--fg-subtle)]">{empty}</p>;
  return (
    <>
      <ul className="space-y-2.5">
        {rows.map((r) => {
          const width = r.amount > 0 ? Math.max(2, Math.round((r.amount / max) * 100)) : 0;
          const body = (
            <>
              <div className="flex items-baseline gap-2 text-sm">
                {r.swatch && <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: r.swatch }} aria-hidden />}
                <span className="min-w-0 flex-1 truncate">{r.label}</span>
                <span className="shrink-0 text-xs text-[var(--fg-subtle)]">{r.count}×</span>
                <span className="shrink-0 font-medium tabular">{formatMinor(r.amount, currency)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-[var(--muted)]" aria-hidden>
                <div className="h-1.5 rounded-full" style={{ width: `${width}%`, background: theme.spending }} />
              </div>
            </>
          );
          return (
            <li key={r.key}>
              {r.href ? (
                <Link href={r.href} className="block rounded-md p-1 -m-1 hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">{body}</Link>
              ) : (
                <div className="p-1 -m-1">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
      {footer}
    </>
  );
}

function txnHref(o: Overview, extra: Record<string, string>): string {
  const q = new URLSearchParams({ from: o.date_from, to: o.date_to, status: "posted", ...extra });
  return `/transactions?${q}`;
}

export function categoryBars(o: Overview, account: string, limit?: number): BarRow[] {
  const rows = o.spending_by_category.filter((c) => c.net_spending !== 0);
  return (limit ? rows.slice(0, limit) : rows).map((c: ReportCategoryRow) => ({
    key: c.category_id ?? "none",
    label: c.name,
    amount: c.net_spending,
    count: c.transaction_count,
    swatch: c.color,
    href: txnHref(o, { category: c.category_id ?? "none", ...(account ? { account } : {}) }),
  }));
}

export function merchantBars(o: Overview, account: string, limit?: number): BarRow[] {
  const rows = limit ? o.top_merchants.slice(0, limit) : o.top_merchants;
  return rows.map((m: MerchantRow) => ({
    key: m.merchant ?? "none",
    label: m.merchant ?? "No merchant recognised",
    amount: m.net_spending,
    count: m.transaction_count,
    href: txnHref(o, { merchant: m.merchant ?? "none", ...(account ? { account } : {}) }),
  }));
}

export function BalancesNote({ o }: { o: Overview }) {
  const reconciled = o.accounts.filter((a) => a.balance.status === "reconciled").length;
  return (
    <p className="text-xs text-[var(--fg-subtle)]">
      {o.balances_are_estimated
        ? `Balances are estimated from what you have recorded${reconciled ? ` (${reconciled} of ${o.accounts.length} account${o.accounts.length === 1 ? "" : "s"} match a statement)` : ""}. Reconcile an account against a bank statement to confirm it.`
        : "Every balance matches a recorded statement balance."}
    </p>
  );
}
