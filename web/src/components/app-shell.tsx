"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuth } from "./auth-provider";
import { Brand } from "./brand";
import { Alert } from "./ui/alert";

export function AppShell({ children, adminOnly = false }: { children: ReactNode; adminOnly?: boolean }) {
  const { me, loading, error, setMe } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [signingOut, setSigningOut] = useState(false);

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

  const links = [
    { href: "/", label: "Home" },
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
      <header className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <Link href="/" className="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
            <Brand />
          </Link>
          <nav aria-label="Main" className="ml-auto flex items-center gap-1">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                aria-current={pathname === l.href ? "page" : undefined}
                className={cn(
                  "rounded-md px-3 py-2 text-sm hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
                  pathname === l.href ? "font-semibold text-[var(--fg)]" : "text-[var(--fg-subtle)]",
                )}
              >
                {l.label}
              </Link>
            ))}
            <button
              onClick={signOut}
              disabled={signingOut}
              className="ml-1 inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm text-[var(--fg-subtle)] hover:bg-[var(--muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">Sign out</span>
              <span className="sr-only sm:hidden">Sign out</span>
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
