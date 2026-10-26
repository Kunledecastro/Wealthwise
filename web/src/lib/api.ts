/**
 * Minimal API client. All calls are same-origin (/api/*), cookies are sent
 * automatically, and every state-changing request carries the CSRF header
 * (double-submit token, see docs/SECURITY.md).
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fieldErrors: { field: string; message: string }[] = [],
  ) {
    super(message);
  }
}

const CSRF_COOKIES = ["__Host-ww_csrf", "ww_csrf"];

export function readCsrfCookie(cookieString: string): string | null {
  for (const part of cookieString.split(";")) {
    const [rawName, ...rest] = part.trim().split("=");
    if (rawName && CSRF_COOKIES.includes(rawName)) return decodeURIComponent(rest.join("="));
  }
  return null;
}

async function ensureCsrf(): Promise<string> {
  const existing = typeof document !== "undefined" ? readCsrfCookie(document.cookie) : null;
  if (existing) return existing;
  const res = await fetch("/api/auth/csrf", { credentials: "same-origin" });
  const data = (await res.json()) as { csrf_token: string };
  return data.csrf_token;
}

export async function parseError(res: Response): Promise<ApiError> {
  let message = "Something went wrong. Please try again.";
  let fieldErrors: { field: string; message: string }[] = [];
  try {
    const body = (await res.json()) as { detail?: unknown; errors?: typeof fieldErrors };
    if (typeof body.detail === "string") message = body.detail;
    if (Array.isArray(body.errors)) fieldErrors = body.errors;
  } catch {
    /* non-JSON error body */
  }
  if (res.status === 429 && message.startsWith("Something")) {
    message = "Too many attempts. Please wait a few minutes.";
  }
  return new ApiError(res.status, message, fieldErrors);
}

export async function api<T>(
  path: string,
  options: { method?: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    headers["X-CSRF-Token"] = await ensureCsrf();
    headers["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

// ---- types mirrored from the API ----

export type Preferences = {
  currency: string;
  timezone: string;
  week_start: number;
  budget_alert_thresholds: number[];
  notify_in_app: boolean;
  notify_email: boolean;
  ai_enabled: boolean;
  external_ai_consent: boolean;
};

export type Me = {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "member";
  preferences: Preferences;
};

export type Invite = {
  id: string;
  email: string | null;
  note: string | null;
  created_at: string;
  expires_at: string;
  status: "pending" | "used" | "expired" | "revoked";
  invite_url?: string;
};

export type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  status: "active" | "disabled";
  created_at: string;
  last_login_at: string | null;
};
