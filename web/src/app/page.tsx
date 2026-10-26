"use client";

import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { Card } from "@/components/ui/card";

export default function HomePage() {
  return (
    <AppShell>
      <Welcome />
    </AppShell>
  );
}

function Welcome() {
  const { me } = useAuth();
  if (!me) return null;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Welcome, {me.display_name}</h1>
        <p className="mt-1 text-[var(--fg-subtle)]">Spend wisely. Grow steadily.</p>
      </div>
      <Card>
        <h2 className="font-semibold">No financial data yet</h2>
        <p className="mt-1 text-sm text-[var(--fg-subtle)]">
          Accounts and transactions arrive in the next phase. For now you can set your currency, timezone and alert
          preferences.
        </p>
        <Link href="/settings" className="mt-4 inline-block text-sm font-medium text-[var(--accent)] hover:underline">
          Open settings →
        </Link>
      </Card>
    </div>
  );
}
