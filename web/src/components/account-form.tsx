"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "./auth-provider";
import { Alert } from "./ui/alert";
import { Button } from "./ui/button";
import { Field } from "./ui/field";
import { SelectField } from "./ui/select";
import { ACCOUNT_TYPE_LABEL, api, ApiError, type Account, type AccountType } from "@/lib/api";
import { minorToInput, parseMoneyToMinor, todayIn } from "@/lib/money";

export function AccountForm({ existing, onDone }: { existing?: Account; onDone: (msg: string) => void }) {
  const { me } = useAuth();
  const today = todayIn(me?.preferences.timezone ?? "Africa/Lagos");
  const [type, setType] = useState<AccountType>(existing?.type ?? "bank");
  const [name, setName] = useState(existing?.display_name ?? "");
  const [institution, setInstitution] = useState(existing?.institution_name ?? "");
  const [mask, setMask] = useState(existing?.mask ?? "");
  const [opening, setOpening] = useState(existing ? minorToInput(existing.opening_balance_minor) : "");
  const [openingDate, setOpeningDate] = useState(existing?.opening_balance_date ?? today);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    const openingMinor = parseMoneyToMinor(opening || "0", 2, true);
    if (!name.trim()) errs.name = "Give the account a name.";
    if (openingMinor === null) errs.opening = "Enter an amount like 150,000.00 (use a minus sign for money owed).";
    if (mask && !/^\d{4}$/.test(mask)) errs.mask = "Enter exactly the last 4 digits, or leave blank.";
    if (!openingDate) errs.openingDate = "Choose a date.";
    else if (openingDate > today) errs.openingDate = "The date cannot be in the future.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setFormError(null);
    const body = {
      type,
      display_name: name,
      institution_name: institution,
      mask,
      opening_balance_minor: openingMinor,
      opening_balance_date: openingDate,
    };
    try {
      if (existing) {
        await api(`/api/accounts/${existing.id}`, { method: "PATCH", body });
        onDone("Account updated.");
      } else {
        await api("/api/accounts", { method: "POST", body: { ...body, currency: "NGN" } });
        onDone("Account added.");
      }
    } catch (err) {
      setFormError(err instanceof ApiError ? (err.fieldErrors[0]?.message ?? err.message) : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <SelectField label="Type" value={type} onChange={(e) => setType(e.target.value as AccountType)}>
        {Object.entries(ACCOUNT_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </SelectField>
      <Field label="Name" placeholder="e.g. GTBank salary" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} error={errors.name} />
      <Field label="Bank or provider (optional)" placeholder="e.g. Guaranty Trust Bank" value={institution} maxLength={80} onChange={(e) => setInstitution(e.target.value)} />
      <Field
        label="Last 4 digits (optional)"
        inputMode="numeric"
        maxLength={4}
        value={mask}
        onChange={(e) => setMask(e.target.value.replace(/\D/g, ""))}
        hint="Only to help you recognise the account. Never enter the full account number."
        error={errors.mask}
      />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Starting balance (₦)" inputMode="decimal" placeholder="0.00" value={opening} onChange={(e) => setOpening(e.target.value)} error={errors.opening} />
        <Field label="As of" type="date" max={today} value={openingDate} onChange={(e) => setOpeningDate(e.target.value)} error={errors.openingDate} />
      </div>
      <p className="text-sm text-[var(--fg-subtle)]">
        The balance on that date, from your banking app or statement. Transactions dated before it are assumed to be included already.
        {existing && existing.transaction_count > 0 && " Changing it updates the calculated balance."}
      </p>
      {formError && <Alert>{formError}</Alert>}
      <Button type="submit" size="full" loading={busy}>{existing ? "Save changes" : "Add account"}</Button>
    </form>
  );
}
