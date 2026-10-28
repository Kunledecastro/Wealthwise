"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { FlaskConical, Upload } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SelectField } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import { api, ApiError, type Account, type AppConfig, type ImportBatch, type ImportDetail } from "@/lib/api";
import { formatDate } from "@/lib/money";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";

export default function ImportsPage() {
  return (
    <AppShell>
      <Suspense fallback={<p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}>
        <Imports />
      </Suspense>
    </AppShell>
  );
}

const STATUS: Record<ImportBatch["status"], { label: string; cls: string }> = {
  staged: { label: "Waiting for review", cls: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
  committed: { label: "Imported", cls: "bg-[var(--accent-bg)] text-[var(--accent-strong)]" },
  undone: { label: "Undone", cls: "bg-[var(--muted)] text-[var(--fg-subtle)]" },
  discarded: { label: "Cancelled", cls: "bg-[var(--muted)] text-[var(--fg-subtle)]" },
};

function Imports() {
  const params = useSearchParams();
  const router = useRouter();
  const list = useLoad<ImportBatch[]>("/api/imports");
  const accounts = useLoad<Account[]>("/api/accounts");
  const config = useLoad<AppConfig>("/api/me/app-config");
  const [open, setOpen] = useState(params.get("account") !== null);
  const [simBusy, setSimBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function simulate() {
    setSimBusy(true);
    setError(null);
    try {
      const b = await api<ImportDetail>("/api/imports/simulate", { method: "POST", body: { days: 30 } });
      router.push(`/imports/${b.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not simulate.");
      setSimBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Imports</h1>
          <p className="text-sm text-[var(--fg-subtle)]">Bring in transactions from your bank&apos;s CSV or Excel statement.</p>
        </div>
        <div className="ml-auto flex gap-2">
          {config.data?.demo_mode && (
            <Button variant="secondary" loading={simBusy} onClick={simulate} title="Creates fake bank activity in a clearly labelled demo account">
              <FlaskConical className="h-4 w-4" aria-hidden /> Simulate bank events
            </Button>
          )}
          <Button onClick={() => setOpen(true)}><Upload className="h-4 w-4" aria-hidden /> Import statement</Button>
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {list.error && <Alert>{list.error}</Alert>}
      {list.loading && <p role="status" className="text-sm text-[var(--fg-subtle)]">Loading…</p>}
      {list.data && list.data.length === 0 && (
        <Card>
          <h2 className="font-semibold">No imports yet</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-[var(--fg-subtle)]">
            <li>In your bank&apos;s app or internet banking, download your statement as <strong>CSV</strong> or <strong>Excel</strong>.</li>
            <li>Click <strong>Import statement</strong>, choose the account and the file.</li>
            <li>Check the rows, then press <strong>Import</strong>. Nothing is saved before that.</li>
          </ol>
        </Card>
      )}
      {list.data && list.data.length > 0 && (
        <Card className="p-0 sm:p-0">
          <ul className="divide-y divide-[var(--border)]">
            {list.data.map((b) => (
              <li key={b.id}>
                <Link href={`/imports/${b.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 hover:bg-[var(--muted)] focus-visible:bg-[var(--muted)] focus-visible:outline-none">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{b.filename}</p>
                    <p className="text-sm text-[var(--fg-subtle)]">
                      {b.account_name}
                      {b.statement_first_date && b.statement_last_date && ` · ${formatDate(b.statement_first_date)} – ${formatDate(b.statement_last_date)}`}
                      {b.status === "committed" && ` · ${b.counts.committed ?? 0} added`}
                      {b.status === "staged" && ` · ${b.counts.included ?? 0} selected`}
                    </p>
                  </div>
                  <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS[b.status].cls)}>{STATUS[b.status].label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Sheet title="Import statement" open={open} onClose={() => setOpen(false)}>
        {open && accounts.data && <UploadForm accounts={accounts.data} maxMb={config.data?.upload_max_mb ?? 10} initialAccount={params.get("account") ?? undefined} />}
      </Sheet>
    </div>
  );
}

function UploadForm({ accounts, maxMb, initialAccount }: { accounts: Account[]; maxMb: number; initialAccount?: string }) {
  const router = useRouter();
  const [accountId, setAccountId] = useState(initialAccount ?? accounts[0]?.id ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (accounts.length === 0) {
    return <Alert kind="info">Add the account first (Accounts → Add account), then import its statement.</Alert>;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file) return setError("Choose a statement file.");
    if (file.size > maxMb * 1024 * 1024) return setError(`The file is larger than ${maxMb} MB.`);
    const form = new FormData();
    form.append("account_id", accountId);
    form.append("file", file);
    setBusy(true);
    try {
      const b = await api<ImportDetail>("/api/imports", { method: "POST", form });
      router.push(`/imports/${b.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <SelectField label="Which account is this statement for?" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
        {accounts.map((a) => <option key={a.id} value={a.id}>{a.display_name}</option>)}
      </SelectField>
      <div className="space-y-1.5">
        <label htmlFor="file" className="block text-sm font-medium">Statement file</label>
        <input
          id="file"
          type="file"
          accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="block w-full text-sm file:mr-3 file:min-h-10 file:rounded-md file:border-0 file:bg-[var(--muted)] file:px-4 file:text-sm file:font-medium"
        />
        <p className="text-sm text-[var(--fg-subtle)]">CSV, Excel (.xlsx) or older Excel (.xls), up to {maxMb} MB. The file itself isn&apos;t kept after reading.</p>
      </div>
      {error && <Alert>{error}</Alert>}
      <Button type="submit" size="full" loading={busy}>Upload and review</Button>
      <p className="text-xs text-[var(--fg-subtle)]">Never upload your internet-banking password, PIN or OTP anywhere. Wealthwise never asks for them.</p>
    </form>
  );
}
