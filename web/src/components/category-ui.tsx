"use client";

import { useState } from "react";
import { Alert } from "./ui/alert";
import { Button } from "./ui/button";
import { api, ApiError, categoryKindFor, type Category, type RuleSuggestion } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

const SOURCE_LABEL: Record<string, string> = {
  user: "You chose",
  rule: "Your rule",
  system: "Automatic",
  linked: "Same as original",
  ai: "AI suggestion",
};

/** Category chip: colour dot + name, or a clear "needs review"/"uncategorised" state. */
export function CategoryBadge({
  name,
  color,
  needsReview,
  reason,
  className,
}: {
  name: string | null;
  color: string | null;
  needsReview?: boolean;
  reason?: string | null;
  className?: string;
}) {
  if (!name) {
    return (
      <span
        title={reason ?? undefined}
        className={cn(
          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
          needsReview ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" : "bg-[var(--muted)] text-[var(--fg-subtle)]",
          className,
        )}
      >
        {needsReview ? "Needs a category" : "Uncategorised"}
      </span>
    );
  }
  return (
    <span title={reason ?? undefined} className={cn("inline-flex max-w-full items-center gap-1.5 rounded-full bg-[var(--muted)] px-2 py-0.5 text-xs", className)}>
      <span aria-hidden className="h-2 w-2 shrink-0 rounded-full" style={{ background: color ?? "#94a3b8" }} />
      <span className="truncate">{name}</span>
      {needsReview && <span className="font-semibold text-amber-700 dark:text-amber-300">· check</span>}
    </span>
  );
}

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? "";
}

/** <select> of categories that fit a transaction type. Value "" = automatic/none. */
export function CategorySelect({
  categories,
  txnKind,
  value,
  onChange,
  id,
  label,
  emptyLabel = "— Uncategorised —",
  className,
}: {
  categories: Category[];
  txnKind: string;
  value: string;
  onChange: (v: string) => void;
  id?: string;
  label?: string;
  emptyLabel?: string;
  className?: string;
}) {
  const want = categoryKindFor(txnKind);
  const options = categories.filter((c) => !c.is_archived && c.kind === want);
  return (
    <select
      id={id}
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "min-h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)]",
        className,
      )}
    >
      <option value="">{emptyLabel}</option>
      {options.map((c) => (
        <option key={c.id} value={c.id}>{c.name}</option>
      ))}
    </select>
  );
}

/** Loads the signed-in user's categories (shared by many screens). */
export function useCategories() {
  return useLoad<Category[]>("/api/categories");
}

/**
 * After the user picks a category: offer a rule for the merchant ("Always put SHOPRITE in
 * Food & groceries?") and to apply it to similar transactions. Nothing is created unless
 * they say yes.
 */
export function LearnPrompt({ transactionId, onDone }: { transactionId: string; onDone: (msg: string | null) => void }) {
  const { data: s } = useLoad<RuleSuggestion>(`/api/categories/suggestion?transaction_id=${transactionId}`);
  const [pattern, setPattern] = useState<string | null>(null);
  const [applyExisting, setApplyExisting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!s || !s.pattern || !s.category_id) return null;
  const pat = pattern ?? s.pattern;

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ applied_to: number }>("/api/categories/rules", {
        method: "POST",
        body: { category_id: s!.category_id, pattern: pat, match_type: "contains", apply_to_existing: applyExisting, created_from: "user_correction" },
      });
      onDone(`Rule saved. ${r.applied_to ? `${r.applied_to} similar transaction${r.applied_to === 1 ? "" : "s"} updated.` : "New matching transactions will use it."}`);
    } catch (e) {
      setError(e instanceof ApiError ? (e.fieldErrors[0]?.message ?? e.message) : "Could not save the rule.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-[var(--accent)]/40 bg-[var(--accent-bg)] p-3 text-sm">
      <p>
        Always put transactions containing{" "}
        <input
          aria-label="Text to match"
          value={pat}
          onChange={(e) => setPattern(e.target.value.toUpperCase())}
          className="inline-block w-36 rounded border border-[var(--border)] bg-[var(--surface)] px-1.5 py-0.5 font-mono text-xs"
          maxLength={100}
        />{" "}
        in <strong>{s.category_name}</strong>?
      </p>
      {s.similar_count > 0 && pattern === null && (
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={applyExisting} onChange={(e) => setApplyExisting(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
          Also update {s.similar_count} similar transaction{s.similar_count === 1 ? "" : "s"} (never ones you categorised yourself)
        </label>
      )}
      {pattern !== null && (
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={applyExisting} onChange={(e) => setApplyExisting(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
          Also update matching transactions you haven&apos;t categorised yourself
        </label>
      )}
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <Button size="sm" loading={busy} disabled={pat.trim().length < 2} onClick={create}>Create rule</Button>
        <Button size="sm" variant="ghost" onClick={() => onDone(null)}>No thanks</Button>
      </div>
    </div>
  );
}
