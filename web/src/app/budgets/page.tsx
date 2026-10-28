"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ChevronLeft, ChevronRight, Pencil, Plus, Trash2, X } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { BudgetBar, BudgetStatus, LineFigures } from "@/components/budgets/budget-ui";
import { useCategories } from "@/components/category-ui";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, ApiError, type Budget, type BudgetLine, type BudgetPage, type BudgetSuggestions, type Category } from "@/lib/api";
import { formatMinor, minorToInput, parseMoneyToMinor } from "@/lib/money";
import { isIsoDate, monthEnd, monthName, monthStart, parseThresholds } from "@/lib/periods";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

export default function BudgetsPage() {
  return (
    <AppShell>
      <Suspense fallback={<p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}>
        <Budgets />
      </Suspense>
    </AppShell>
  );
}

const iconBtn = "inline-flex h-10 w-10 items-center justify-center rounded-md border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]";

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
}

function Budgets() {
  const params = useSearchParams();
  const router = useRouter();
  const m = params.get("month");
  const monthParam = m && isIsoDate(`${m}-01`) ? `${m}-01` : null;
  const page = useLoad<BudgetPage>(`/api/budgets${monthParam ? `?month=${monthParam}` : ""}`);
  const [data, setData] = useState<BudgetPage | null>(null);
  const [editing, setEditing] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const current = data && data.month === (monthParam ?? page.data?.month) ? data : page.data;

  function go(offset: number) {
    if (!current) return;
    setEditing(false);
    setFlash(null);
    setData(null);
    router.replace(`/budgets?month=${monthStart(current.month, offset).slice(0, 7)}`, { scroll: false });
  }
  function update(p: BudgetPage, msg?: string) {
    setData(p);
    setFlash(msg ?? null);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Budgets</h1>
        {current && (
          <div className="ml-auto flex items-center gap-2">
            <button type="button" onClick={() => go(-1)} className={iconBtn} aria-label="Previous month"><ChevronLeft className="h-4 w-4" aria-hidden /></button>
            <p className="min-w-36 text-center font-medium" aria-live="polite">{monthName(current.month)}</p>
            <button type="button" onClick={() => go(1)} className={iconBtn} aria-label="Next month"><ChevronRight className="h-4 w-4" aria-hidden /></button>
          </div>
        )}
      </div>
      {flash && <Alert kind="success">{flash}</Alert>}
      {page.error && <Alert>{page.error}</Alert>}
      {!current && !page.error && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}
      {current && !current.budget && <CreateBudget page={current} onCreated={(p) => { update(p, `Budget for ${monthName(p.month)} created.`); setEditing(true); }} />}
      {current?.budget && (
        editing
          ? <EditLines page={current} budget={current.budget} onCancel={() => setEditing(false)} onSaved={(p) => { update(p, "Budget saved."); setEditing(false); }} />
          : <BudgetView page={current} budget={current.budget} onEdit={() => setEditing(true)} onChange={update} onDeleted={() => { setData({ ...current, budget: null }); setFlash("Budget deleted."); }} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- create

function CreateBudget({ page, onCreated }: { page: BudgetPage; onCreated: (p: BudgetPage) => void }) {
  const sugg = useLoad<BudgetSuggestions>(`/api/budgets/suggestions?month=${page.month}`);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const prevName = monthName(monthStart(page.month, -1), { year: false });

  async function create(start: "blank" | "copy_previous" | "suggested") {
    setBusy(start);
    setError(null);
    try {
      onCreated(await api<BudgetPage>("/api/budgets", { method: "POST", body: { month: page.month, start } }));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(null);
    }
  }

  const s = sugg.data;
  return (
    <Card>
      <h2 className="font-semibold">No budget for {monthName(page.month)} yet</h2>
      <p className="mt-1 text-sm text-[var(--fg-subtle)]">
        Choose how much you plan to spend in each category. Wealthwise then tracks your spending against it and warns you at {page.default_thresholds.join("%, ")}% (change these in Settings).
      </p>
      {error && <div className="mt-4"><Alert>{error}</Alert></div>}

      {s && s.suggestions.length > 0 && (
        <div className="mt-5 rounded-lg border border-[var(--border)]">
          <div className="border-b border-[var(--border)] px-4 py-3">
            <h3 className="text-sm font-semibold">Suggested from your spending</h3>
            <p className="text-xs text-[var(--fg-subtle)]">
              Average of {s.based_on.map((d) => monthName(d, { short: true, year: false })).join(", ")}, rounded up to the nearest ₦1,000. Only categories with spending in at least 2 of those months.
            </p>
          </div>
          <ul className="divide-y divide-[var(--border)] text-sm">
            {s.suggestions.map((x) => (
              <li key={x.category_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: x.color }} aria-hidden />
                <span className="flex-1">{x.name}</span>
                <span className="text-xs text-[var(--fg-subtle)] tabular">{x.months.map((mm) => formatMinor(mm.net_spending)).join(" · ")}</span>
                <span className="w-28 text-right font-medium tabular">{formatMinor(x.amount_minor)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {s && s.suggestions.length === 0 && (
        <p className="mt-4 text-sm text-[var(--fg-subtle)]">No suggestions yet: they need at least two of the last three complete months of categorised spending.</p>
      )}

      <div className="mt-5 flex flex-wrap gap-2">
        {s && s.suggestions.length > 0 && <Button loading={busy === "suggested"} disabled={!!busy} onClick={() => create("suggested")}>Use these suggestions</Button>}
        {page.previous_month_has_budget && (
          <Button variant="secondary" loading={busy === "copy_previous"} disabled={!!busy} onClick={() => create("copy_previous")}>Copy {prevName}&apos;s budget</Button>
        )}
        <Button variant="secondary" loading={busy === "blank"} disabled={!!busy} onClick={() => create("blank")}>Start blank</Button>
      </div>
      <p className="mt-3 text-xs text-[var(--fg-subtle)]">You can change every amount before anything is tracked.</p>
    </Card>
  );
}

// ---------------------------------------------------------------- view

function BudgetView({ page, budget, onEdit, onChange, onDeleted }: { page: BudgetPage; budget: Budget; onEdit: () => void; onChange: (p: BudgetPage, msg?: string) => void; onDeleted: () => void }) {
  const end = `${Number(monthEnd(page.month).slice(8))} ${monthName(page.month, { short: true, year: false })}`;
  const q = `from=${page.month}&to=${monthEnd(page.month)}&status=posted`;
  const empty = budget.lines.length === 0 && !budget.overall;

  return (
    <>
      {empty ? (
        <Card>
          <h2 className="font-semibold">This budget has no lines yet</h2>
          <p className="mt-1 text-sm text-[var(--fg-subtle)]">Add the categories you want to plan for, and an optional overall limit.</p>
          <Button className="mt-4" onClick={onEdit}><Plus className="h-4 w-4" aria-hidden /> Add categories</Button>
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Card className="p-4 sm:p-5">
              <p className="text-sm text-[var(--fg-subtle)]">Budgeted</p>
              <p className="mt-1 text-xl font-semibold tabular">{formatMinor(budget.total_planned)}</p>
              <p className="text-xs text-[var(--fg-subtle)]">{budget.lines.length} categor{budget.lines.length === 1 ? "y" : "ies"}</p>
            </Card>
            <Card className="p-4 sm:p-5">
              <p className="text-sm text-[var(--fg-subtle)]">Spent in those categories</p>
              <p className="mt-1 text-xl font-semibold tabular">{formatMinor(budget.budgeted_spending)}</p>
              <p className="text-xs text-[var(--fg-subtle)]">{budget.attention_count ? `${budget.attention_count} need${budget.attention_count === 1 ? "s" : ""} attention` : "Nothing needs attention"}</p>
            </Card>
            <Card className="p-4 sm:p-5">
              <p className="text-sm text-[var(--fg-subtle)]">Not in the budget</p>
              <p className="mt-1 text-xl font-semibold tabular">{formatMinor(budget.unbudgeted_spending)}</p>
              <p className="text-xs text-[var(--fg-subtle)]">of {formatMinor(budget.total_spending)} total spending</p>
            </Card>
          </div>

          {budget.overall && (
            <Card>
              <LineCard line={budget.overall} thresholds={budget.alert_thresholds} monthEnd={end} />
              <p className="mt-2 text-xs text-[var(--fg-subtle)]">Counts all spending this month, including categories without a budget and uncategorised spending.</p>
            </Card>
          )}

          {budget.lines.length > 0 && (
            <Card className="p-0 sm:p-0">
              <ul className="divide-y divide-[var(--border)]">
                {budget.lines.map((l) => (
                  <li key={l.id} className="p-4 sm:p-5">
                    <LineCard line={l} thresholds={budget.alert_thresholds} monthEnd={end} href={`/transactions?category=${l.category_id}&${q}`} />
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}

      {budget.unbudgeted.length > 0 && (
        <Card>
          <h2 className="font-semibold">Spending not in the budget</h2>
          <p className="mt-1 text-sm text-[var(--fg-subtle)]">Still counted in your totals. Add a category to the budget to track it.</p>
          <ul className="mt-3 divide-y divide-[var(--border)] text-sm">
            {budget.unbudgeted.map((u) => (
              <li key={u.category_id ?? "none"}>
                <Link href={`/transactions?category=${u.category_id ?? "none"}&${q}`} className="flex items-center gap-2 py-2 hover:underline">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: u.color }} aria-hidden />
                  <span className="flex-1">{u.name}</span>
                  <span className="tabular">{formatMinor(u.net_spending)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        {!empty && <Button onClick={onEdit}><Pencil className="h-4 w-4" aria-hidden /> Edit amounts</Button>}
      </div>

      <BudgetSettings page={page} budget={budget} onChange={onChange} onDeleted={onDeleted} />
      <p className="text-xs text-[var(--fg-subtle)]">
        Spent = posted spending in the category this month, after refunds. Transfers between your own accounts are never counted. Estimates assume you keep spending at the same pace and appear from day 7.
      </p>
    </>
  );
}

function LineCard({ line, thresholds, monthEnd, href }: { line: BudgetLine; thresholds: number[]; monthEnd: string; href?: string }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {line.category_id && <span className="h-2.5 w-2.5 rounded-full" style={{ background: line.color }} aria-hidden />}
        {href ? <Link href={href} className="font-medium hover:underline">{line.name}</Link> : <span className="font-medium">{line.name}</span>}
        {line.archived && <span className="text-xs text-[var(--fg-subtle)]">(archived)</span>}
        <span className="ml-auto"><BudgetStatus line={line} /></span>
      </div>
      <BudgetBar line={line} thresholds={thresholds} />
      <LineFigures line={line} monthEnd={monthEnd} />
    </div>
  );
}

function BudgetSettings({ page, budget, onChange, onDeleted }: { page: BudgetPage; budget: Budget; onChange: (p: BudgetPage, msg?: string) => void; onDeleted: () => void }) {
  const [thresholds, setThresholds] = useState(budget.thresholds_overridden ? budget.alert_thresholds.join(", ") : "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function patch(body: Record<string, unknown>, msg: string) {
    setBusy(true);
    setError(null);
    try {
      onChange(await api<BudgetPage>(`/api/budgets/${budget.id}`, { method: "PATCH", body }), msg);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }
  async function saveThresholds() {
    if (!thresholds.trim()) return patch({ alert_thresholds: null }, "Alerts now follow your Settings.");
    const parsed = parseThresholds(thresholds);
    if (!parsed) return setError("Enter 1 to 5 whole percentages between 1 and 200, e.g. 80, 100.");
    return patch({ alert_thresholds: parsed }, "Alert levels saved for this budget.");
  }
  async function remove() {
    setBusy(true);
    try {
      await api(`/api/budgets/${budget.id}`, { method: "DELETE" });
      onDeleted();
    } catch (e) {
      setError(errMsg(e));
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2 className="font-semibold">Budget settings</h2>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      <div className="mt-4 space-y-5">
        <label className="flex items-start gap-3">
          <input type="checkbox" className="mt-1 h-4 w-4" checked={budget.rollover_enabled} disabled={busy} onChange={(e) => patch({ rollover_enabled: e.target.checked }, e.target.checked ? "Carry-over switched on." : "Carry-over switched off.")} />
          <span>
            <span className="block text-sm font-medium">Carry over unspent money from {monthName(monthStart(page.month, -1), { year: false })}</span>
            <span className="block text-sm text-[var(--fg-subtle)]">Needs a budget last month. Only money you didn&apos;t spend moves forward; overspending is never carried.</span>
          </span>
        </label>
        <div>
          <label htmlFor="thr" className="block text-sm font-medium">Alert levels for this month</label>
          <div className="mt-1.5 flex flex-wrap gap-2">
            <input id="thr" value={thresholds} onChange={(e) => setThresholds(e.target.value)} placeholder={`${page.default_thresholds.join(", ")} (from Settings)`} className="min-h-10 w-64 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-sm" />
            <Button variant="secondary" onClick={saveThresholds} disabled={busy}>Save</Button>
          </div>
          <p className="mt-1 text-xs text-[var(--fg-subtle)]">Percentages of each line, e.g. 80, 100. Leave blank to use your Settings.</p>
        </div>
        <div className="border-t border-[var(--border)] pt-4">
          {confirmDelete ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm">Delete the {monthName(page.month)} budget? Your transactions are not affected.</p>
              <Button variant="danger" size="sm" loading={busy} onClick={remove}>Delete budget</Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            </div>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)} className="text-[var(--danger)]"><Trash2 className="h-4 w-4" aria-hidden /> Delete this budget</Button>
          )}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- edit

type Row = { key: string; categoryId: string; amount: string };

function EditLines({ page, budget, onCancel, onSaved }: { page: BudgetPage; budget: Budget; onCancel: () => void; onSaved: (p: BudgetPage) => void }) {
  const categories = useCategories();
  const [rows, setRows] = useState<Row[]>(() => budget.lines.map((l) => ({ key: l.id, categoryId: l.category_id!, amount: minorToInput(l.planned_minor) })));
  const [overall, setOverall] = useState(budget.overall ? minorToInput(budget.overall.planned_minor) : "");
  const [adding, setAdding] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const expense = (categories.data ?? []).filter((c: Category) => c.kind === "expense");
  const byId = new Map(expense.map((c) => [c.id, c]));
  const used = new Set(rows.map((r) => r.categoryId));
  const available = expense.filter((c) => !c.is_archived && !used.has(c.id));
  const spentById = new Map([...budget.lines.map((l) => [l.category_id, l.spent_minor] as const), ...budget.unbudgeted.map((u) => [u.category_id, u.net_spending] as const)]);

  function addRow(id: string) {
    if (!id) return;
    setRows((r) => [...r, { key: `new-${id}`, categoryId: id, amount: "" }]);
    setAdding("");
  }

  async function save() {
    const errs: Record<string, string> = {};
    const lines: { category_id: string | null; planned_minor: number }[] = [];
    for (const r of rows) {
      const v = parseMoneyToMinor(r.amount);
      if (v === null) errs[r.key] = "Enter an amount above ₦0";
      else lines.push({ category_id: r.categoryId, planned_minor: v });
    }
    if (overall.trim()) {
      const v = parseMoneyToMinor(overall);
      if (v === null) errs.overall = "Enter an amount above ₦0, or leave blank";
      else lines.push({ category_id: null, planned_minor: v });
    }
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError(null);
    try {
      onSaved(await api<BudgetPage>(`/api/budgets/${budget.id}/lines`, { method: "PUT", body: { lines } }));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  const total = rows.reduce((sum, r) => sum + (parseMoneyToMinor(r.amount) ?? 0), 0);

  return (
    <Card>
      <h2 className="font-semibold">Edit {monthName(page.month)} budget</h2>
      <p className="mt-1 text-sm text-[var(--fg-subtle)]">Monthly amounts in naira. The figure under each category is what you have spent so far this month.</p>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      <ul className="mt-4 divide-y divide-[var(--border)]">
        {rows.map((r) => {
          const c = byId.get(r.categoryId);
          return (
            <li key={r.key} className="flex flex-wrap items-start gap-3 py-3">
              <div className="min-w-40 flex-1">
                <p className="flex items-center gap-2 font-medium">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: c?.color ?? "#94a3b8" }} aria-hidden />
                  {c?.name ?? "…"}
                  {c?.is_archived && <span className="text-xs font-normal text-[var(--fg-subtle)]">(archived)</span>}
                </p>
                <p className="text-xs text-[var(--fg-subtle)]">Spent so far: {formatMinor(spentById.get(r.categoryId) ?? 0)}</p>
              </div>
              <div className="w-40">
                <label className="sr-only" htmlFor={`amt-${r.key}`}>Budget for {c?.name}</label>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-[var(--fg-subtle)]">₦</span>
                  <input
                    id={`amt-${r.key}`}
                    inputMode="decimal"
                    value={r.amount}
                    onChange={(e) => setRows((rs) => rs.map((x) => (x.key === r.key ? { ...x, amount: e.target.value } : x)))}
                    aria-invalid={errors[r.key] ? true : undefined}
                    className={cn("min-h-10 w-full rounded-md border bg-[var(--surface)] pl-7 pr-3 text-right text-base tabular sm:text-sm", errors[r.key] ? "border-[var(--danger)]" : "border-[var(--border)]")}
                  />
                </div>
                {errors[r.key] && <p className="mt-1 text-xs text-[var(--danger)]">{errors[r.key]}</p>}
              </div>
              <button type="button" onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))} className={iconBtn} aria-label={`Remove ${c?.name ?? "line"}`}>
                <X className="h-4 w-4" aria-hidden />
              </button>
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-sm">
          <span className="block font-medium">Add a category</span>
          <select value={adding} onChange={(e) => addRow(e.target.value)} className="mt-1.5 min-h-10 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-sm">
            <option value="">Choose…</option>
            {available.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <p className="ml-auto text-sm">Total budgeted: <span className="font-semibold tabular">{formatMinor(total)}</span></p>
      </div>

      <div className="mt-6 border-t border-[var(--border)] pt-4">
        <label htmlFor="overall" className="block text-sm font-medium">Overall spending limit (optional)</label>
        <p className="text-xs text-[var(--fg-subtle)]">Covers all spending this month, including categories without a line. So far: {formatMinor(budget.total_spending)}.</p>
        <div className="relative mt-1.5 w-48">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-[var(--fg-subtle)]">₦</span>
          <input id="overall" inputMode="decimal" value={overall} onChange={(e) => setOverall(e.target.value)} className={cn("min-h-10 w-full rounded-md border bg-[var(--surface)] pl-7 pr-3 text-right text-base tabular sm:text-sm", errors.overall ? "border-[var(--danger)]" : "border-[var(--border)]")} />
        </div>
        {errors.overall && <p className="mt-1 text-xs text-[var(--danger)]">{errors.overall}</p>}
      </div>

      <div className="mt-6 flex gap-2">
        <Button onClick={save} loading={busy}>Save budget</Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </Card>
  );
}
