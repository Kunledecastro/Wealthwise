"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus } from "lucide-react";
import { AccountForm } from "@/components/account-form";
import { AppShell } from "@/components/app-shell";
import { BalanceStatusBadge, Money } from "@/components/money";
import { ReconcileForm } from "@/components/reconcile-form";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Sheet } from "@/components/ui/sheet";
import { ACCOUNT_TYPE_LABEL, api, ApiError, type Account } from "@/lib/api";
import { formatDate } from "@/lib/money";
import { useLoad } from "@/lib/use-load";

export default function AccountsPage() {
  return (
    <AppShell>
      <Accounts />
    </AppShell>
  );
}

function Accounts() {
  const [showArchived, setShowArchived] = useState(false);
  const { data, error, reload, loading } = useLoad<Account[]>(`/api/accounts?include_archived=${showArchived}`);
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const [checking, setChecking] = useState<Account | null>(null);
  const [flash, setFlash] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  async function act(a: Account, action: "archive" | "unarchive" | "delete") {
    setFlash(null);
    try {
      if (action === "delete") {
        if (!window.confirm(`Delete "${a.display_name}"? This cannot be undone.`)) return;
        await api(`/api/accounts/${a.id}`, { method: "DELETE" });
        setFlash({ kind: "success", msg: "Account deleted." });
      } else {
        await api(`/api/accounts/${a.id}`, { method: "PATCH", body: { is_archived: action === "archive" } });
        setFlash({ kind: "success", msg: action === "archive" ? "Account archived. Its history is kept." : "Account restored." });
      }
      reload();
    } catch (e) {
      setFlash({ kind: "error", msg: e instanceof ApiError ? e.message : "Something went wrong." });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Accounts</h1>
        <Button className="ml-auto" onClick={() => setEditing("new")}><Plus className="h-4 w-4" aria-hidden /> Add account</Button>
      </div>
      {flash && <Alert kind={flash.kind}>{flash.msg}</Alert>}
      {error && <Alert>{error}</Alert>}
      {loading && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}
      {data && data.length === 0 && (
        <Card>
          <h2 className="font-semibold">No accounts yet</h2>
          <p className="mt-1 text-sm text-[var(--fg-subtle)]">Add each bank account, wallet (e.g. OPay, Kuda) and cash you want to track, with its current balance.</p>
          <Button className="mt-4" onClick={() => setEditing("new")}>Add your first account</Button>
        </Card>
      )}
      <ul className="grid gap-4 sm:grid-cols-2">
        {data?.map((a) => (
          <li key={a.id}>
            <Card className={a.is_archived ? "opacity-70" : undefined}>
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0">
                  <h2 className="truncate font-semibold">{a.display_name}</h2>
                  <p className="text-sm text-[var(--fg-subtle)]">
                    {ACCOUNT_TYPE_LABEL[a.type]}
                    {a.institution_name && ` · ${a.institution_name}`}
                    {a.mask && ` · ••${a.mask}`}
                    {a.source === "imported" && " · Statements imported"}
                    {a.source === "simulated" && " · Simulated demo data"}
                    {a.is_archived && " · Archived"}
                  </p>
                </div>
                <span className="ml-auto"><BalanceStatusBadge balance={a.balance} currency={a.currency} /></span>
              </div>
              <p className="mt-4 text-2xl font-semibold"><Money minor={a.balance.posted_minor} currency={a.currency} /></p>
              {(a.balance.pending_in > 0 || a.balance.pending_out > 0) && (
                <p className="mt-1 text-sm text-[var(--fg-subtle)]">
                  Including pending: <Money minor={a.balance.available_incl_pending} currency={a.currency} />
                </p>
              )}
              <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                Started at <Money minor={a.opening_balance_minor} currency={a.currency} /> on {formatDate(a.opening_balance_date)} · {a.transaction_count} transaction{a.transaction_count === 1 ? "" : "s"}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href={`/transactions?account=${a.id}`} className="inline-flex min-h-8 items-center rounded-md px-3 text-xs font-medium text-[var(--accent)] hover:bg-[var(--muted)]">View transactions</Link>
                {!a.is_archived && <Link href={`/imports?account=${a.id}`} className="inline-flex min-h-8 items-center rounded-md px-3 text-xs font-medium text-[var(--accent)] hover:bg-[var(--muted)]">Import statement</Link>}
                <Button size="sm" variant="ghost" onClick={() => setChecking(a)}>Check against bank</Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(a)}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => act(a, a.is_archived ? "unarchive" : "archive")}>{a.is_archived ? "Unarchive" : "Archive"}</Button>
                {a.transaction_count === 0 && <Button size="sm" variant="ghost" onClick={() => act(a, "delete")}>Delete</Button>}
              </div>
            </Card>
          </li>
        ))}
      </ul>
      <label className="flex items-center gap-2 text-sm text-[var(--fg-subtle)]">
        <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} className="h-4 w-4 accent-[var(--accent)]" />
        Show archived accounts
      </label>
      <Sheet title="Check against your bank" open={checking !== null} onClose={() => setChecking(null)}>
        {checking && <ReconcileForm account={checking} onDone={reload} />}
      </Sheet>
      <Sheet title={editing === "new" ? "Add account" : "Edit account"} open={editing !== null} onClose={() => setEditing(null)}>
        {editing !== null && (
          <AccountForm
            existing={editing === "new" ? undefined : editing}
            onDone={(msg) => {
              setEditing(null);
              setFlash({ kind: "success", msg });
              reload();
            }}
          />
        )}
      </Sheet>
    </div>
  );
}
