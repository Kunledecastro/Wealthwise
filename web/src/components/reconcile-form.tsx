"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "./auth-provider";
import { Alert } from "./ui/alert";
import { Button } from "./ui/button";
import { Field } from "./ui/field";
import { api, ApiError, type Account, type ReconciliationRecord } from "@/lib/api";
import { formatDate, formatMinor, parseMoneyToMinor, todayIn } from "@/lib/money";
import { useLoad } from "@/lib/use-load";

/** Compare our balance with the one on a bank statement or in the banking app (rule B5). */
export function ReconcileForm({ account, onDone }: { account: Account; onDone: () => void }) {
  const { me } = useAuth();
  const today = todayIn(me?.preferences.timezone ?? "Africa/Lagos");
  const history = useLoad<ReconciliationRecord[]>(`/api/accounts/${account.id}/reconciliations`);
  const [asOf, setAsOf] = useState(today);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ReconciliationRecord | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const minor = parseMoneyToMinor(amount, 2, true);
    if (minor === null) return setError("Enter the balance exactly as the bank shows it, e.g. 423,943.06 (minus sign if overdrawn).");
    setBusy(true);
    try {
      const r = await api<ReconciliationRecord>(`/api/accounts/${account.id}/reconcile`, {
        method: "POST",
        body: { as_of_date: asOf, statement_balance_minor: minor },
      });
      setResult(r);
      history.reload();
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors[0]?.message ?? err.message) : "Could not check.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-[var(--fg-subtle)]">
        Type the balance your bank shows for <strong>{account.display_name}</strong> at the end of a day. Wealthwise compares it with its own figure for that date.
      </p>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Balance (₦)" inputMode="decimal" placeholder="e.g. 423,943.06" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <Field label="At the end of" type="date" max={today} min={account.opening_balance_date} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </div>
        {error && <Alert>{error}</Alert>}
        {result && (result.difference_minor_now === 0 ? (
          <Alert kind="success">Matches: Wealthwise also shows {formatMinor(result.computed_balance_minor_now)} on {formatDate(result.as_of_date)}.</Alert>
        ) : (
          <Alert>
            Wealthwise shows {formatMinor(result.computed_balance_minor_now)} on {formatDate(result.as_of_date)}, a difference of {formatMinor(Math.abs(result.difference_minor_now))}.
            Look for a missing, duplicated or mistyped transaction around that date, or check the starting balance.
          </Alert>
        ))}
        <Button type="submit" size="full" loading={busy}>Check balance</Button>
      </form>
      {history.data && history.data.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold">Previous checks</h3>
          <ul className="space-y-2 text-sm">
            {history.data.map((h) => (
              <li key={h.id} className="flex flex-wrap gap-x-2">
                <span>{formatDate(h.as_of_date)}</span>
                <span className="text-[var(--fg-subtle)]">{h.source === "statement" ? "from imported statement" : "entered by you"}</span>
                <span className="ml-auto tabular">{formatMinor(h.statement_balance_minor)}</span>
                <span className={h.difference_minor_now === 0 ? "text-[var(--accent-strong)]" : "text-amber-700 dark:text-amber-300"}>
                  {h.difference_minor_now === 0 ? "✓ matches now" : `differs by ${formatMinor(Math.abs(h.difference_minor_now))}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
