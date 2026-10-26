import { describe, expect, it } from "vitest";
import { readCsrfCookie } from "./api";
import { formatMinor } from "./money";
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
