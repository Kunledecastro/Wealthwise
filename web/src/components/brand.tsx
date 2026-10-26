export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Wealthwise";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 font-semibold tracking-tight text-[var(--fg)]">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="8" fill="var(--accent)" />
        <path d="M7 11l4 11 5-8 5 8 4-11" stroke="var(--accent-fg)" strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {!compact && <span className="text-lg">{APP_NAME}</span>}
    </span>
  );
}
