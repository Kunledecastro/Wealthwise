import { describe, expect, it } from "vitest";
import { readCsrfCookie } from "./api";
import { formatMinor, minorToInput, parseMoneyToMinor } from "./money";
import { fragmentParam, loginSchema, registerSchema } from "./schemas";

describe("formatMinor", () => {
  it("formats kobo as naira without floating point", () => {
    expect(formatMinor(123456)).toBe("₦1,234.56");
    expect(formatMinor(5)).toBe("₦0.05");
    expect(formatMinor(-100000)).toBe("-₦1,000.00");
  });
  it("handles values beyond Number.MAX_SAFE_INTEGER", () => {
    expect(formatMinor(900719925474099312n)).toBe("₦9,007,199,254,740,993.12");
  });
});

describe("readCsrfCookie", () => {
  it("finds either cookie name", () => {
    expect(readCsrfCookie("a=1; ww_csrf=abc; b=2")).toBe("abc");
    expect(readCsrfCookie("__Host-ww_csrf=xyz")).toBe("xyz");
    expect(readCsrfCookie("other=1")).toBeNull();
  });
});

describe("fragmentParam", () => {
  it("reads tokens from the URL fragment only when plausible", () => {
    const t = "A".repeat(43);
    expect(fragmentParam(`#invite=${t}`, "invite")).toBe(t);
    expect(fragmentParam("#invite=short", "invite")).toBeNull();
    expect(fragmentParam("", "invite")).toBeNull();
  });
});

describe("schemas", () => {
  it("validates login", () => {
    expect(loginSchema.safeParse({ email: "x", password: "" }).success).toBe(false);
    expect(loginSchema.safeParse({ email: "a@b.co", password: "p" }).success).toBe(true);
  });
  it("requires matching passwords on register", () => {
    const base = { display_name: "Ada", email: "a@b.co", password: "Long-enough-1" };
    expect(registerSchema.safeParse({ ...base, confirm: "nope" }).success).toBe(false);
    expect(registerSchema.safeParse({ ...base, confirm: base.password }).success).toBe(true);
  });
});

describe("parseMoneyToMinor", () => {
  it("parses typed naira into exact kobo", () => {
    expect(parseMoneyToMinor("12,500.50")).toBe(1250050);
    expect(parseMoneyToMinor("₦ 1,000")).toBe(100000);
    expect(parseMoneyToMinor("0.1")).toBe(10);
    expect(parseMoneyToMinor("0.29")).toBe(29); // 0.29*100 is 28.999… in floating point
    expect(parseMoneyToMinor("1.")).toBe(100);
  });
  it("rejects invalid input", () => {
    for (const bad of ["", "abc", "1.234", "-5", "0", "1e5", "10000000000000.01", "1..2"]) {
      expect(parseMoneyToMinor(bad)).toBeNull();
    }
  });
  it("allows negatives and zero when asked (opening balances)", () => {
    expect(parseMoneyToMinor("-250.75", 2, true)).toBe(-25075);
    expect(parseMoneyToMinor("0", 2, true)).toBe(0);
  });
  it("round-trips with minorToInput", () => {
    for (const v of [0, 5, 1250050, -25075, 100]) {
      expect(parseMoneyToMinor(minorToInput(v), 2, true)).toBe(v);
    }
  });
});

import { bucketLabel, bucketTitle, compactMinor, isIsoDate, periodFromParams, periodLabel, presetRange } from "./periods";

describe("periods", () => {
  const today = "2026-10-28";
  it("computes presets in the user's own calendar", () => {
    expect(presetRange("this_month", today)).toEqual({ from: "2026-10-01", to: "2026-10-28" });
    expect(presetRange("last_month", today)).toEqual({ from: "2026-09-01", to: "2026-09-30" });
    expect(presetRange("last_3_months", today)).toEqual({ from: "2026-08-01", to: "2026-10-28" });
    expect(presetRange("this_year", today)).toEqual({ from: "2026-01-01", to: "2026-10-28" });
    expect(presetRange("last_month", "2026-03-15")).toEqual({ from: "2026-02-01", to: "2026-02-28" });
    expect(presetRange("last_month", "2026-01-10")).toEqual({ from: "2025-12-01", to: "2025-12-31" });
  });
  it("reads periods from the URL safely", () => {
    const p = (s: string) => periodFromParams(new URLSearchParams(s), today);
    expect(p("")).toEqual({ preset: "this_month", from: "2026-10-01", to: "2026-10-28" });
    expect(p("period=custom&from=2026-05-01&to=2026-05-31")).toEqual({ preset: "custom", from: "2026-05-01", to: "2026-05-31" });
    expect(p("period=custom&from=2026-05-31&to=2026-05-01").preset).toBe("this_month");
    expect(p("period=custom&from=2026-02-30&to=2026-03-01").preset).toBe("this_month");
    expect(p("period=evil").preset).toBe("this_month");
    expect(isIsoDate("2026-13-01")).toBe(false);
  });
  it("labels buckets and periods", () => {
    expect(bucketLabel("2026-10-05", "2026-10-05", "day")).toBe("5 Oct");
    expect(bucketLabel("2026-09-28", "2026-10-04", "week")).toBe("28 Sep–4 Oct");
    expect(bucketLabel("2026-10-01", "2026-10-31", "month")).toBe("Oct 26");
    expect(bucketTitle("2026-10-01", "2026-10-31", "month")).toBe("Oct 2026");
    expect(bucketTitle("2026-10-01", "2026-10-28", "month")).toBe("1 Oct – 28 Oct 2026");
    expect(bucketTitle("2026-10-05", "2026-10-05", "day")).toBe("Mon 5 Oct 2026");
    expect(periodLabel("2026-10-01", "2026-10-28")).toBe("1–28 Oct 2026");
    expect(periodLabel("2025-12-01", "2026-01-31")).toBe("1 Dec 2025 – 31 Jan 2026");
  });
  it("formats compact axis values", () => {
    expect(compactMinor(0)).toBe("₦0");
    expect(compactMinor(2_500_000_00)).toBe("₦2.5m");
    expect(compactMinor(25_000_00)).toBe("₦25k");
    expect(compactMinor(-1_500_00)).toBe("-₦1.5k");
  });
});

import { monthName, monthStart as ms, parseThresholds } from "./periods";

describe("budget helpers", () => {
  it("names months", () => {
    expect(monthName("2026-10-01")).toBe("October 2026");
    expect(monthName("2026-09-01", { short: true, year: false })).toBe("Sep");
    expect(ms("2026-01-15", -1)).toBe("2025-12-01");
  });
  it("parses thresholds strictly", () => {
    expect(parseThresholds("90, 70 100 70")).toEqual([70, 90, 100]);
    expect(parseThresholds("")).toBeNull();
    expect(parseThresholds("0")).toBeNull();
    expect(parseThresholds("201")).toBeNull();
    expect(parseThresholds("70.5")).toBeNull();
    expect(parseThresholds("1,2,3,4,5,6")).toBeNull();
  });
});
