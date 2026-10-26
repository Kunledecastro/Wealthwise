"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Download } from "lucide-react";
import { useAuth } from "./auth-provider";
import { Alert } from "./ui/alert";
import { Button } from "./ui/button";
import { Card, CardHeader } from "./ui/card";
import { Field } from "./ui/field";
import { api, ApiError, type Me } from "@/lib/api";

export function EmailCard() {
  const { me, setMe } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<{ kind: "success" | "error"; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setStatus(null);
    if (!email.includes("@") || !password) {
      setStatus({ kind: "error", msg: "Enter the new email and your current password." });
      return;
    }
    setBusy(true);
    try {
      const updated = await api<Me>("/api/me/email", { method: "POST", body: { new_email: email, password } });
      setMe(updated);
      setEmail("");
      setPassword("");
      setStatus({ kind: "success", msg: "Email updated. Use it next time you sign in. Other devices were signed out." });
    } catch (err) {
      setStatus({ kind: "error", msg: err instanceof ApiError ? (err.fieldErrors[0]?.message ?? err.message) : "Could not update email." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Sign-in email" description={`Currently ${me?.email ?? ""}`} />
      <form onSubmit={submit} className="max-w-sm space-y-4" noValidate>
        <Field label="New email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="Current password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {status && <Alert kind={status.kind}>{status.msg}</Alert>}
        <Button type="submit" loading={busy}>Change email</Button>
      </form>
    </Card>
  );
}

export function DataCard() {
  const linkClass =
    "inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface)] px-4 text-sm font-medium hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]";
  return (
    <Card>
      <CardHeader title="Your data" description="Download a copy of everything Wealthwise holds about you." />
      <div className="flex flex-wrap gap-2">
        <a href="/api/me/export" className={linkClass}><Download className="h-4 w-4" aria-hidden /> Everything (JSON)</a>
        <a href="/api/transactions/export.csv" className={linkClass}><Download className="h-4 w-4" aria-hidden /> Transactions (CSV)</a>
      </div>
      <p className="mt-3 text-sm text-[var(--fg-subtle)]">The CSV opens in Excel or Google Sheets. Keep downloaded files somewhere safe: they contain your financial history.</p>
    </Card>
  );
}

export function DeleteAccountCard() {
  const router = useRouter();
  const { setMe } = useAuth();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/api/me/delete", { method: "POST", body: { password, confirm } });
      setMe(null);
      router.replace("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete your account.");
      setBusy(false);
    }
  }

  return (
    <Card className="border-[var(--danger)]/50">
      <CardHeader title="Delete my account" description="Permanently deletes your login, accounts, transactions and history. This cannot be undone. Export your data first if you want a copy." />
      {open ? (
        <form onSubmit={submit} className="max-w-sm space-y-4" noValidate>
          <Field label="Current password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <Field label='Type DELETE to confirm' autoComplete="off" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          {error && <Alert>{error}</Alert>}
          <div className="flex gap-2">
            <Button type="submit" variant="danger" loading={busy} disabled={confirm !== "DELETE" || !password}>Delete everything</Button>
            <Button type="button" variant="secondary" onClick={() => { setOpen(false); setError(null); }}>Cancel</Button>
          </div>
        </form>
      ) : (
        <Button variant="secondary" className="text-[var(--danger)]" onClick={() => setOpen(true)}>Delete my account…</Button>
      )}
    </Card>
  );
}
