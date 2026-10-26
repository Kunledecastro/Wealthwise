"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Check, Copy } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { api, ApiError, type AdminUser, type Invite } from "@/lib/api";

const dateFmt = new Intl.DateTimeFormat("en-NG", { dateStyle: "medium", timeStyle: "short" });

export default function AdminPage() {
  return (
    <AppShell adminOnly>
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Admin</h1>
        <AdminContent />
      </div>
    </AppShell>
  );
}

function AdminContent() {
  const { me } = useAuth();
  const [invites, setInvites] = useState<Invite[] | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchAll = useCallback(
    () => Promise.all([api<Invite[]>("/api/admin/invites"), api<AdminUser[]>("/api/admin/users")]),
    [],
  );
  const apply = useCallback(([i, u]: [Invite[], AdminUser[]]) => {
    setInvites(i);
    setUsers(u);
  }, []);
  const fail = useCallback((e: unknown) => {
    setLoadError(e instanceof ApiError ? e.message : "Could not load admin data.");
  }, []);
  const load = useCallback(() => {
    fetchAll().then(apply).catch(fail);
  }, [fetchAll, apply, fail]);

  useEffect(() => {
    let active = true;
    fetchAll()
      .then((r) => active && apply(r))
      .catch((e: unknown) => active && fail(e));
    return () => {
      active = false;
    };
  }, [fetchAll, apply, fail]);

  if (me?.role !== "admin") return null;
  if (loadError) return <Alert>{loadError}</Alert>;

  return (
    <>
      <InviteCard onCreated={load} />
      <Card>
        <CardHeader title="Invites" description="Links are shown only once, when created." />
        {invites === null ? (
          <p className="text-sm text-[var(--fg-subtle)]" role="status">Loading…</p>
        ) : invites.length === 0 ? (
          <p className="text-sm text-[var(--fg-subtle)]">No invites yet.</p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {invites.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-sm">
                <span className="font-medium">{inv.email ?? "Anyone with the link"}</span>
                {inv.note && <span className="text-[var(--fg-subtle)]">{inv.note}</span>}
                <span className="text-[var(--fg-subtle)]">expires {dateFmt.format(new Date(inv.expires_at))}</span>
                <StatusBadge status={inv.status} />
                {inv.status === "pending" && (
                  <Button size="sm" variant="ghost" className="ml-auto"
                    onClick={async () => { await api(`/api/admin/invites/${inv.id}/revoke`, { method: "POST" }); load(); }}>
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardHeader title="People" />
        {users === null ? (
          <p className="text-sm text-[var(--fg-subtle)]" role="status">Loading…</p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {users.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-sm">
                <span className="font-medium">{u.display_name}</span>
                <span className="text-[var(--fg-subtle)]">{u.email}</span>
                <span className="text-[var(--fg-subtle)]">{u.role}</span>
                <StatusBadge status={u.status} />
                {u.id !== me.id && (
                  <Button size="sm" variant="ghost" className="ml-auto"
                    onClick={async () => {
                      const next = u.role === "admin" ? "member" : "admin";
                      if (!window.confirm(next === "admin" ? `Make ${u.display_name} an admin? They will be able to invite and disable people.` : `Remove admin rights from ${u.display_name}?`)) return;
                      await api(`/api/admin/users/${u.id}/role`, { method: "POST", body: { role: next } });
                      load();
                    }}>
                    {u.role === "admin" ? "Remove admin" : "Make admin"}
                  </Button>
                )}
                {u.id !== me.id && (
                  <Button size="sm" variant="ghost"
                    onClick={async () => {
                      const next = u.status === "active" ? "disabled" : "active";
                      if (next === "disabled" && !window.confirm(`Disable ${u.display_name}? They will be signed out immediately.`)) return;
                      await api(`/api/admin/users/${u.id}/status`, { method: "POST", body: { status: next } });
                      load();
                    }}>
                    {u.status === "active" ? "Disable" : "Enable"}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function StatusBadge({ status }: { status: string }) {
  const good = status === "pending" || status === "active";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${good ? "bg-[var(--accent-bg)] text-[var(--accent-strong)]" : "bg-[var(--muted)] text-[var(--fg-subtle)]"}`}>
      {status}
    </span>
  );
}

function InviteCard({ onCreated }: { onCreated: () => void }) {
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      const inv = await api<Invite>("/api/admin/invites", { method: "POST", body: { email: email.trim() || null, note: note.trim() || null } });
      setLink(inv.invite_url ?? null);
      setEmail("");
      setNote("");
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? (err.fieldErrors[0]?.message ?? err.message) : "Could not create invite.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Invite someone" description="Invites are single-use and expire after 7 days. Send the link privately." />
      <form onSubmit={create} className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label="Email (optional)" type="email" value={email} onChange={(e) => setEmail(e.target.value)} hint="If set, only this email can use the link." />
        <Field label="Note (optional)" value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} hint="e.g. their name" />
        <div className="sm:pb-6"><Button type="submit" loading={busy}>Create invite</Button></div>
      </form>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      {link && (
        <div className="mt-4 space-y-2">
          <Alert kind="success">Invite created. Copy it now; it won&apos;t be shown again.</Alert>
          <div className="flex gap-2">
            <input readOnly value={link} aria-label="Invite link" className="min-h-10 flex-1 rounded-md border border-[var(--border)] bg-[var(--muted)] px-3 text-sm" onFocus={(e) => e.target.select()} />
            <Button variant="secondary" onClick={async () => { await navigator.clipboard.writeText(link); setCopied(true); }}>
              {copied ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
