import { forwardRef, useId, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string };

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, error, hint, className, id, ...props },
  ref,
) {
  const auto = useId();
  const inputId = id ?? auto;
  const describedBy = error ? `${inputId}-err` : hint ? `${inputId}-hint` : undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={inputId} className="block text-sm font-medium text-[var(--fg)]">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={cn(
          "block w-full min-h-10 rounded-md border bg-[var(--surface)] px-3 py-2 text-base text-[var(--fg)] placeholder:text-[var(--fg-subtle)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] sm:text-sm",
          error ? "border-[var(--danger)]" : "border-[var(--border)]",
          className,
        )}
        {...props}
      />
      {error ? (
        <p id={`${inputId}-err`} className="text-sm text-[var(--danger)]">{error}</p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-sm text-[var(--fg-subtle)]">{hint}</p>
      ) : null}
    </div>
  );
});
