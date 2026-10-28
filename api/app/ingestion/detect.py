"""Find the header row and guess which column is which.

Statements often start with a few lines of account details before the table, so we scan
the first rows and pick the one that looks most like a header.
"""

import hashlib
import re
from typing import Any

from app.ingestion.parse import guess_date_order

ROLES = (
    "date",
    "posting_date",
    "description",
    "debit",
    "credit",
    "amount",
    "indicator",
    "balance",
    "reference",
)

# Normalised header text → role. Matched exactly first, then by containment.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "date": (
        "trans date",
        "transaction date",
        "tran date",
        "txn date",
        "trans. date",
        "date",
        "booking date",
        "posted date",
        "post date",
        "entry date",
        "transaction time",
        "date/time",
        "date time",
    ),
    "posting_date": ("value date", "posting date", "effective date", "val date", "value dt"),
    "description": (
        "narration",
        "description",
        "details",
        "transaction details",
        "remarks",
        "particulars",
        "memo",
        "narrative",
        "transaction description",
        "transaction narration",
        "beneficiary",
        "note",
    ),
    "debit": (
        "debit",
        "debits",
        "withdrawal",
        "withdrawals",
        "money out",
        "debit amount",
        "amount debited",
        "paid out",
        "dr amount",
        "outflow",
        "dr",
    ),
    "credit": (
        "credit",
        "credits",
        "deposit",
        "deposits",
        "lodgement",
        "lodgements",
        "lodgment",
        "money in",
        "credit amount",
        "amount credited",
        "paid in",
        "cr amount",
        "inflow",
        "cr",
    ),
    "amount": ("amount", "transaction amount", "amt", "amount (ngn)", "amount(ngn)", "value"),
    "indicator": (
        "dr/cr",
        "cr/dr",
        "d/c",
        "dr / cr",
        "debit/credit",
        "credit/debit",
        "transaction type",
        "type",
        "direction",
    ),
    "balance": (
        "balance",
        "running balance",
        "closing balance",
        "available balance",
        "bal",
        "balance after",
        "ledger balance",
        "book balance",
        "balance (ngn)",
    ),
    "reference": (
        "reference",
        "ref",
        "reference number",
        "transaction reference",
        "ref no",
        "ref. no",
        "session id",
        "transaction id",
        "tran id",
        "txn id",
        "ref number",
        "cheque no",
        "chq no",
        "receipt no",
    ),
}


def norm(h: str) -> str:
    h = h.lower().replace("\n", " ").replace("_", " ")
    h = re.sub(r"[^a-z0-9/().& ]+", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def role_for(header: str) -> str | None:
    h = norm(header)
    if not h:
        return None
    for role, words in SYNONYMS.items():
        if h in words:
            return role
    for role in (
        "posting_date",
        "balance",
        "description",
        "reference",
        "debit",
        "credit",
        "date",
        "indicator",
        "amount",
    ):
        for w in SYNONYMS[role]:
            if len(w) >= 4 and re.search(rf"\b{re.escape(w)}\b", h):
                return role
    return None


def header_score(row: list[str]) -> int:
    roles = {role_for(c) for c in row if c}
    roles.discard(None)
    score = len(roles)
    if "date" in roles and ({"debit", "credit"} & roles or "amount" in roles):
        score += 5
    return score


def find_header_row(grid: list[list[str]], scan: int = 40) -> int | None:
    best, best_i = 0, None
    for i, row in enumerate(grid[:scan]):
        sc = header_score(row)
        if sc > best:
            best, best_i = sc, i
    return best_i if best >= 6 else None


def header_signature(headers: list[str]) -> str:
    return hashlib.sha256("|".join(norm(h) for h in headers).encode()).hexdigest()


def guess_mapping(grid: list[list[str]]) -> dict[str, Any]:
    hi = find_header_row(grid)
    if hi is None:
        return {
            "header_row": None,
            "columns": dict.fromkeys(ROLES),
            "amount_mode": None,
            "date_order": "DMY",
        }
    headers = grid[hi]
    cols: dict[str, int | None] = dict.fromkeys(ROLES)
    for idx, h in enumerate(headers):
        r = role_for(h)
        if r and cols[r] is None:
            cols[r] = idx
        elif r == "date" and cols["date"] is not None and cols["posting_date"] is None:
            cols["posting_date"] = idx
    # "Type" columns are only DR/CR indicators if their values look like it.
    body = [r for r in grid[hi + 1 : hi + 200] if any(r)]
    if cols["indicator"] is not None:
        vals = {
            (r[cols["indicator"]] if cols["indicator"] < len(r) else "").strip().upper()
            for r in body
        }
        vals.discard("")
        if not vals or not vals <= {
            "DR",
            "CR",
            "D",
            "C",
            "DEBIT",
            "CREDIT",
            "WITHDRAWAL",
            "DEPOSIT",
            "DB",
            "CRT",
        }:
            cols["indicator"] = None
    if cols["debit"] is not None or cols["credit"] is not None:
        mode = "debit_credit"
    elif cols["amount"] is not None and cols["indicator"] is not None:
        mode = "indicator"
    elif cols["amount"] is not None:
        mode = "signed"
    else:
        mode = None
    order = "DMY"
    if cols["date"] is not None:
        samples = [r[cols["date"]] for r in body if cols["date"] < len(r)]
        order = guess_date_order(samples)
    return {"header_row": hi, "columns": cols, "amount_mode": mode, "date_order": order}


def validate_mapping(m: dict[str, Any], ncols: int) -> list[str]:
    """Problems that stop parsing; returned as user-facing messages."""
    problems = []
    cols = m.get("columns") or {}
    if m.get("header_row") is None:
        problems.append("Choose the row that contains the column headings.")
    if cols.get("date") is None:
        problems.append("Choose the date column.")
    mode = m.get("amount_mode")
    if mode == "debit_credit" and cols.get("debit") is None and cols.get("credit") is None:
        problems.append("Choose the debit and/or credit columns.")
    if mode in ("signed", "indicator") and cols.get("amount") is None:
        problems.append("Choose the amount column.")
    if mode == "indicator" and cols.get("indicator") is None:
        problems.append("Choose the DR/CR column.")
    if mode not in ("debit_credit", "signed", "indicator"):
        problems.append("Choose how amounts are shown.")
    for role, idx in cols.items():
        if idx is not None and not (0 <= idx < ncols):
            problems.append(f"The {role.replace('_', ' ')} column doesn't exist.")
    if m.get("date_order") not in ("DMY", "MDY", "YMD"):
        problems.append("Choose the date format.")
    return problems
