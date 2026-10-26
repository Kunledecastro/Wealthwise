import Link from "next/link";
import type { ReactNode } from "react";
import { Brand } from "./brand";

export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 flex justify-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]">
          <Brand />
        </Link>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm">
          <h1 className="text-xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-[var(--fg-subtle)]">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        {footer && <div className="mt-6 text-center text-sm text-[var(--fg-subtle)]">{footer}</div>}
      </div>
    </main>
  );
}
