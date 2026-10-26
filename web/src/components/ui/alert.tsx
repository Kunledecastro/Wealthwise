import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Alert({ kind = "error", children }: { kind?: "error" | "success" | "info"; children: ReactNode }) {
  const Icon = kind === "success" ? CheckCircle2 : AlertCircle;
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      className={cn(
        "flex gap-2 rounded-md border px-3 py-2.5 text-sm",
        kind === "error" && "border-[var(--danger)]/40 bg-[var(--danger-bg)] text-[var(--danger)]",
        kind === "success" && "border-[var(--accent)]/40 bg-[var(--accent-bg)] text-[var(--accent-strong)]",
        kind === "info" && "border-[var(--border)] bg-[var(--muted)] text-[var(--fg)]",
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}
