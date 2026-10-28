"use client";

import { useMemo, useState, type FormEvent } from "react";
import { useAuth } from "./auth-provider";
import { CategorySelect, useCategories } from "./category-ui";
import { Alert } from "./ui/alert";
import { Button } from "./ui/button";
import { Field } from "./ui/field";
import { SelectField } from "./ui/select";
import { api, ApiError, type Account, type Transaction } from "@/lib/api";
import { minorToInput, parseMoneyToMinor, todayIn } from "@/lib/money";
import { cn } from "@/lib/utils";

type Mode = "expense" | "income" | "transfer" | "fee" | "refund" | "adjustment";
const MODES: { value: Mode; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
  { value: "fee", label: "Bank fee" },
  { value: "refund", label: "Refund" },
  { value: "adjustment", label: "Adjustment" },
];

type Props = {
  accounts: Account[];
  existing?: Transaction;
  defaultAccountId?: string;
  onDone: (message: string) => void;
};

/** Create or edit a transaction. Amounts are typed in naira and converted exactly to kobo. */
export function TransactionForm({ accounts, existing, defaultAccountId, onDone }: Props) {
  const { me } = useAuth();
  const tz = me?.preferences.timezone ?? "Africa/Lagos";
  const isEdit = Boolean(existing);
  const isTransferEdit = existing?.kind === "transfer";
  const notesOnly = existing?.status === "reversed";
  const usable = accounts.filter((a) => !a.is_archived || a.id === existing?.account_id);

  const [mode, setModeRaw] = useState<Mode>((existing?.kind as Mode) ?? "expense");
  function setMode(m: Mode) {
    setModeRaw(m);
    setCategoryId(""); // categories differ between spending and income
  }
  const [accountId, setAccountId] = useState(existing?.account_id ?? defaultAccountId ?? usable[0]?.id ?? "");
  const [toAccountId, setToAccountId] = useState(usable.find((a) => a.id !== accountId)?.id ?? "");
  const [amount, setAmount] = useState(existing ? minorToInput(existing.amount_minor) : "");
  const [direction, setDirection] = useState<"credit" | "debit">(existing?.direction ?? "debit");
  const [date, setDate] = useState(existing?.transaction_date ?? todayIn(tz));
  const [status, setStatus] = useState<"posted" | "pending" | "failed">(
    existing && existing.status !== "reversed" ? existing.status : "posted",
  );
  const [merchant, setMerchant] = useState(existing?.merchant ?? "");
  const [narration, setNarration] = useState(existing?.narration ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [reason, setReason] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const categories = useCategories();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const merchantLabel = mode === "income" ? "From (payer)" : "Merchant / payee";
  const currency = useMemo(() => accounts.find((a) => a.id === accountId)?.currency ?? "NGN", [accounts, accountId]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (notesOnly && existing) {
      setBusy(true);
      setFormError(null);
      try {
        await api(`/api/transactions/${existing.id}`, { method: "PATCH", body: { notes, reason: reason || undefined } });
        onDone("Notes updated.");
      } catch (err) {
        setFormError(err instanceof ApiError ? err.message : "Could not save.");
      } finally {
        setBusy(false);
      }
      return;
    }
    const errs: Record<string, string> = {};
    const amountMinor = parseMoneyToMinor(amount);
    if (amountMinor === null) errs.amount = "Enter an amount greater than 0, with at most 2 decimal places.";
    if (!accountId) errs.account = "Choose an account.";
    if (mode === "transfer" && !isEdit && (!toAccountId || toAccountId === accountId)) errs.to = "Choose a different account to send to.";
    if (!date) errs.date = "Choose a date.";
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setBusy(true);
    setFormError(null);
    try {
      if (isEdit && existing) {
        const body: Record<string, unknown> = {
          amount_minor: amountMinor,
          transaction_date: date,
          status,
          narration,
          notes,
          reason: reason || undefined,
        };
        if (!isTransferEdit) Object.assign(body, { account_id: accountId, kind: mode, merchant, ...(mode === "adjustment" ? { direction } : {}) });
        if (status === "posted" && existing.status === "pending") body.posting_date = date;
        await api(`/api/transactions/${existing.id}`, { method: "PATCH", body });
        onDone("Transaction updated.");
      } else if (mode === "transfer") {
        await api("/api/transactions/transfers", {
          method: "POST",
          body: { from_account_id: accountId, to_account_id: toAccountId, amount_minor: amountMinor, transaction_date: date, status, narration, notes },
        });
        onDone("Transfer saved.");
      } else {
        await api("/api/transactions", {
          method: "POST",
          body: {
            account_id: accountId,
            kind: mode,
            amount_minor: amountMinor,
            transaction_date: date,
            status,
            merchant,
            narration,
            notes,
            ...(mode === "adjustment" ? { direction } : {}),
            ...(categoryId ? { category_id: categoryId } : {}),
          },
        });
        onDone(`${MODES.find((m) => m.value === mode)?.label} saved.`);
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? (err.fieldErrors[0]?.message ?? err.message) : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  if (notesOnly) {
    return (
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Notes" value={notes} maxLength={1000} onChange={(e) => setNotes(e.target.value)} />
        <Field label="Reason for change (optional)" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} />
        {formError && <Alert>{formError}</Alert>}
        <Button type="submit" size="full" loading={busy}>Save notes</Button>
      </form>
    );
  }

  if (usable.length === 0) {
    return <Alert kind="info">Add an account first, then you can record transactions.</Alert>;
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {!isTransferEdit && (
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Type</legend>
          <div className="grid grid-cols-3 gap-2" role="radiogroup">
            {MODES.filter((m) => !(isEdit && m.value === "transfer")).map((m) => (
              <label
                key={m.value}
                className={cn(
                  "flex min-h-10 cursor-pointer items-center justify-center rounded-md border px-2 text-sm focus-within:ring-2 focus-within:ring-[var(--ring)]",
                  mode === m.value ? "border-[var(--accent)] bg-[var(--accent-bg)] font-semibold text-[var(--accent-strong)]" : "border-[var(--border)]",
                )}
              >
                <input type="radio" name="mode" value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} className="sr-only" />
                {m.label}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <Field
        label={`Amount (${currency === "NGN" ? "₦" : currency})`}
        inputMode="decimal"
        autoComplete="off"
        placeholder="e.g. 12,500.50"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        error={errors.amount}
      />

      {isTransferEdit ? (
        <p className="text-sm text-[var(--fg-subtle)]">
          Transfer between {existing!.direction === "debit" ? existing!.account_name : existing!.counterpart_account_name} →{" "}
          {existing!.direction === "debit" ? existing!.counterpart_account_name : existing!.account_name}. Changes apply to both sides.
        </p>
      ) : (
        <SelectField label={mode === "transfer" ? "From account" : "Account"} value={accountId} onChange={(e) => setAccountId(e.target.value)} error={errors.account}>
          {usable.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
        </SelectField>
      )}

      {mode === "transfer" && !isEdit && (
        <SelectField label="To account" value={toAccountId} onChange={(e) => setToAccountId(e.target.value)} error={errors.to}>
          <option value="">Choose…</option>
          {usable.filter((a) => a.id !== accountId).map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
        </SelectField>
      )}

      {mode === "adjustment" && (
        <SelectField label="Adjustment" value={direction} onChange={(e) => setDirection(e.target.value as "credit" | "debit")} hint="Use this to correct a balance. It is not counted as income or spending.">
          <option value="credit">Add money to the balance</option>
          <option value="debit">Remove money from the balance</option>
        </SelectField>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} error={errors.date} />
        <SelectField label="Status" value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
          <option value="posted">Completed</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </SelectField>
      </div>

      {mode !== "transfer" && (
        <Field label={merchantLabel} value={merchant} maxLength={120} onChange={(e) => setMerchant(e.target.value)} placeholder={mode === "income" ? "e.g. Employer" : "e.g. Shoprite"} />
      )}
      {!isEdit && categories.data && (mode === "expense" || mode === "income" || mode === "fee" || mode === "refund") && (
        <div className="space-y-1.5">
          <label htmlFor="txn-category" className="block text-sm font-medium">Category</label>
          <CategorySelect
            id="txn-category"
            categories={categories.data}
            txnKind={mode}
            value={categoryId}
            onChange={setCategoryId}
            emptyLabel="Automatic (recommended)"
            className="w-full min-h-10"
          />
          <p className="text-sm text-[var(--fg-subtle)]">Leave on Automatic and Wealthwise uses your rules and known merchants.</p>
        </div>
      )}
      <Field label="Description (optional)" value={narration} maxLength={500} onChange={(e) => setNarration(e.target.value)} />
      <Field label="Notes (optional)" value={notes} maxLength={1000} onChange={(e) => setNotes(e.target.value)} />
      {isEdit && <Field label="Reason for change (optional)" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} hint="Saved in the history." />}

      {mode === "refund" && !isEdit && (
        <p className="text-sm text-[var(--fg-subtle)]">Refunds reduce your spending. They are never counted as income.</p>
      )}
      {formError && <Alert>{formError}</Alert>}
      <Button type="submit" size="full" loading={busy}>{isEdit ? "Save changes" : "Save"}</Button>
    </form>
  );
}
