/**
 * Reporting periods. Pure string date arithmetic on YYYY-MM-DD (no timezones involved:
 * "today" is supplied by the caller in the user's own timezone).
 */
import type { Granularity } from "./api";

export type PresetId = "this_month" | "last_month" | "last_3_months" | "this_year" | "custom";
export type Period = { preset: PresetId; from: string; to: string };

export const PRESETS: { id: PresetId; label: string }[] = [
  { id: "this_month", label: "This month" },
  { id: "last_month", label: "Last month" },
  { id: "last_3_months", label: "Last 3 months" },
  { id: "this_year", label: "This year" },
  { id: "custom", label: "Custom" },
];

const ISO = /^\d{4}-\d{2}-\d{2}$/;

function parts(iso: string): [number, number, number] {
  const [y, m, d] = iso.split("-").map(Number);
  return [y!, m!, d!];
}

function iso(y: number, m: number, d: number): string {
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.toISOString().slice(0, 10);
}

export function isIsoDate(s: string | null | undefined): s is string {
  if (!s || !ISO.test(s)) return false;
  const [y, m, d] = parts(s);
  return iso(y, m, d) === s;
}

/** First day of the month `offset` months from the month containing `day`. */
export function monthStart(day: string, offset = 0): string {
  const [y, m] = parts(day);
  return iso(y, m + offset, 1);
}

export function monthEnd(day: string, offset = 0): string {
  const [y, m] = parts(day);
  return iso(y, m + offset + 1, 0);
}

export function presetRange(preset: Exclude<PresetId, "custom">, today: string): { from: string; to: string } {
  const [y] = parts(today);
  switch (preset) {
    case "this_month":
      return { from: monthStart(today), to: today };
    case "last_month":
      return { from: monthStart(today, -1), to: monthEnd(today, -1) };
    case "last_3_months":
      return { from: monthStart(today, -2), to: today };
    case "this_year":
      return { from: iso(y, 1, 1), to: today };
  }
}

/** Read a period from URL search params, falling back to this month. */
export function periodFromParams(params: URLSearchParams, today: string): Period {
  const p = params.get("period") as PresetId | null;
  if (p === "custom") {
    const from = params.get("from");
    const to = params.get("to");
    if (isIsoDate(from) && isIsoDate(to) && from <= to) return { preset: "custom", from, to };
  } else if (p && PRESETS.some((x) => x.id === p)) {
    return { preset: p, ...presetRange(p as Exclude<PresetId, "custom">, today) };
  }
  return { preset: "this_month", ...presetRange("this_month", today) };
}

export function periodToParams(period: Period): Record<string, string> {
  return period.preset === "custom" ? { period: "custom", from: period.from, to: period.to } : { period: period.preset };
}

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function weekday(day: string): string {
  const [y, m, d] = parts(day);
  return DAYS_SHORT[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]!;
}

/** Short label for a chart bucket. */
export function bucketLabel(from: string, to: string, g: Granularity): string {
  const [y, m, d] = parts(from);
  if (g === "month") return `${MONTHS_SHORT[m - 1]} ${String(y).slice(2)}`;
  if (g === "day") return `${d} ${MONTHS_SHORT[m - 1]}`;
  const [, m2, d2] = parts(to);
  return m === m2 ? `${d}–${d2} ${MONTHS_SHORT[m - 1]}` : `${d} ${MONTHS_SHORT[m - 1]}–${d2} ${MONTHS_SHORT[m2 - 1]}`;
}

/** Full label for a bucket, used in tooltips and tables. */
export function bucketTitle(from: string, to: string, g: Granularity): string {
  const [y, m, d] = parts(from);
  if (g === "day") return `${weekday(from)} ${d} ${MONTHS_SHORT[m - 1]} ${y}`;
  const [y2, m2, d2] = parts(to);
  if (g === "month" && d === 1 && to === monthEnd(from)) return `${MONTHS_SHORT[m - 1]} ${y}`;
  return `${d} ${MONTHS_SHORT[m - 1]}${y !== y2 ? ` ${y}` : ""} – ${d2} ${MONTHS_SHORT[m2 - 1]} ${y2}`;
}

/** Human description of a period, e.g. "1–28 Oct 2026". */
export function periodLabel(from: string, to: string): string {
  const [y, m, d] = parts(from);
  const [y2, m2, d2] = parts(to);
  if (y === y2 && m === m2) return d === d2 ? `${d} ${MONTHS_SHORT[m - 1]} ${y}` : `${d}–${d2} ${MONTHS_SHORT[m - 1]} ${y}`;
  if (y === y2) return `${d} ${MONTHS_SHORT[m - 1]} – ${d2} ${MONTHS_SHORT[m2 - 1]} ${y}`;
  return `${d} ${MONTHS_SHORT[m - 1]} ${y} – ${d2} ${MONTHS_SHORT[m2 - 1]} ${y2}`;
}

/** Compact axis label from minor units, e.g. 2_500_000_00 → "₦2.5m". Display only. */
export function compactMinor(minor: number): string {
  const major = minor / 100;
  const abs = Math.abs(major);
  const sign = major < 0 ? "-" : "";
  const fmt = (n: number, suffix: string) => `${sign}₦${Number(n.toFixed(n < 10 ? 1 : 0))}${suffix}`;
  if (abs >= 1e9) return fmt(abs / 1e9, "bn");
  if (abs >= 1e6) return fmt(abs / 1e6, "m");
  if (abs >= 1e3) return fmt(abs / 1e3, "k");
  return `${sign}₦${Math.round(abs)}`;
}

const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** "2026-10-01" → "October 2026" (or "Oct" with short=true and no year). */
export function monthName(iso: string, opts: { short?: boolean; year?: boolean } = {}): string {
  const [y, m] = parts(iso);
  const name = opts.short ? MONTHS_SHORT[m - 1]! : MONTHS_LONG[m - 1]!;
  return opts.year === false ? name : `${name} ${y}`;
}

/** Parse "70, 90, 100" into sorted unique whole percentages 1..200 (null if invalid). */
export function parseThresholds(text: string): number[] | null {
  const bits = text.split(/[,\s]+/).filter(Boolean);
  if (bits.length < 1 || bits.length > 5) return null;
  const nums = bits.map((b) => (/^\d{1,3}$/.test(b) ? Number(b) : NaN));
  if (nums.some((n) => !Number.isInteger(n) || n < 1 || n > 200)) return null;
  return [...new Set(nums)].sort((a, b) => a - b);
}
