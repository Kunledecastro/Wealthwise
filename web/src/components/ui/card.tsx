import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 sm:p-6", className)}>{children}</section>;
}

export function CardHeader({ title, description }: { title: string; description?: string }) {
  return (
    <header className="mb-5">
      <h2 className="text-base font-semibold text-[var(--fg)]">{title}</h2>
      {description && <p className="mt-1 text-sm text-[var(--fg-subtle)]">{description}</p>}
    </header>
  );
}
