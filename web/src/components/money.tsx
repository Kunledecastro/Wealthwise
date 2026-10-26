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
    <span title="Calculated from your manual entries, not from your bank. Phase 3 adds statement reconciliation." className="rounded-full bg-[var(--muted)] px-2 py-0.5 text-xs text-[var(--fg-subtle)]">
      Manual · estimated
    </span>
  );
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

