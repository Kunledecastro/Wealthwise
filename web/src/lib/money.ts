/**
 * Display-only money formatting. Amounts arrive from the API as integer minor
 * units (kobo for NGN) and are never used for arithmetic in the browser.
 */
export function formatMinor(amountMinor: number | bigint, currency = "NGN", exponent = 2, locale = "en-NG"): string {
  const big = BigInt(amountMinor);
  const negative = big < 0n;
  const abs = negative ? -big : big;
  const base = 10n ** BigInt(exponent);
  const whole = abs / base;
  const frac = abs % base;
  const wholeStr = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(whole);
  const fracStr = exponent > 0 ? "." + frac.toString().padStart(exponent, "0") : "";
  const symbol =
    new Intl.NumberFormat(locale, { style: "currency", currency, currencyDisplay: "narrowSymbol" })
      .formatToParts(0)
      .find((p) => p.type === "currency")?.value ?? currency;
  return `${negative ? "-" : ""}${symbol}${wholeStr}${fracStr}`;
}

/**
 * Parse what a person types ("12,500.50", "₦ 1,000", "750") into integer minor units,
 * using string arithmetic only (no floating point). Returns null when the input is not
 * a valid positive amount with at most `exponent` decimal places.
 */
export function parseMoneyToMinor(input: string, exponent = 2, allowNegative = false): number | null {
  let s = input.trim().replace(/[₦,\s]/g, "");
  let negative = false;
  if (s.startsWith("-")) {
    if (!allowNegative) return null;
    negative = true;
    s = s.slice(1);
  }
  const m = /^(\d+)(?:\.(\d*))?$/.exec(s);
  if (!m) return null;
  const whole = m[1]!;
  const frac = m[2] ?? "";
  if (frac.length > exponent) return null;
  const minor = BigInt(whole) * 10n ** BigInt(exponent) + BigInt((frac + "0".repeat(exponent)).slice(0, exponent) || "0");
  if (minor > 10n ** 15n) return null;
  const n = Number(minor);
  if (n === 0 && !allowNegative) return null;
  return negative ? -n : n;
}

/** Minor units → plain editable string, e.g. 1250050 → "12500.50". */
export function minorToInput(amountMinor: number, exponent = 2): string {
  const neg = amountMinor < 0;
  const abs = BigInt(Math.abs(amountMinor));
  const base = 10n ** BigInt(exponent);
  const frac = (abs % base).toString().padStart(exponent, "0");
  return `${neg ? "-" : ""}${abs / base}${exponent ? "." + frac : ""}`;
}

/** Today's date (YYYY-MM-DD) in the given IANA timezone. */
export function todayIn(timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y!, (m ?? 1) - 1, d ?? 1)),
  );
}
