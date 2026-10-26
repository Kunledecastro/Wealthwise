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
