"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCheck } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CategoryBadge, CategorySelect, LearnPrompt, useCategories } from "@/components/category-ui";
import { Money } from "@/components/money";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, categoryKindFor, KIND_LABEL, type Category, type Transaction, type TransactionPage } from "@/lib/api";
import { formatDate } from "@/lib/money";
import { useLoad } from "@/lib/use-load";

export default function ReviewPage() {
  return (
    <AppShell>
      <Review />
    </AppShell>
  );
}

function Review() {
  const [page, setPage] = useState(1);
  const list = useLoad<TransactionPage>(`/api/transactions?needs_review=true&page_size=50&page=${page}`);
  const categories = useCategories();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkCat, setBulkCat] = useState("");
  const [flash, setFlash] = useState<{ kind: "success" | "error"; msg: string } | null>(null);
  const [learnFor, setLearnFor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const items = list.data?.items ?? [];
  const selectedItems = items.filter((t) => selected.has(t.id));
  const kinds = new Set(selectedItems.map((t) => categoryKindFor(t.kind)));
  const bulkKind = kinds.size === 1 ? [...kinds][0] : null;

  function toggle(id: string, on: boolean) {
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
  }

  async function assign(body: Record<string, unknown>, ids: string[], learnId?: string) {
    setBusy(true);
    setFlash(null);
    try {
      const r = await api<{ updated: number; skipped: number }>("/api/categories/assign", { method: "POST", body: { ids, ...body } });
      setFlash({ kind: "success", msg: `${r.updated} updated${r.skipped ? `, ${r.skipped} skipped (category didn't fit)` : ""}.` });
      setSelected(new Set());
      setBulkCat("");
      setLearnFor(learnId ?? null);
      list.reload();
    } catch (e) {
      setFlash({ kind: "error", msg: e instanceof ApiError ? e.message : "Could not update." });
    } finally {
      setBusy(false);
    }
  }

  async function reapply() {
    setBusy(true);
    try {
      const r = await api<{ updated: number }>("/api/categories/reapply", { method: "POST", body: {} });
      setFlash({ kind: "success", msg: `Rules re-applied: ${r.updated} transaction${r.updated === 1 ? "" : "s"} changed.` });
      list.reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold">To review</h1>
          <p className="text-sm text-[var(--fg-subtle)]">Transactions Wealthwise couldn&apos;t categorise confidently. Your choices are never overwritten.</p>
        </div>
        <Button variant="secondary" className="ml-auto" loading={busy} onClick={reapply}>Re-run my rules</Button>
      </div>
      {flash && <Alert kind={flash.kind}>{flash.msg}</Alert>}
      {learnFor && <LearnPrompt transactionId={learnFor} onDone={(m) => { setLearnFor(null); if (m) { setFlash({ kind: "success", msg: m }); list.reload(); } }} />}
      {list.error && <Alert>{list.error}</Alert>}
      {list.loading && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}
      {list.data && items.length === 0 && (
        <Card>
          <p className="flex items-center gap-2 font-medium"><CheckCheck className="h-5 w-5 text-[var(--accent)]" aria-hidden /> All caught up</p>
          <p className="mt-1 text-sm text-[var(--fg-subtle)]">Every transaction has a category you can trust. <Link href="/categories" className="text-[var(--accent)] hover:underline">Manage categories and rules</Link></p>
        </Card>
      )}

      {items.length > 0 && categories.data && (
        <>
          <Card className="flex flex-wrap items-center gap-2 p-3 sm:p-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selected.size === items.length}
                onChange={(e) => setSelected(e.target.checked ? new Set(items.map((t) => t.id)) : new Set())}
                className="h-4 w-4 accent-[var(--accent)]"
              />
              Select all ({items.length})
            </label>
            {selected.size > 0 && (
              <>
                <Button size="sm" variant="secondary" loading={busy} onClick={() => assign({ accept_suggestions: true }, [...selected])}>Accept suggestions</Button>
                {bulkKind ? (
                  <span className="flex items-center gap-1">
                    <CategorySelect label="Category for selected" categories={categories.data} txnKind={bulkKind === "income" ? "income" : "expense"} value={bulkCat} onChange={setBulkCat} emptyLabel="Set category…" />
                    <Button size="sm" disabled={!bulkCat} loading={busy} onClick={() => assign({ category_id: bulkCat }, [...selected])}>Apply</Button>
                  </span>
                ) : (
                  <span className="text-xs text-[var(--fg-subtle)]">Select only spending or only income to set one category</span>
                )}
                <Button size="sm" variant="ghost" loading={busy} onClick={() => assign({ uncategorised: true }, [...selected])}>Leave uncategorised</Button>
              </>
            )}
          </Card>
          <Card className="p-0 sm:p-0">
            <ul className="divide-y divide-[var(--border)]">
              {items.map((t) => (
                <ReviewRow key={t.id} t={t} categories={categories.data!} selected={selected.has(t.id)} onToggle={(on) => toggle(t.id, on)}
                  onChoose={(cid) => assign({ category_id: cid }, [t.id], t.id)} onConfirm={() => assign({ accept_suggestions: true }, [t.id], t.id)} busy={busy} />
              ))}
            </ul>
          </Card>
          {list.data && list.data.total > 50 && (
            <nav className="flex items-center justify-end gap-2 text-sm" aria-label="Pages">
              <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <span>Page {page} of {Math.ceil(list.data.total / 50)}</span>
              <Button size="sm" variant="secondary" disabled={page * 50 >= list.data.total} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

function ReviewRow({ t, categories, selected, onToggle, onChoose, onConfirm, busy }: {
  t: Transaction; categories: Category[]; selected: boolean; onToggle: (on: boolean) => void;
  onChoose: (categoryId: string) => void; onConfirm: () => void; busy: boolean;
}) {
  const title = t.merchant || t.narration || KIND_LABEL[t.kind];
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <input type="checkbox" aria-label={`Select ${title}`} checked={selected} onChange={(e) => onToggle(e.target.checked)} className="mt-1 h-4 w-4 accent-[var(--accent)]" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="break-words font-medium">{title}</p>
        <p className="text-sm text-[var(--fg-subtle)]">{formatDate(t.transaction_date)} · {KIND_LABEL[t.kind]} · {t.account_name}</p>
        <div className="flex flex-wrap items-center gap-2">
          <CategoryBadge name={t.category_name} color={t.category_color} needsReview />
          {t.category_reason && <span className="text-xs text-[var(--fg-subtle)]">{t.category_reason}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <CategorySelect label={`Category for ${title}`} categories={categories} txnKind={t.kind} value="" onChange={(v) => v && onChoose(v)} emptyLabel="Choose category…" />
          {t.category_id && <Button size="sm" variant="secondary" disabled={busy} onClick={onConfirm}>Confirm {t.category_name}</Button>}
        </div>
      </div>
      <Money minor={t.amount_minor} currency={t.currency} direction={t.direction} className="font-semibold" />
    </li>
  );
}
