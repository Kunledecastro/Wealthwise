"use client";

import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { Money } from "@/components/money";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { SelectField } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import { api, ApiError, type ByCategory, type Category, type CategoryRule } from "@/lib/api";
import { formatDate, todayIn } from "@/lib/money";
import { useLoad } from "@/lib/use-load";

export default function CategoriesPage() {
  return (
    <AppShell>
      <Categories />
    </AppShell>
  );
}

function monthRange(today: string, offset: number): [string, string] {
  const [y, m] = today.split("-").map(Number);
  const d = new Date(Date.UTC(y!, (m! - 1) + offset, 1));
  const end = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
  return [d.toISOString().slice(0, 10), end.toISOString().slice(0, 10)];
}

function Categories() {
  const { me } = useAuth();
  const today = todayIn(me?.preferences.timezone ?? "Africa/Lagos");
  const [offset, setOffset] = useState(0);
  const [from, to] = monthRange(today, offset);
  const spend = useLoad<ByCategory>(`/api/ledger/by-category?date_from=${from}&date_to=${to}`);
  const [showArchived, setShowArchived] = useState(false);
  const cats = useLoad<Category[]>(`/api/categories?include_archived=${showArchived}`);
  const rules = useLoad<CategoryRule[]>("/api/categories/rules");
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [flash, setFlash] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const reloadAll = () => { cats.reload(); rules.reload(); spend.reload(); };
  const spending = (spend.data?.rows ?? []).filter((r) => r.net_spending !== 0);
  const income = (spend.data?.rows ?? []).filter((r) => r.income > 0);
  const maxSpend = Math.max(1, ...spending.map((r) => Math.abs(r.net_spending)));
  const totalSpend = spending.reduce((a, r) => a + r.net_spending, 0);

  async function deleteRule(r: CategoryRule) {
    if (!window.confirm(`Delete the rule "${r.pattern}" → ${r.category_name}? Transactions keep their current category.`)) return;
    try {
      await api(`/api/categories/rules/${r.id}`, { method: "DELETE" });
      setFlash({ kind: "success", msg: "Rule deleted. Use “Re-run my rules” on the To review page to recategorise." });
      rules.reload();
    } catch (e) {
      setFlash({ kind: "error", msg: e instanceof ApiError ? e.message : "Could not delete." });
    }
  }

  async function toggleRule(r: CategoryRule) {
    await api(`/api/categories/rules/${r.id}`, { method: "PATCH", body: { is_active: !r.is_active } });
    rules.reload();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Categories</h1>
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" onClick={() => setRuleOpen(true)}><Plus className="h-4 w-4" aria-hidden /> Add rule</Button>
          <Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" aria-hidden /> Add category</Button>
        </div>
      </div>
      {flash && <Alert kind={flash.kind}>{flash.msg}</Alert>}

      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <h2 className="font-semibold">Spending by category</h2>
          <span className="text-sm text-[var(--fg-subtle)]">{formatDate(from)} – {formatDate(to)}</span>
          <div className="ml-auto flex gap-1">
            <Button size="sm" variant="secondary" onClick={() => setOffset((o) => o - 1)} aria-label="Previous month">←</Button>
            <Button size="sm" variant="secondary" disabled={offset >= 0} onClick={() => setOffset((o) => o + 1)} aria-label="Next month">→</Button>
          </div>
        </div>
        {spend.loading && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}
        {spend.data && spending.length === 0 && <p className="text-sm text-[var(--fg-subtle)]">No spending recorded for this month.</p>}
        {spending.length > 0 && (
          <ul className="space-y-2">
            {spending.map((r) => (
              <li key={r.category_id ?? "none"}>
                <Link href={`/transactions?category=${r.category_id ?? "none"}`} className="block rounded-md p-1 hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
                  <div className="flex items-center gap-2 text-sm">
                    <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: r.color }} />
                    <span className="min-w-0 flex-1 truncate">{r.name}</span>
                    <span className="text-xs text-[var(--fg-subtle)]">{Math.round((r.net_spending / (totalSpend || 1)) * 100)}%</span>
                    <Money minor={r.net_spending} className="font-medium" />
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--muted)]" aria-hidden>
                    <div className="h-full rounded-full" style={{ width: `${Math.max(2, (Math.abs(r.net_spending) / maxSpend) * 100)}%`, background: r.color }} />
                  </div>
                </Link>
              </li>
            ))}
            <li className="flex justify-between border-t border-[var(--border)] pt-2 text-sm font-semibold">
              <span>Total spending</span><Money minor={totalSpend} />
            </li>
          </ul>
        )}
        {income.length > 0 && (
          <p className="mt-4 text-sm text-[var(--fg-subtle)]">
            Income: {income.map((r) => `${r.name} `).join("· ")}
          </p>
        )}
        <p className="mt-3 text-xs text-[var(--fg-subtle)]">Refunds reduce their own category. Transfers between your accounts are never counted.</p>
      </Card>

      <Card>
        <CardHeader title="Your categories" description="Rename, recolour, archive or merge. Bank fees and Transfers are filled in automatically." />
        {cats.data && (["expense", "income", "transfer"] as const).map((kind) => {
          const list = cats.data!.filter((c) => c.kind === kind);
          if (!list.length) return null;
          return (
            <div key={kind} className="mb-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">{kind === "expense" ? "Spending" : kind === "income" ? "Income" : "Automatic"}</h3>
              <ul className="divide-y divide-[var(--border)]">
                {list.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                    <span aria-hidden className="h-3 w-3 rounded-full" style={{ background: c.color }} />
                    <span className={c.is_archived ? "text-[var(--fg-subtle)] line-through" : "font-medium"}>{c.name}</span>
                    <span className="text-xs text-[var(--fg-subtle)]">{c.transaction_count} transaction{c.transaction_count === 1 ? "" : "s"}{c.rule_count ? ` · ${c.rule_count} rule${c.rule_count === 1 ? "" : "s"}` : ""}</span>
                    <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setEditing(c)}>Edit</Button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        <label className="flex items-center gap-2 text-sm text-[var(--fg-subtle)]">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
          Show archived categories
        </label>
      </Card>

      <Card>
        <CardHeader title="Your rules" description="Checked before built-in recognition. Most specific first: exact merchant, then 'starts with', then 'contains'." />
        {rules.data && rules.data.length === 0 && <p className="text-sm text-[var(--fg-subtle)]">No rules yet. When you change a transaction&apos;s category, Wealthwise offers to create one.</p>}
        {rules.data && rules.data.length > 0 && (
          <ul className="divide-y divide-[var(--border)]">
            {rules.data.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className={r.is_active ? "" : "text-[var(--fg-subtle)] line-through"}>
                  {r.match_type === "contains" ? "Contains" : r.match_type === "starts_with" ? "Merchant starts with" : "Merchant is"} <code className="rounded bg-[var(--muted)] px-1">{r.pattern}</code> → <strong>{r.category_name}</strong>
                  {r.account_name && ` (only ${r.account_name})`}
                </span>
                <span className="text-xs text-[var(--fg-subtle)]">used {r.hit_count}×{r.created_from === "user_correction" ? " · learned from you" : ""}</span>
                <span className="ml-auto flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => toggleRule(r)}>{r.is_active ? "Pause" : "Resume"}</Button>
                  <Button size="sm" variant="ghost" onClick={() => deleteRule(r)} aria-label={`Delete rule ${r.pattern}`}><Trash2 className="h-4 w-4" aria-hidden /></Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Sheet title={editing === "new" ? "Add category" : "Edit category"} open={editing !== null} onClose={() => setEditing(null)}>
        {editing !== null && cats.data && (
          <CategoryForm existing={editing === "new" ? undefined : editing} all={cats.data} onDone={(msg) => { setEditing(null); setFlash({ kind: "success", msg }); reloadAll(); }} />
        )}
      </Sheet>
      <Sheet title="Add rule" open={ruleOpen} onClose={() => setRuleOpen(false)}>
        {ruleOpen && cats.data && <RuleForm categories={cats.data} onDone={(msg) => { setRuleOpen(false); setFlash({ kind: "success", msg }); reloadAll(); }} />}
      </Sheet>
    </div>
  );
}

const SWATCHES = ["#2f8f68", "#e07a3f", "#3b82c4", "#7c5cc4", "#c49a1b", "#1aa3a3", "#d0527a", "#9b4dca", "#d94848", "#4a6fd8", "#b5651d", "#5aa04a", "#6b7280"];

function CategoryForm({ existing, all, onDone }: { existing?: Category; all: Category[]; onDone: (msg: string) => void }) {
  const [name, setName] = useState(existing?.name ?? "");
  const [kind, setKind] = useState<"expense" | "income">(existing?.kind === "income" ? "income" : "expense");
  const [color, setColor] = useState(existing?.color ?? SWATCHES[0]!);
  const [mergeInto, setMergeInto] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mergeTargets = useMemo(() => all.filter((c) => existing && c.id !== existing.id && c.kind === existing.kind && !c.is_archived), [all, existing]);

  async function run(fn: () => Promise<string>) {
    setBusy(true);
    setError(null);
    try {
      onDone(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? (e.fieldErrors[0]?.message ?? e.message) : "Something went wrong.");
      setBusy(false);
    }
  }

  function save(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Give the category a name.");
    run(async () => {
      if (existing) {
        await api(`/api/categories/${existing.id}`, { method: "PATCH", body: { name, color } });
        return "Category updated.";
      }
      await api("/api/categories", { method: "POST", body: { name, kind, color } });
      return "Category added.";
    });
  }

  return (
    <div className="space-y-5">
      <form onSubmit={save} className="space-y-4" noValidate>
        <Field label="Name" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
        {!existing && (
          <SelectField label="Type" value={kind} onChange={(e) => setKind(e.target.value as "expense" | "income")}>
            <option value="expense">Spending</option>
            <option value="income">Income</option>
          </SelectField>
        )}
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Colour</legend>
          <div className="flex flex-wrap gap-2">
            {SWATCHES.map((c) => (
              <button type="button" key={c} onClick={() => setColor(c)} aria-label={`Colour ${c}`} aria-pressed={color === c}
                className={`h-8 w-8 rounded-full ring-offset-2 ring-offset-[var(--surface)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] ${color === c ? "ring-2 ring-[var(--fg)]" : ""}`} style={{ background: c }} />
            ))}
          </div>
        </fieldset>
        {error && <Alert>{error}</Alert>}
        <Button type="submit" size="full" loading={busy}>{existing ? "Save" : "Add category"}</Button>
      </form>

      {existing && !existing.locked && (
        <div className="space-y-3 border-t border-[var(--border)] pt-4">
          <Button variant="secondary" size="full" disabled={busy}
            onClick={() => run(async () => { await api(`/api/categories/${existing.id}`, { method: "PATCH", body: { is_archived: !existing.is_archived } }); return existing.is_archived ? "Category restored." : "Category archived. Its transactions keep it; it won't be suggested any more."; })}>
            {existing.is_archived ? "Unarchive" : "Archive"}
          </Button>
          {mergeTargets.length > 0 && (
            <div className="flex items-end gap-2">
              <SelectField label={`Merge into another category (moves ${existing.transaction_count} transaction${existing.transaction_count === 1 ? "" : "s"} and ${existing.rule_count} rule${existing.rule_count === 1 ? "" : "s"})`} value={mergeInto} onChange={(e) => setMergeInto(e.target.value)} className="flex-1">
                <option value="">Choose…</option>
                {mergeTargets.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </SelectField>
              <Button variant="secondary" disabled={!mergeInto || busy}
                onClick={() => { if (window.confirm(`Merge "${existing.name}" into the selected category? This can't be undone.`)) run(async () => { await api(`/api/categories/${existing.id}/merge`, { method: "POST", body: { into_id: mergeInto } }); return "Categories merged."; }); }}>
                Merge
              </Button>
            </div>
          )}
          {existing.transaction_count === 0 && (
            <Button variant="ghost" size="full" className="text-[var(--danger)]" disabled={busy}
              onClick={() => { if (window.confirm(`Delete "${existing.name}"?`)) run(async () => { await api(`/api/categories/${existing.id}`, { method: "DELETE" }); return "Category deleted."; }); }}>
              Delete category
            </Button>
          )}
        </div>
      )}
      {existing?.locked && <p className="text-sm text-[var(--fg-subtle)]">This category is filled in automatically, so it can be renamed but not archived or deleted.</p>}
    </div>
  );
}

function RuleForm({ categories, onDone }: { categories: Category[]; onDone: (msg: string) => void }) {
  const usable = categories.filter((c) => c.kind !== "transfer" && !c.is_archived);
  const [pattern, setPattern] = useState("");
  const [matchType, setMatchType] = useState<"contains" | "starts_with" | "equals">("contains");
  const [categoryId, setCategoryId] = useState(usable[0]?.id ?? "");
  const [applyExisting, setApplyExisting] = useState(true);
  const [preview, setPreview] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function check() {
    setError(null);
    try {
      const r = await api<{ updated: number }>("/api/categories/rules/preview", { method: "POST", body: { category_id: categoryId, pattern, match_type: matchType } });
      setPreview(r.updated);
    } catch (e) {
      setError(e instanceof ApiError ? (e.fieldErrors[0]?.message ?? e.message) : "Could not check.");
    }
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ applied_to: number }>("/api/categories/rules", { method: "POST", body: { category_id: categoryId, pattern, match_type: matchType, apply_to_existing: applyExisting } });
      onDone(`Rule added${r.applied_to ? `; ${r.applied_to} transaction${r.applied_to === 1 ? "" : "s"} updated` : ""}.`);
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors[0]?.message ?? err.message) : "Could not save.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4" noValidate>
      <SelectField label="When" value={matchType} onChange={(e) => { setMatchType(e.target.value as typeof matchType); setPreview(null); }}>
        <option value="contains">the description or merchant contains</option>
        <option value="starts_with">the merchant name starts with</option>
        <option value="equals">the merchant name is exactly</option>
      </SelectField>
      <Field label="Text" placeholder="e.g. MAMA PUT" value={pattern} maxLength={100} onChange={(e) => { setPattern(e.target.value); setPreview(null); }} hint="Not case-sensitive." />
      <SelectField label="Put it in" value={categoryId} onChange={(e) => { setCategoryId(e.target.value); setPreview(null); }}>
        {usable.map((c) => <option key={c.id} value={c.id}>{c.name}{c.kind === "income" ? " (income)" : ""}</option>)}
      </SelectField>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={applyExisting} onChange={(e) => setApplyExisting(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
        Also apply to existing transactions (never ones you categorised yourself)
      </label>
      <div className="flex items-center gap-2 text-sm">
        <Button type="button" size="sm" variant="secondary" disabled={pattern.trim().length < 2} onClick={check}>Check matches</Button>
        {preview !== null && <span>{preview} existing transaction{preview === 1 ? "" : "s"} would change.</span>}
      </div>
      {error && <Alert>{error}</Alert>}
      <Button type="submit" size="full" loading={busy} disabled={pattern.trim().length < 2}>Add rule</Button>
    </form>
  );
}
