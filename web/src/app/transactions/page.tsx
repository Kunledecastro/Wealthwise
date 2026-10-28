"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { ArrowLeftRight, Download, Plus } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CategoryBadge, useCategories } from "@/components/category-ui";
import { Money, STATUS_LABEL, StatusPill } from "@/components/money";
import { TransactionDetail } from "@/components/transaction-detail";
import { TransactionForm } from "@/components/transaction-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { SelectField } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import { KIND_LABEL, type Account, type Transaction, type TransactionPage, type TxnKind } from "@/lib/api";
import { formatDate } from "@/lib/money";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;

export default function TransactionsPage() {
  return (
    <AppShell>
      <Suspense fallback={<p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}>
        <Transactions />
      </Suspense>
    </AppShell>
  );
}

function Transactions() {
  const params = useSearchParams();
  const [filters, setFilters] = useState({
    account: params.get("account") ?? "",
    kind: "",
    status: "",
    from: "",
    to: "",
    q: "",
    category: params.get("category") ?? "",
    review: params.get("review") === "1" ? "1" : "",
  });
  const [page, setPage] = useState(1);
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (filters.account) p.set("account_id", filters.account);
    if (filters.kind) p.set("kind", filters.kind);
    if (filters.status) p.set("status", filters.status);
    if (filters.from) p.set("date_from", filters.from);
    if (filters.to) p.set("date_to", filters.to);
    if (filters.q.trim()) p.set("q", filters.q.trim());
    if (filters.category) p.set("category", filters.category);
    if (filters.review) p.set("needs_review", "true");
    return p;
  }, [filters]);

  const listQuery = new URLSearchParams(query);
  listQuery.set("page", String(page));
  listQuery.set("page_size", String(PAGE_SIZE));
  const list = useLoad<TransactionPage>(`/api/transactions?${listQuery}`);
  const accounts = useLoad<Account[]>("/api/accounts?include_archived=true");
  const categories = useCategories();

  function setFilter(k: keyof typeof filters, v: string) {
    setFilters((f) => ({ ...f, [k]: v }));
    setPage(1);
  }
  function refresh(msg?: string) {
    if (msg) setFlash(msg);
    list.reload();
    accounts.reload();
  }

  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;
  const anyFilter = Object.values(filters).some(Boolean);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Transactions</h1>
        <a
          href={`/api/transactions/export.csv?${query}`}
          className="ml-auto inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface)] px-4 text-sm font-medium hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
        >
          <Download className="h-4 w-4" aria-hidden /> CSV
        </a>
        <Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" aria-hidden /> Add</Button>
      </div>

      {flash && <Alert kind="success">{flash}</Alert>}

      <Card className="p-4 sm:p-4">
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-7">
          <Field label="Search" placeholder="Merchant, description, notes" value={filters.q} onChange={(e) => setFilter("q", e.target.value)} />
          <SelectField label="Account" value={filters.account} onChange={(e) => setFilter("account", e.target.value)}>
            <option value="">All accounts</option>
            {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.display_name}{a.is_archived ? " (archived)" : ""}</option>)}
          </SelectField>
          <SelectField label="Type" value={filters.kind} onChange={(e) => setFilter("kind", e.target.value)}>
            <option value="">All types</option>
            {(Object.keys(KIND_LABEL) as TxnKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </SelectField>
          <SelectField label="Status" value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
            <option value="">Any status</option>
            {Object.entries(STATUS_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </SelectField>
          <SelectField label="Category" value={filters.category} onChange={(e) => setFilter("category", e.target.value)}>
            <option value="">All categories</option>
            <option value="none">Uncategorised</option>
            {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </SelectField>
          <Field label="From" type="date" value={filters.from} onChange={(e) => setFilter("from", e.target.value)} />
          <Field label="To" type="date" value={filters.to} onChange={(e) => setFilter("to", e.target.value)} />
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={filters.review === "1"} onChange={(e) => setFilter("review", e.target.checked ? "1" : "")} className="h-4 w-4 accent-[var(--accent)]" />
          Only show ones that need a category
        </label>
        {anyFilter && (
          <button className="mt-3 text-sm text-[var(--accent)] hover:underline" onClick={() => { setFilters({ account: "", kind: "", status: "", from: "", to: "", q: "", category: "", review: "" }); setPage(1); }}>
            Clear filters
          </button>
        )}
      </Card>

      {list.error && <Alert>{list.error}</Alert>}
      {list.loading && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}
      {list.data && list.data.items.length === 0 && (
        <Card>
          <p className="text-sm text-[var(--fg-subtle)]">
            {anyFilter ? "No transactions match these filters." : "No transactions yet. Use Add to record your first one."}
          </p>
        </Card>
      )}

      {list.data && list.data.items.length > 0 && (
        <Card className="p-0 sm:p-0">
          <ul className="divide-y divide-[var(--border)]">
            {list.data.items.map((t) => <Row key={t.id} t={t} onOpen={() => setOpenId(t.id)} />)}
          </ul>
        </Card>
      )}

      {list.data && list.data.total > 0 && (
        <nav aria-label="Pages" className="flex items-center justify-between text-sm">
          <span className="text-[var(--fg-subtle)]">{list.data.total} transaction{list.data.total === 1 ? "" : "s"}</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <span aria-current="page">Page {page} of {pages}</span>
            <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </nav>
      )}

      <Sheet title="Add transaction" open={adding} onClose={() => setAdding(false)}>
        {adding && accounts.data && (
          <TransactionForm
            accounts={accounts.data}
            defaultAccountId={filters.account || undefined}
            onDone={(msg) => { setAdding(false); refresh(msg); }}
          />
        )}
      </Sheet>
      <Sheet title="Transaction" open={openId !== null} onClose={() => setOpenId(null)}>
        {openId && accounts.data && (
          <TransactionDetail
            id={openId}
            accounts={accounts.data}
            onChanged={(msg, close) => { refresh(msg); if (close) setOpenId(null); }}
            onOpenOther={(id) => setOpenId(id)}
          />
        )}
      </Sheet>
    </div>
  );
}

function Row({ t, onOpen }: { t: Transaction; onOpen: () => void }) {
  const title =
    t.kind === "transfer"
      ? `Transfer ${t.direction === "debit" ? "to" : "from"} ${t.counterpart_account_name ?? "account"}`
      : t.merchant || t.narration || KIND_LABEL[t.kind];
  return (
    <li>
      <button onClick={onOpen} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-[var(--muted)] focus-visible:bg-[var(--muted)] focus-visible:outline-none">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 truncate font-medium">
            {t.kind === "transfer" && <ArrowLeftRight className="h-4 w-4 shrink-0 text-[var(--fg-subtle)]" aria-hidden />}
            <span className="truncate">{title}</span>
          </p>
          <p className="truncate text-sm text-[var(--fg-subtle)]">
            {formatDate(t.transaction_date)} · {KIND_LABEL[t.kind]} · {t.account_name}
          </p>
          {t.kind !== "transfer" && t.kind !== "adjustment" && (
            <CategoryBadge name={t.category_name} color={t.category_color} needsReview={t.needs_review} className="mt-1" />
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <Money minor={t.amount_minor} currency={t.currency} direction={t.direction} className={cn("font-semibold", (t.status === "failed" || t.status === "reversed") && "text-[var(--fg-subtle)] line-through")} />
          <StatusPill status={t.status} />
        </div>
      </button>
    </li>
  );
}
