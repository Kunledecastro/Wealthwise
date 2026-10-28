"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Money } from "@/components/money";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { SelectField } from "@/components/ui/select";
import { api, ApiError, KIND_LABEL, type ColumnRole, type CommitResult, type ImportBatch, type ImportDetail, type ImportRow, type Mapping, type TxnKind } from "@/lib/api";
import { formatDate, formatMinor } from "@/lib/money";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

export default function ImportReviewPage() {
  return (
    <AppShell>
      <Review />
    </AppShell>
  );
}

type Tab = "all" | "new" | "possible_duplicate" | "duplicate" | "error";
const TABS: { key: Tab; label: string; count: (c: Record<string, number>) => number }[] = [
  { key: "all", label: "All", count: (c) => (c.new ?? 0) + (c.duplicate ?? 0) + (c.possible_duplicate ?? 0) + (c.error ?? 0) },
  { key: "new", label: "New", count: (c) => c.new ?? 0 },
  { key: "possible_duplicate", label: "Possible duplicates", count: (c) => c.possible_duplicate ?? 0 },
  { key: "duplicate", label: "Already imported", count: (c) => c.duplicate ?? 0 },
  { key: "error", label: "Problems", count: (c) => c.error ?? 0 },
];

const OUTCOME: Record<ImportRow["outcome"], { label: string; cls: string }> = {
  new: { label: "New", cls: "bg-[var(--accent-bg)] text-[var(--accent-strong)]" },
  possible_duplicate: { label: "Possible duplicate", cls: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
  duplicate: { label: "Already imported", cls: "bg-[var(--muted)] text-[var(--fg-subtle)]" },
  error: { label: "Problem", cls: "bg-[var(--danger-bg)] text-[var(--danger)]" },
};

function Review() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("all");
  const [page, setPage] = useState(1);
  const query = `/api/imports/${id}?page=${page}&page_size=100${tab !== "all" ? `&outcome=${tab}` : ""}`;
  const { data: b, error, reload } = useLoad<ImportDetail>(query);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [setOpening, setSetOpening] = useState(false);
  const [saveMapping, setSaveMapping] = useState(true);
  const [confirmUndo, setConfirmUndo] = useState(false);

  if (error) return <Alert>{error}</Alert>;
  if (!b) return <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>;

  const staged = b.status === "staged";
  const needsColumns = staged && (b.mapping?.header_row == null || (b.counts.new ?? 0) + (b.counts.duplicate ?? 0) + (b.counts.possible_duplicate ?? 0) === 0);

  async function updateRows(updates: { id: string; include?: boolean; kind?: string }[]) {
    setActionError(null);
    try {
      await api<ImportBatch>(`/api/imports/${b!.id}/rows`, { method: "POST", body: { updates } });
      reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Could not update.");
    }
  }

  async function run(action: "commit" | "discard" | "undo") {
    setBusy(action);
    setActionError(null);
    try {
      if (action === "commit") {
        const r = await api<CommitResult>(`/api/imports/${b!.id}/commit`, { method: "POST", body: { set_opening_from_statement: setOpening, save_mapping: saveMapping } });
        setResult(r);
      } else if (action === "discard") {
        await api(`/api/imports/${b!.id}/discard`, { method: "POST", body: {} });
        router.push("/imports");
        return;
      } else {
        await api(`/api/imports/${b!.id}/undo`, { method: "POST", body: {} });
        setConfirmUndo(false);
      }
      reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const selectable = b.rows.filter((r) => r.outcome === "new" || r.outcome === "possible_duplicate");

  return (
    <div className="space-y-5">
      <div>
        <Link href="/imports" className="text-sm text-[var(--accent)] hover:underline">← All imports</Link>
        <h1 className="mt-1 break-words text-2xl font-semibold">{b.filename}</h1>
        <p className="text-sm text-[var(--fg-subtle)]">
          Into <strong>{b.account_name}</strong>
          {b.statement_first_date && b.statement_last_date && ` · ${formatDate(b.statement_first_date)} – ${formatDate(b.statement_last_date)}`}
          {b.sheet_name && ` · sheet “${b.sheet_name}”`}
          {b.adapter === "simulated" && " · simulated demo data"}
        </p>
      </div>

      {result && <CommitSummary r={result} accountId={b.account_id} />}
      {b.status === "undone" && <Alert kind="info">This import was undone. Its transactions were removed and any changes it made were put back.</Alert>}
      {b.status === "discarded" && <Alert kind="info">This import was cancelled. Nothing was saved.</Alert>}
      {b.same_file_imported_at && staged && (
        <Alert kind="info">You already imported this exact file on {new Date(b.same_file_imported_at).toLocaleDateString("en-NG", { dateStyle: "medium" })}. Its rows are marked “Already imported”.</Alert>
      )}
      {b.warnings.map((w) => <Alert key={w}>{w}</Alert>)}
      {actionError && <Alert>{actionError}</Alert>}

      {staged && <ColumnsCard b={b} defaultOpen={needsColumns} onSaved={() => { setPage(1); reload(); }} />}

      {b.statement_closing_balance_minor !== null && (
        <Card className="p-4 sm:p-4">
          <p className="text-sm">
            Statement closing balance on {b.statement_last_date && formatDate(b.statement_last_date)}: <strong><Money minor={b.statement_closing_balance_minor} /></strong>.
            {staged && " After importing, Wealthwise checks its own balance against this figure."}
          </p>
        </Card>
      )}

      <div className="flex gap-1 overflow-x-auto" role="tablist" aria-label="Filter rows">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => { setTab(t.key); setPage(1); }}
            className={cn(
              "shrink-0 rounded-md px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
              tab === t.key ? "bg-[var(--surface)] font-semibold shadow-sm ring-1 ring-[var(--border)]" : "text-[var(--fg-subtle)] hover:bg-[var(--muted)]",
            )}
          >
            {t.label} <span className="tabular text-[var(--fg-subtle)]">{t.count(b.counts)}</span>
          </button>
        ))}
      </div>

      {staged && selectable.length > 0 && (
        <div className="flex flex-wrap gap-2 text-sm">
          <Button size="sm" variant="secondary" onClick={() => updateRows(selectable.map((r) => ({ id: r.id, include: true })))}>Select all on this page</Button>
          <Button size="sm" variant="secondary" onClick={() => updateRows(selectable.map((r) => ({ id: r.id, include: false })))}>Deselect all on this page</Button>
        </div>
      )}

      <Card className="p-0 sm:p-0">
        {b.rows.length === 0 ? (
          <p className="p-4 text-sm text-[var(--fg-subtle)]">No rows here.</p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {b.rows.map((r) => <RowItem key={r.id} r={r} editable={staged} onChange={(u) => updateRows([{ id: r.id, ...u }])} />)}
          </ul>
        )}
      </Card>

      {b.rows_total > b.page_size && (
        <nav aria-label="Pages" className="flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span>Page {page} of {Math.ceil(b.rows_total / b.page_size)}</span>
          <Button size="sm" variant="secondary" disabled={page * b.page_size >= b.rows_total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </nav>
      )}

      {staged && (
        <Card className="sticky bottom-0 z-10 border-[var(--accent)]/40 p-4 shadow-lg sm:p-5">
          <div className="flex flex-wrap items-center gap-4">
            <p className="text-sm"><strong className="tabular">{b.counts.included ?? 0}</strong> row{b.counts.included === 1 ? "" : "s"} selected to import</p>
            <div className="flex flex-col gap-1 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={saveMapping} onChange={(e) => setSaveMapping(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
                Remember these column settings for this account
              </label>
              {b.can_set_opening && (
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={setOpening} onChange={(e) => setSetOpening(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
                  Set the account&apos;s starting balance from this statement ({b.statement_opening_balance_minor !== null && formatMinor(b.statement_opening_balance_minor)} on {b.statement_first_date && formatDate(b.statement_first_date)})
                </label>
              )}
            </div>
            <div className="ml-auto flex gap-2">
              <Button variant="ghost" loading={busy === "discard"} onClick={() => run("discard")}>Cancel import</Button>
              <Button loading={busy === "commit"} disabled={!b.counts.included} onClick={() => run("commit")}>Import {b.counts.included ?? 0}</Button>
            </div>
          </div>
        </Card>
      )}

      {b.status === "committed" && (
        <Card>
          <CardHeader title="Undo this import" description="Removes every transaction this file added and puts back anything it changed (for example transfers it matched). You can import the file again afterwards." />
          {confirmUndo ? (
            <div className="flex flex-wrap gap-2">
              <Button variant="danger" loading={busy === "undo"} onClick={() => run("undo")}>Yes, undo import</Button>
              <Button variant="secondary" onClick={() => setConfirmUndo(false)}>Keep it</Button>
            </div>
          ) : (
            <Button variant="secondary" onClick={() => setConfirmUndo(true)}>Undo import…</Button>
          )}
        </Card>
      )}
    </div>
  );
}

function CommitSummary({ r, accountId }: { r: CommitResult; accountId: string }) {
  const rec = r.reconciliation;
  return (
    <div className="space-y-3">
      <Alert kind="success">
        Imported {r.created} transaction{r.created === 1 ? "" : "s"}
        {r.transfers_linked > 0 && `, matched ${r.transfers_linked} transfer${r.transfers_linked === 1 ? "" : "s"} between your accounts`}
        {r.reversals_linked > 0 && `, linked ${r.reversals_linked} reversal${r.reversals_linked === 1 ? "" : "s"}`}
        {r.opening_balance_set && ", and set the starting balance from the statement"}.{" "}
        <Link href={`/transactions?account=${accountId}`} className="underline">View transactions</Link>
      </Alert>
      {rec && (rec.matches ? (
        <div role="status" className="flex gap-2 rounded-md border border-[var(--accent)]/40 bg-[var(--accent-bg)] px-3 py-2.5 text-sm text-[var(--accent-strong)]">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>Balance check passed: Wealthwise shows <strong>{formatMinor(rec.computed_minor)}</strong> on {formatDate(rec.as_of)}, exactly what your statement says.</span>
        </div>
      ) : (
        <div role="alert" className="flex gap-2 rounded-md border border-amber-400 bg-amber-50 px-3 py-2.5 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            Your statement says <strong>{formatMinor(rec.statement_minor)}</strong> on {formatDate(rec.as_of)} but Wealthwise calculates <strong>{formatMinor(rec.computed_minor)}</strong> (difference {formatMinor(Math.abs(rec.difference_minor))}).
            Common causes: the account&apos;s starting balance or date is wrong, a row was skipped, or a transaction was entered twice.
          </span>
        </div>
      ))}
    </div>
  );
}

function RowItem({ r, editable, onChange }: { r: ImportRow; editable: boolean; onChange: (u: { include?: boolean; kind?: string }) => void }) {
  const canToggle = editable && (r.outcome === "new" || r.outcome === "possible_duplicate");
  const label = r.narration || (r.direction === "credit" ? "Money in" : "Money out");
  return (
    <li className={cn("flex items-start gap-3 px-4 py-3", !r.include && r.outcome !== "new" && "opacity-75")}>
      <input
        type="checkbox"
        aria-label={`Import row ${r.row_number}`}
        checked={r.include}
        disabled={!canToggle}
        onChange={(e) => onChange({ include: e.target.checked })}
        className="mt-1 h-4 w-4 accent-[var(--accent)]"
      />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 break-words font-medium">{label}</p>
          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", OUTCOME[r.outcome].cls)}>{OUTCOME[r.outcome].label}</span>
        </div>
        <p className="text-sm text-[var(--fg-subtle)]">
          Row {r.row_number}
          {r.transaction_date && ` · ${formatDate(r.transaction_date)}`}
          {r.external_ref && ` · Ref ${r.external_ref}`}
          {r.balance_after_minor !== null && ` · Balance after ${formatMinor(r.balance_after_minor)}`}
        </p>
        {r.error && <p className="text-sm text-[var(--danger)]">{r.error}</p>}
        {r.note && <p className="text-sm text-[var(--fg-subtle)]">{r.note}</p>}
        {editable && r.allowed_kinds.length > 0 && r.outcome !== "duplicate" ? (
          <select
            aria-label={`Type for row ${r.row_number}`}
            value={r.kind ?? ""}
            onChange={(e) => onChange({ kind: e.target.value })}
            className="mt-1 min-h-8 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)]"
          >
            {r.allowed_kinds.map((k) => (
              <option key={k} value={k}>{k === "transfer" ? "Transfer between my accounts" : KIND_LABEL[k as TxnKind] ?? k}</option>
            ))}
          </select>
        ) : r.kind && r.outcome !== "error" ? (
          <p className="text-sm">{r.kind === "transfer" ? "Transfer between my accounts" : KIND_LABEL[r.kind as TxnKind] ?? r.kind}</p>
        ) : null}
      </div>
      {r.amount_minor !== null && r.direction && (
        <Money minor={r.amount_minor} direction={r.direction} className="font-semibold" />
      )}
    </li>
  );
}

const ROLE_LABEL: Record<ColumnRole, string> = {
  date: "Date",
  posting_date: "Value / posting date",
  description: "Description / narration",
  debit: "Money out (debit)",
  credit: "Money in (credit)",
  amount: "Amount",
  indicator: "DR/CR column",
  balance: "Balance",
  reference: "Reference",
};

function ColumnsCard({ b, defaultOpen, onSaved }: { b: ImportDetail; defaultOpen: boolean; onSaved: () => void }) {
  const [open, setOpen] = useState(defaultOpen);
  const init: Mapping = b.mapping ?? { header_row: null, columns: {} as Mapping["columns"], amount_mode: null, date_order: "DMY" };
  const [m, setM] = useState<Mapping>(init);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const headerRow = m.header_row ?? 0;
  const headers = useMemo(() => b.preview[headerRow] ?? [], [b.preview, headerRow]);
  const roles: ColumnRole[] = ["date", "description", ...(m.amount_mode === "debit_credit" ? (["debit", "credit"] as ColumnRole[]) : m.amount_mode === "indicator" ? (["amount", "indicator"] as ColumnRole[]) : (["amount"] as ColumnRole[])), "balance", "reference", "posting_date"];

  function setCol(role: ColumnRole, v: string) {
    setM((x) => ({ ...x, columns: { ...x.columns, [role]: v === "" ? null : Number(v) } }));
  }

  async function save() {
    setBusy(true);
    setError(null);
    const cols = { ...m.columns };
    if (m.amount_mode === "debit_credit") { cols.amount = null; cols.indicator = null; }
    if (m.amount_mode === "signed") { cols.debit = null; cols.credit = null; cols.indicator = null; }
    if (m.amount_mode === "indicator") { cols.debit = null; cols.credit = null; }
    try {
      await api(`/api/imports/${b.id}/mapping`, { method: "POST", body: { header_row: m.header_row ?? 0, columns: cols, amount_mode: m.amount_mode ?? "debit_credit", date_order: m.date_order } });
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? (e.fieldErrors[0]?.message ?? e.message) : "Could not apply.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-4 sm:p-5">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
        <span className="font-semibold">Columns</span>
        <span className="text-sm text-[var(--fg-subtle)]">
          {b.mapping?.from_profile ? "Using the settings you saved for this account" : b.mapping?.header_row != null ? "Detected automatically. Check if anything looks wrong." : "Couldn't detect the columns. Please choose them."}
        </span>
        <ChevronDown className={cn("ml-auto h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="mt-4 space-y-4">
          <div className="overflow-x-auto rounded-md border border-[var(--border)]">
            <table className="w-full text-left text-xs">
              <tbody>
                {b.preview.slice(0, 10).map((row, i) => (
                  <tr key={i} className={cn("border-b border-[var(--border)] last:border-0", i === headerRow && "bg-[var(--accent-bg)] font-semibold")}>
                    <td className="px-2 py-1 text-[var(--fg-subtle)]">{i + 1}</td>
                    {row.slice(0, 10).map((c, j) => <td key={j} className="max-w-[12rem] truncate px-2 py-1">{c}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <SelectField label="Heading row" value={String(headerRow)} onChange={(e) => setM((x) => ({ ...x, header_row: Number(e.target.value) }))}>
              {b.preview.slice(0, 15).map((row, i) => <option key={i} value={i}>Row {i + 1}: {row.filter(Boolean).slice(0, 3).join(", ").slice(0, 40)}</option>)}
            </SelectField>
            <SelectField label="How amounts are shown" value={m.amount_mode ?? ""} onChange={(e) => setM((x) => ({ ...x, amount_mode: e.target.value as Mapping["amount_mode"] }))}>
              <option value="" disabled>Choose…</option>
              <option value="debit_credit">Separate money in / money out columns</option>
              <option value="signed">One amount column (minus = money out)</option>
              <option value="indicator">Amount plus a DR/CR column</option>
            </SelectField>
            <SelectField label="Date format" value={m.date_order} onChange={(e) => setM((x) => ({ ...x, date_order: e.target.value as Mapping["date_order"] }))}>
              <option value="DMY">Day/Month/Year (24/10/2026)</option>
              <option value="MDY">Month/Day/Year (10/24/2026)</option>
              <option value="YMD">Year-Month-Day (2026-10-24)</option>
            </SelectField>
            {roles.map((role) => (
              <SelectField key={role} label={ROLE_LABEL[role]} value={m.columns?.[role] ?? ""} onChange={(e) => setCol(role, e.target.value)}>
                <option value="">— not in this file —</option>
                {headers.map((h, i) => <option key={i} value={i}>{h || `Column ${i + 1}`}</option>)}
              </SelectField>
            ))}
          </div>
          {error && <Alert>{error}</Alert>}
          <Button loading={busy} onClick={save}>Apply and re-check rows</Button>
          <p className="text-xs text-[var(--fg-subtle)]">Applying re-reads the file with these settings. Any row changes you made below are reset.</p>
        </div>
      )}
    </Card>
  );
}
