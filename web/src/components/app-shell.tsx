"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/use-load";
import { cn } from "@/lib/utils";
import { useAuth } from "./auth-provider";
import { Brand } from "./brand";
import { Alert } from "./ui/alert";

export function AppShell({ children, adminOnly = false }: { children: ReactNode; adminOnly?: boolean }) {
  const { me, loading, error, setMe } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [signingOut, setSigningOut] = useState(false);
  // Refetched on every page change so the badge stays current.
  const review = useLoad<{ count: number }>(me ? `/api/categories/review-count?p=${encodeURIComponent(pathname)}` : null);

  useEffect(() => {
    if (!loading && !me && !error) router.replace("/login");
    if (!loading && me && adminOnly && me.role !== "admin") router.replace("/");
  }, [loading, me, error, adminOnly, router]);

  if (loading || (!me && !error)) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-sm text-[var(--fg-subtle)]" role="status">
        Loading…
      </div>
    );
  }
  if (!me) {
    return (
      <div className="mx-auto max-w-md p-6">
        <Alert>{error}</Alert>
      </div>
    );
  }

  const links: { href: string; label: string; badge?: number }[] = [
    { href: "/", label: "Home" },
    { href: "/transactions", label: "Transactions" },
    { href: "/reports", label: "Reports" },
    { href: "/review", label: "To review", badge: review.data?.count ?? 0 },
    { href: "/categories", label: "Categories" },
    { href: "/accounts", label: "Accounts" },
    { href: "/imports", label: "Imports" },
    { href: "/settings", label: "Settings" },
    ...(me.role === "admin" ? [{ href: "/admin", label: "Admin" }] : []),
  ];

  async function signOut() {
    setSigningOut(true);
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setMe(null);
      router.replace("/login");
    }
  }

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 print:hidden border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
          <Link href="/" className="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
            <Brand />
          </Link>
          <nav aria-label="Main" className="-mx-1 order-last flex w-full items-center gap-1 overflow-x-auto sm:order-none sm:mx-0 sm:ml-auto sm:w-auto">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                aria-current={pathname === l.href || (l.href !== "/" && pathname.startsWith(l.href + "/")) ? "page" : undefined}
                className={cn(
                  "shrink-0 rounded-md px-3 py-2 text-sm hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
                  pathname === l.href ? "font-semibold text-[var(--fg)]" : "text-[var(--fg-subtle)]",
                )}
              >
                {l.label}
                {l.badge ? (
                  <span className="ml-1 rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white tabular" aria-label={`${l.badge} to review`}>{l.badge}</span>
                ) : null}
              </Link>
            ))}
            <button
              onClick={signOut}
              disabled={signingOut}
              className="ml-auto shrink-0 inline-flex items-center gap-1.5 sm:ml-1 rounded-md px-3 py-2 text-sm text-[var(--fg-subtle)] hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">Sign out</span>
              <span className="sr-only sm:hidden">Sign out</span>
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8 print:max-w-none print:p-0">{children}</main>
    </div>
  );
}
