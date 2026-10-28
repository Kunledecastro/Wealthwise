import { formatMinor } from "@/lib/money";
import { cn } from "@/lib/utils";

/** Shows an amount; debits get a minus sign, credits a plus, using tabular numbers. */
export function Money({ minor, currency = "NGN", direction, className }: { minor: number; currency?: string; direction?: "debit" | "credit"; className?: string }) {
  const signed = direction === "debit" ? -Math.abs(minor) : direction === "credit" ? Math.abs(minor) : minor;
  const text = formatMinor(signed, currency);
  return (
    <span className={cn("tabular whitespace-nowrap", direction === "credit" && "text-[var(--accent-strong)]", className)}>
      {direction === "credit" ? "+" + text : text}
    </span>
  );
}

export function EstimatedBadge() {
  return (
    <span title="Calculated from your entries and imports; not checked against a bank statement." className="rounded-full bg-[var(--muted)] px-2 py-0.5 text-xs text-[var(--fg-subtle)]">
      Estimated
    </span>
  );
}

type BalanceLike = { status: "estimated" | "reconciled" | "unreconciled"; statement_as_of: string | null; difference_minor: number | null };

/** Whether a balance has been checked against a bank statement (ledger rule B5). */
export function BalanceStatusBadge({ balance, currency = "NGN" }: { balance: BalanceLike; currency?: string }) {
  if (balance.status === "reconciled" && balance.statement_as_of) {
    return (
      <span title="Matches the balance on your bank statement for that date." className="rounded-full bg-[var(--accent-bg)] px-2 py-0.5 text-xs font-medium text-[var(--accent-strong)]">
        ✓ Matches statement · {formatShort(balance.statement_as_of)}
      </span>
    );
  }
  if (balance.status === "unreconciled" && balance.difference_minor !== null) {
    return (
      <span title="Your bank statement shows a different balance for that date. A transaction may be missing, duplicated or entered wrongly." className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
        Differs from statement by {formatMinor(Math.abs(balance.difference_minor), currency)}
      </span>
    );
  }
  return <EstimatedBadge />;
}

function formatShort(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(y!, (m ?? 1) - 1, d ?? 1)));
}

export const STATUS_LABEL: Record<string, string> = { posted: "Completed", pending: "Pending", failed: "Failed", reversed: "Reversed" };

export function StatusPill({ status }: { status: string }) {
  if (status === "posted") return null;
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        status === "pending" && "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
        status === "failed" && "bg-[var(--danger-bg)] text-[var(--danger)]",
        status === "reversed" && "bg-[var(--muted)] text-[var(--fg-subtle)] line-through",
      )}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

