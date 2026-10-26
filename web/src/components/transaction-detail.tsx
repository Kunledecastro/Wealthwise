"use client";

import { useState } from "react";
import { Money } from "./money";
import { TransactionForm } from "./transaction-form";
import { Alert } from "./ui/alert";
import { Button } from "./ui/button";
import { Field } from "./ui/field";
import { api, ApiError, KIND_LABEL, type Account, type TransactionDetail as Detail } from "@/lib/api";
import { formatDate, formatMinor } from "@/lib/money";
import { useLoad } from "@/lib/use-load";

const FIELD_LABEL: Record<string, string> = {
  amount_minor: "Amount",
  account_id: "Account",
  kind: "Type",
  direction: "Direction",
  status: "Status",
  transaction_date: "Date",
  posting_date: "Posting date",
  merchant: "Merchant",
  narration: "Description",
  notes: "Notes",
};
const ACTION_LABEL: Record<string, string> = { create: "Created", update: "Edited", delete: "Deleted", reverse: "Reversed" };

function show(field: string, v: unknown, accounts: Account[], currency: string): string {
  if (v === null || v === undefined || v === "") return "—";
  if (field === "amount_minor" && typeof v === "number") return formatMinor(v, currency);
  if (field === "account_id") return accounts.find((a) => a.id === v)?.display_name ?? "another account";
  if (field === "status") return ({ posted: "Completed", pending: "Pending", failed: "Failed", reversed: "Reversed" } as Record<string, string>)[String(v)] ?? String(v);
  return String(v);
}

type Props = {
  id: string;
  accounts: Account[];
  onChanged: (message: string, close: boolean) => void;
  onOpenOther: (id: string) => void;
};

export function TransactionDetail({ id, accounts, onChanged, onOpenOther }: Props) {
  const { data: t, error, reload } = useLoad<Detail>(`/api/transactions/${id}`);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState<"delete" | "reverse" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (error) return <Alert>{error}</Alert>;
  if (!t) return <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>;

  if (editing) {
    return (
      <div className="space-y-3">
        <TransactionForm accounts={accounts} existing={t} onDone={(msg) => { setEditing(false); reload(); onChanged(msg, false); }} />
        <Button variant="ghost" size="full" onClick={() => setEditing(false)}>Cancel</Button>
      </div>
    );
  }

  async function run(action: "delete" | "reverse" | "post" | "fail") {
    setBusy(true);
    setActionError(null);
    try {
      if (action === "delete") {
        await api(`/api/transactions/${t!.id}/delete`, { method: "POST", body: { reason: reason || null } });
        onChanged(t!.kind === "transfer" ? "Transfer deleted (both sides)." : "Transaction deleted.", true);
        return;
      }
      if (action === "reverse") {
        await api(`/api/transactions/${t!.id}/reverse`, { method: "POST", body: { reason: reason || null } });
        onChanged("Reversal recorded. The original and the reversal now cancel out.", false);
      } else {
        await api(`/api/transactions/${t!.id}`, { method: "PATCH", body: { status: action === "post" ? "posted" : "failed" } });
        onChanged(action === "post" ? "Marked as completed." : "Marked as failed. It no longer counts.", false);
      }
      setConfirm(null);
      setReason("");
      reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const locked = t.kind === "reversal" || t.status === "reversed";
  const canReverse = t.status === "posted" && !["transfer", "reversal"].includes(t.kind);

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm text-[var(--fg-subtle)]">{KIND_LABEL[t.kind]}</p>
        <p className="text-3xl font-semibold"><Money minor={t.amount_minor} currency={t.currency} direction={t.direction} /></p>
        <p className="mt-1 font-medium">{t.merchant || t.narration || (t.kind === "transfer" ? `${t.direction === "debit" ? "To" : "From"} ${t.counterpart_account_name}` : "")}</p>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-[var(--fg-subtle)]">Status</dt>
        <dd>{show("status", t.status, accounts, t.currency)}</dd>
        <dt className="text-[var(--fg-subtle)]">Date</dt>
        <dd>{formatDate(t.transaction_date)}{t.posting_date && t.posting_date !== t.transaction_date && ` (posted ${formatDate(t.posting_date)})`}</dd>
        <dt className="text-[var(--fg-subtle)]">Account</dt>
        <dd>{t.account_name}</dd>
        {t.kind === "transfer" && (<><dt className="text-[var(--fg-subtle)]">{t.direction === "debit" ? "To" : "From"}</dt><dd>{t.counterpart_account_name}</dd></>)}
        {t.narration && (<><dt className="text-[var(--fg-subtle)]">Description</dt><dd className="break-words">{t.narration}</dd></>)}
        {t.notes && (<><dt className="text-[var(--fg-subtle)]">Notes</dt><dd className="break-words">{t.notes}</dd></>)}
        <dt className="text-[var(--fg-subtle)]">Source</dt>
        <dd>Entered manually</dd>
      </dl>

      {(t.reversed_by_id || t.reverses_id || t.refund_of_id) && (
        <div className="space-y-1 text-sm">
          {t.reversed_by_id && <button className="text-[var(--accent)] hover:underline" onClick={() => onOpenOther(t.reversed_by_id!)}>View the reversal →</button>}
          {t.reverses_id && <button className="text-[var(--accent)] hover:underline" onClick={() => onOpenOther(t.reverses_id!)}>View the original transaction →</button>}
          {t.refund_of_id && <button className="text-[var(--accent)] hover:underline" onClick={() => onOpenOther(t.refund_of_id!)}>View the original purchase →</button>}
        </div>
      )}

      {locked && <Alert kind="info">{t.kind === "reversal" ? "This reversal cancels out the original transaction. Delete it to undo the reversal." : "This transaction was reversed, so it no longer counts. Only notes can be changed."}</Alert>}
      {actionError && <Alert>{actionError}</Alert>}

      {confirm ? (
        <div className="space-y-3 rounded-lg border border-[var(--border)] p-4">
          <p className="text-sm font-medium">
            {confirm === "delete"
              ? t.kind === "transfer" ? "Delete this transfer? Both sides will be removed from your totals." : "Delete this transaction? It will be removed from all totals but kept in the history."
              : "Record that your bank reversed this? It will stop counting, and a matching reversal entry is added."}
          </p>
          <Field label="Reason (optional)" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} />
          <div className="flex gap-2">
            <Button variant={confirm === "delete" ? "danger" : "primary"} loading={busy} onClick={() => run(confirm)}>{confirm === "delete" ? "Delete" : "Record reversal"}</Button>
            <Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {!locked && <Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button>}
          {locked && t.kind !== "reversal" && <Button variant="secondary" onClick={() => setEditing(true)}>Edit notes</Button>}
          {t.status === "pending" && <Button variant="secondary" loading={busy} onClick={() => run("post")}>Mark completed</Button>}
          {t.status === "pending" && <Button variant="secondary" loading={busy} onClick={() => run("fail")}>Mark failed</Button>}
          {canReverse && <Button variant="secondary" onClick={() => setConfirm("reverse")}>Bank reversed it</Button>}
          <Button variant="ghost" className="text-[var(--danger)]" onClick={() => setConfirm("delete")}>Delete</Button>
        </div>
      )}

      <section>
        <h3 className="mb-2 text-sm font-semibold">History</h3>
        <ol className="space-y-3 border-l border-[var(--border)] pl-4 text-sm">
          {t.revisions.map((r, i) => (
            <li key={i}>
              <p className="font-medium">{ACTION_LABEL[r.action] ?? r.action} <span className="font-normal text-[var(--fg-subtle)]">· {new Date(r.created_at).toLocaleString("en-NG", { dateStyle: "medium", timeStyle: "short" })}</span></p>
              {r.action === "update" && (
                <ul className="mt-1 text-[var(--fg-subtle)]">
                  {Object.entries(r.changes).map(([f, [a, b]]) => (
                    <li key={f}>{FIELD_LABEL[f] ?? f}: {show(f, a, accounts, t.currency)} → {show(f, b, accounts, t.currency)}</li>
                  ))}
                </ul>
              )}
              {r.reason && <p className="text-[var(--fg-subtle)]">Reason: {r.reason}</p>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
