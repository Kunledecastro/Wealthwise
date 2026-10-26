"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { api, ApiError, type Preferences } from "@/lib/api";
import { changePasswordSchema, PASSWORD_MIN } from "@/lib/schemas";

export default function SettingsPage() {
  return (
    <AppShell>
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <PreferencesCard />
        <PasswordCard />
        <SessionsCard />
      </div>
    </AppShell>
  );
}

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const selectClass =
  "block w-full min-h-10 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)]";

function Toggle({ id, label, description, checked, onChange }: { id: string; label: string; description?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start gap-3">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 h-4 w-4 accent-[var(--accent)]" />
      <label htmlFor={id} className="text-sm">
        <span className="font-medium">{label}</span>
        {description && <span className="block text-[var(--fg-subtle)]">{description}</span>}
      </label>
    </div>
  );
}

function PreferencesCard() {
  const { me, setMe } = useAuth();
  const [prefs, setPrefs] = useState<Preferences>(me!.preferences);
  const [thresholds, setThresholds] = useState(me!.preferences.budget_alert_thresholds.join(", "));
  const [status, setStatus] = useState<{ kind: "success" | "error"; msg: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const timezones = useMemo(() => {
    const list = Intl.supportedValuesOf("timeZone");
    return list.includes(prefs.timezone) ? list : [prefs.timezone, ...list];
  }, [prefs.timezone]);

  function set<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    setPrefs((p) => ({ ...p, [key]: value }));
    setStatus(null);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    const parsed = thresholds.split(",").map((t) => t.trim()).filter(Boolean).map(Number);
    if (parsed.some((n) => !Number.isInteger(n) || n < 1 || n > 200) || parsed.length === 0) {
      setStatus({ kind: "error", msg: "Alert thresholds must be whole percentages between 1 and 200, separated by commas." });
      return;
    }
    setSaving(true);
    try {
      const updated = await api<Preferences>("/api/me/preferences", { method: "PATCH", body: { ...prefs, budget_alert_thresholds: parsed } });
      setPrefs(updated);
      setThresholds(updated.budget_alert_thresholds.join(", "));
      if (me) setMe({ ...me, preferences: updated });
      setStatus({ kind: "success", msg: "Preferences saved." });
    } catch (err) {
      setStatus({ kind: "error", msg: err instanceof ApiError ? (err.fieldErrors[0]?.message ?? err.message) : "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Preferences" description="How amounts, dates and alerts are shown to you." />
      <form onSubmit={save} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="currency" className="block text-sm font-medium">Currency</label>
            <select id="currency" className={selectClass} value={prefs.currency} onChange={(e) => set("currency", e.target.value)}>
              <option value="NGN">Nigerian naira (₦)</option>
            </select>
            <p className="text-sm text-[var(--fg-subtle)]">More currencies will be added later.</p>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="timezone" className="block text-sm font-medium">Timezone</label>
            <select id="timezone" className={selectClass} value={prefs.timezone} onChange={(e) => set("timezone", e.target.value)}>
              {timezones.map((tz) => <option key={tz} value={tz}>{tz.replaceAll("_", " ")}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="week_start" className="block text-sm font-medium">Week starts on</label>
            <select id="week_start" className={selectClass} value={prefs.week_start} onChange={(e) => set("week_start", Number(e.target.value))}>
              {WEEKDAYS.map((d, i) => <option key={d} value={i + 1}>{d}</option>)}
            </select>
          </div>
          <Field label="Budget alert thresholds (%)" value={thresholds} onChange={(e) => { setThresholds(e.target.value); setStatus(null); }} hint="Warn me when a budget reaches these percentages, e.g. 70, 90, 100." inputMode="numeric" />
        </div>
        <fieldset className="space-y-3">
          <legend className="mb-2 text-sm font-medium">Notifications</legend>
          <Toggle id="notify_in_app" label="In-app alerts" checked={prefs.notify_in_app} onChange={(v) => set("notify_in_app", v)} />
          <Toggle id="notify_email" label="Email alerts" description="Available once email notifications are enabled on the server." checked={prefs.notify_email} onChange={(v) => set("notify_email", v)} />
        </fieldset>
        <fieldset className="space-y-3">
          <legend className="mb-2 text-sm font-medium">AI features</legend>
          <Toggle id="ai_enabled" label="Use AI explanations" description="Runs on the server's local AI model. All figures still come from exact calculations." checked={prefs.ai_enabled} onChange={(v) => set("ai_enabled", v)} />
          <Toggle id="external_ai_consent" label="Allow external AI providers" description="Off by default. If on, your financial data may be sent to an AI service outside this server." checked={prefs.external_ai_consent} onChange={(v) => set("external_ai_consent", v)} />
        </fieldset>
        {status && <Alert kind={status.kind}>{status.msg}</Alert>}
        <Button type="submit" loading={saving}>Save preferences</Button>
      </form>
    </Card>
  );
}

type PwValues = z.infer<typeof changePasswordSchema>;

function PasswordCard() {
  const [status, setStatus] = useState<{ kind: "success" | "error"; msg: string } | null>(null);
  const { register, handleSubmit, formState, reset } = useForm<PwValues>({ resolver: zodResolver(changePasswordSchema) });

  async function onSubmit(v: PwValues) {
    setStatus(null);
    try {
      const res = await api<{ message: string }>("/api/auth/password/change", { method: "POST", body: { current_password: v.current_password, new_password: v.password } });
      reset();
      setStatus({ kind: "success", msg: res.message });
    } catch (e) {
      setStatus({ kind: "error", msg: e instanceof ApiError ? e.message : "Could not change password." });
    }
  }

  return (
    <Card>
      <CardHeader title="Password" description="Changing your password signs you out on other devices." />
      <form onSubmit={handleSubmit(onSubmit)} className="max-w-sm space-y-4" noValidate>
        <Field label="Current password" type="password" autoComplete="current-password" error={formState.errors.current_password?.message} {...register("current_password")} />
        <Field label="New password" type="password" autoComplete="new-password" hint={`At least ${PASSWORD_MIN} characters.`} error={formState.errors.password?.message} {...register("password")} />
        <Field label="Confirm new password" type="password" autoComplete="new-password" error={formState.errors.confirm?.message} {...register("confirm")} />
        {status && <Alert kind={status.kind}>{status.msg}</Alert>}
        <Button type="submit" loading={formState.isSubmitting}>Change password</Button>
      </form>
    </Card>
  );
}

function SessionsCard() {
  const router = useRouter();
  const { setMe } = useAuth();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function logoutAll() {
    setBusy(true);
    try {
      await api("/api/auth/logout-all", { method: "POST" });
      setMe(null);
      router.replace("/login");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not sign out.");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Devices" description="Lost a phone or used a shared computer? Sign out everywhere, including here." />
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      {confirming ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm">Sign out on all devices?</span>
          <Button variant="danger" loading={busy} onClick={logoutAll}>Yes, sign out everywhere</Button>
          <Button variant="secondary" onClick={() => setConfirming(false)}>Cancel</Button>
        </div>
      ) : (
        <Button variant="secondary" onClick={() => setConfirming(true)}>Sign out on all devices</Button>
      )}
    </Card>
  );
}
