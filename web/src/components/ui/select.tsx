import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Props = SelectHTMLAttributes<HTMLSelectElement> & { label: string; error?: string; hint?: string; children: ReactNode };

export const SelectField = forwardRef<HTMLSelectElement, Props>(function SelectField({ label, error, hint, id, className, children, ...props }, ref) {
  const auto = useId();
  const sid = id ?? auto;
  return (
    <div className="space-y-1.5">
      <label htmlFor={sid} className="block text-sm font-medium">{label}</label>
      <select
        ref={ref}
        id={sid}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${sid}-err` : hint ? `${sid}-hint` : undefined}
        className={cn(
          "block w-full min-h-10 rounded-md border bg-[var(--surface)] px-3 py-2 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-[var(--ring)]",
          error ? "border-[var(--danger)]" : "border-[var(--border)]",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      {error ? <p id={`${sid}-err`} className="text-sm text-[var(--danger)]">{error}</p> : hint ? <p id={`${sid}-hint`} className="text-sm text-[var(--fg-subtle)]">{hint}</p> : null}
    </div>
  );
});
