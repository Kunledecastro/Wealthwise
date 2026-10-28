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
  options: { method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    headers["X-CSRF-Token"] = await ensureCsrf();
    // For uploads the browser sets the multipart Content-Type (with its boundary) itself.
    if (!options.form) headers["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: options.form ?? (options.body === undefined ? undefined : JSON.stringify(options.body)),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
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

// ---- Phase 2: finance ----

export type AccountType = "bank" | "wallet" | "cash" | "savings" | "card" | "loan";
export const ACCOUNT_TYPE_LABEL: Record<AccountType, string> = {
  bank: "Bank account",
  wallet: "Wallet",
  cash: "Cash",
  savings: "Savings",
  card: "Card",
  loan: "Loan",
};

export type Balance = {
  posted_minor: number;
  pending_in: number;
  pending_out: number;
  available_incl_pending: number;
  status: "estimated" | "reconciled" | "unreconciled";
  as_of: string;
  statement_as_of: string | null;
  statement_balance_minor: number | null;
  difference_minor: number | null;
};

export type Account = {
  id: string;
  type: AccountType;
  display_name: string;
  institution_name: string | null;
  mask: string | null;
  currency: string;
  opening_balance_minor: number;
  opening_balance_date: string;
  source: "manual" | "imported" | "simulated" | "connected";
  is_archived: boolean;
  created_at: string;
  transaction_count: number;
  balance: Balance;
};

export type TxnKind = "income" | "expense" | "fee" | "refund" | "transfer" | "reversal" | "adjustment";
export type TxnStatus = "pending" | "posted" | "failed" | "reversed";
export const KIND_LABEL: Record<TxnKind, string> = {
  income: "Income",
  expense: "Expense",
  fee: "Bank fee",
  refund: "Refund",
  transfer: "Transfer",
  reversal: "Reversal",
  adjustment: "Adjustment",
};

export type Transaction = {
  id: string;
  account_id: string;
  account_name: string;
  kind: TxnKind;
  direction: "debit" | "credit";
  amount_minor: number;
  currency: string;
  status: TxnStatus;
  transaction_date: string;
  posting_date: string | null;
  merchant: string | null;
  narration: string | null;
  notes: string | null;
  source: string;
  transfer_group_id: string | null;
  counterpart_account_id: string | null;
  counterpart_account_name: string | null;
  reverses_id: string | null;
  reversed_by_id: string | null;
  refund_of_id: string | null;
  merchant_normalised: string | null;
  category_id: string | null;
  category_name: string | null;
  category_color: string | null;
  category_source: "none" | "user" | "rule" | "system" | "linked" | "ai";
  category_confidence: number;
  category_reason: string | null;
  needs_review: boolean;
  created_at: string;
  updated_at: string;
};

export type Revision = { action: string; changes: Record<string, [unknown, unknown]>; reason: string | null; created_at: string };
export type TransactionDetail = Transaction & { revisions: Revision[] };
export type TransactionPage = { items: Transaction[]; total: number; page: number; page_size: number };

export type CurrencySummary = {
  currency: string;
  income: number;
  gross_spending: number;
  fees: number;
  refunds: number;
  net_spending: number;
  net_cash_flow: number;
  pending_in: number;
  pending_out: number;
  transaction_count: number;
};

export type Summary = {
  date_from: string;
  date_to: string;
  timezone: string;
  summaries: CurrencySummary[];
  accounts: Account[];
  balance_totals: Record<string, number>;
  balances_are_estimated: boolean;
};

// ---- Phase 3: statement import ----

export type ColumnRole = "date" | "posting_date" | "description" | "debit" | "credit" | "amount" | "indicator" | "balance" | "reference";
export type Mapping = {
  header_row: number | null;
  columns: Record<ColumnRole, number | null>;
  amount_mode: "debit_credit" | "signed" | "indicator" | null;
  date_order: "DMY" | "MDY" | "YMD";
  from_profile?: boolean;
};

export type ImportRow = {
  id: string;
  row_number: number;
  outcome: "new" | "duplicate" | "possible_duplicate" | "error";
  include: boolean;
  error: string | null;
  note: string | null;
  transaction_date: string | null;
  posting_date: string | null;
  direction: "debit" | "credit" | null;
  amount_minor: number | null;
  narration: string | null;
  external_ref: string | null;
  balance_after_minor: number | null;
  suggested_kind: string | null;
  kind: string | null;
  allowed_kinds: string[];
  transaction_id: string | null;
  merchant_normalised: string | null;
  category_id: string | null;
  category_name: string | null;
  category_source: string;
  category_confidence: number;
  category_reason: string | null;
};

export type ImportBatch = {
  id: string;
  account_id: string;
  account_name: string;
  adapter: "csv" | "xlsx" | "xls" | "simulated";
  filename: string;
  sheet_name: string | null;
  status: "staged" | "committed" | "discarded" | "undone";
  counts: Record<string, number>;
  warnings: string[];
  statement_first_date: string | null;
  statement_last_date: string | null;
  statement_opening_balance_minor: number | null;
  statement_closing_balance_minor: number | null;
  can_set_opening: boolean;
  created_at: string;
  committed_at: string | null;
  finished_at: string | null;
  same_file_imported_at: string | null;
};

export type ImportDetail = ImportBatch & {
  mapping: Mapping | null;
  headers: string[];
  preview: string[][];
  rows: ImportRow[];
  rows_total: number;
  page: number;
  page_size: number;
};

export type CommitResult = {
  created: number;
  transfers_linked: number;
  reversals_linked: number;
  opening_balance_set: boolean;
  reconciliation: { as_of: string; statement_minor: number; computed_minor: number; difference_minor: number; matches: boolean } | null;
  batch: ImportBatch;
};

export type ReconciliationRecord = {
  id: string;
  as_of_date: string;
  statement_balance_minor: number;
  computed_balance_minor_then: number;
  computed_balance_minor_now: number;
  difference_minor_now: number;
  source: "statement" | "manual";
  created_at: string;
};

export type AppConfig = { demo_mode: boolean; upload_max_mb: number };

// ---- Phase 4: categories ----

export type Category = {
  id: string;
  slug: string | null;
  name: string;
  kind: "expense" | "income" | "transfer";
  color: string;
  is_archived: boolean;
  locked: boolean;
  transaction_count: number;
  rule_count: number;
};

export type CategoryRule = {
  id: string;
  category_id: string;
  category_name: string;
  match_type: "contains" | "starts_with" | "equals";
  pattern: string;
  direction: "debit" | "credit" | null;
  account_id: string | null;
  account_name: string | null;
  priority: number;
  created_from: "manual" | "user_correction";
  is_active: boolean;
  hit_count: number;
};

export type RuleSuggestion = {
  pattern: string | null;
  match_type: string;
  category_id: string | null;
  category_name: string | null;
  similar_count: number;
};

export type ByCategoryRow = {
  category_id: string | null;
  name: string;
  color: string;
  kind: string | null;
  gross_spending: number;
  refunds: number;
  net_spending: number;
  income: number;
  transaction_count: number;
};

export type ByCategory = { date_from: string; date_to: string; currency: string; rows: ByCategoryRow[] };

/** Which categories fit a transaction type (mirrors the server rule). */
export function categoryKindFor(txnKind: string): "expense" | "income" | null {
  if (txnKind === "expense" || txnKind === "fee" || txnKind === "refund") return "expense";
  if (txnKind === "income") return "income";
  return null;
}

// ---- Phase 5: dashboard and reports ----

export type Granularity = "day" | "week" | "month";

export type SeriesPoint = {
  date_from: string;
  date_to: string;
  income: number;
  gross_spending: number;
  refunds: number;
  net_spending: number;
  net_cash_flow: number;
  pending_out: number;
  transaction_count: number;
};

export type ReportCategoryRow = {
  category_id: string | null;
  name: string;
  color: string;
  net_spending: number;
  income: number;
  transaction_count: number;
};

export type MerchantRow = { merchant: string | null; net_spending: number; transaction_count: number };

export type Overview = {
  date_from: string;
  date_to: string;
  timezone: string;
  currency: string;
  granularity: Granularity;
  week_start: number;
  summary: CurrencySummary;
  previous: { date_from: string; date_to: string; summary: CurrencySummary };
  changes: { income: number | null; net_spending: number | null; net_cash_flow: number | null; transaction_count: number | null };
  series: SeriesPoint[];
  spending_by_category: ReportCategoryRow[];
  income_by_category: ReportCategoryRow[];
  top_merchants: MerchantRow[];
  other_merchants: MerchantRow | null;
  other_currencies: string[];
  accounts: Account[];
  balance_totals: Record<string, number>;
  balances_are_estimated: boolean;
  needs_review_count: number;
  generated_on: string;
};

// ---- Phase 6: budgets ----

export type BudgetLine = {
  id: string;
  category_id: string | null;
  name: string;
  color: string;
  archived: boolean;
  planned_minor: number;
  rollover_minor: number;
  spent_minor: number;
  available_minor: number;
  remaining_minor: number;
  percent_used: number | null;
  threshold_reached: number | null;
  over: boolean;
  projected_minor: number | null;
  projected_over: boolean;
  safe_per_day_minor: number | null;
  days_left: number;
  status: "ok" | "threshold" | "over";
};

export type Budget = {
  id: string;
  rollover_enabled: boolean;
  alert_thresholds: number[];
  thresholds_overridden: boolean;
  lines: BudgetLine[];
  overall: BudgetLine | null;
  total_planned: number;
  total_spending: number;
  budgeted_spending: number;
  unbudgeted_spending: number;
  unbudgeted: { category_id: string | null; name: string; color: string; net_spending: number }[];
  attention_count: number;
};

export type BudgetPage = {
  month: string;
  today: string;
  currency: string;
  default_thresholds: number[];
  previous_month_has_budget: boolean;
  budget: Budget | null;
};

export type BudgetSuggestions = {
  month: string;
  based_on: string[];
  suggestions: { category_id: string; name: string; color: string; amount_minor: number; months: { month: string; net_spending: number }[] }[];
};
