"""Grid + column mapping → normalised statement rows (one common schema for all adapters)."""

import hashlib
import itertools
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.ingestion.parse import parse_amount, parse_date, parse_signed

FEE_RE = re.compile(
    r"\b(sms|alert (fee|charge)|vat|stamp duty|maintenance|maint\.? fee|commission|cot|"
    r"card (fee|issuance|maintenance)|nip (charge|fee)|transfer (charge|fee)|emtl|e-levy|"
    r"electronic money transfer levy|bank charges?|service charges?|token fee|ussd charge)\b",
    re.IGNORECASE,
)
REVERSAL_RE = re.compile(r"\b(reversal|reversed|rvsl|rvsd|rev)\b", re.IGNORECASE)
REFUND_RE = re.compile(r"\b(refund|refunded|chargeback)\b", re.IGNORECASE)
NUBAN_RE = re.compile(r"(?<!\d)\d{10}(?!\d)")
PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
DEBIT_WORDS = {"DR", "D", "DEBIT", "WITHDRAWAL", "DB"}
CREDIT_WORDS = {"CR", "C", "CREDIT", "DEPOSIT", "CRT"}


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def mask_sensitive(text: str) -> str:
    """Mask card numbers and 10-digit NUBAN account numbers, keeping the last 4 digits."""

    def pan(m: re.Match[str]) -> str:
        d = re.sub(r"\D", "", m[0])
        return "•" * 4 + d[-4:] if 13 <= len(d) <= 19 and _luhn(d) else m[0]

    text = PAN_RE.sub(pan, text)
    return NUBAN_RE.sub(lambda m: "••••••" + m[0][-4:], text)


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def suggest_kind(direction: str, narration: str) -> str:
    if REVERSAL_RE.search(narration):
        return "reversal"
    if direction == "debit":
        return "fee" if FEE_RE.search(narration) else "expense"
    return "refund" if REFUND_RE.search(narration) else "income"


@dataclass
class NormRow:
    row_number: int
    transaction_date: date | None = None
    posting_date: date | None = None
    direction: str | None = None
    amount_minor: int | None = None
    narration: str | None = None
    external_ref: str | None = None
    balance_after_minor: int | None = None
    suggested_kind: str | None = None
    fingerprint: str | None = None
    error: str | None = None


@dataclass
class ParseResult:
    rows: list[NormRow] = field(default_factory=list)
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    opening_balance_minor: int | None = None
    closing_balance_minor: int | None = None
    first_date: date | None = None
    last_date: date | None = None


def _get(row: list[str], idx: int | None) -> str:
    return row[idx] if idx is not None and idx < len(row) else ""


def normalise(grid: list[list[str]], m: dict[str, Any], account_id: int) -> ParseResult:
    c = m["columns"]
    order = m["date_order"]
    mode = m["amount_mode"]
    res = ParseResult()
    seen: dict[tuple[Any, ...], int] = {}

    for i in range(m["header_row"] + 1, len(grid)):
        row = grid[i]
        if not any(row):
            continue
        n = NormRow(row_number=i + 1)
        raw_date = _get(row, c["date"])
        d = parse_date(raw_date, order)
        try:
            if mode == "debit_credit":
                dr = parse_amount(_get(row, c["debit"])) if c["debit"] is not None else None
                cr = parse_amount(_get(row, c["credit"])) if c["credit"] is not None else None
                if dr and cr:
                    raise ValueError("has both a debit and a credit amount")
                if dr:
                    n.amount_minor, n.direction = dr[0], "debit"
                elif cr:
                    n.amount_minor, n.direction = cr[0], "credit"
            else:
                a = parse_amount(_get(row, c["amount"]))
                if a:
                    n.amount_minor = a[0]
                    if mode == "signed":
                        n.direction = "debit" if a[1] else "credit"
                    else:
                        word = _get(row, c["indicator"]).strip().upper()
                        if word in DEBIT_WORDS:
                            n.direction = "debit"
                        elif word in CREDIT_WORDS:
                            n.direction = "credit"
                        else:
                            raise ValueError(f"DR/CR value '{word[:10]}' not recognised")
        except ValueError as exc:
            n.error = f"Amount {exc}."

        if n.amount_minor is None and n.error is None:
            # Opening/closing balance lines, totals, page footers: not transactions.
            res.skipped += 1
            continue
        if d is None:
            n.error = n.error or (
                f"Date '{raw_date[:20]}' not recognised." if raw_date else "Date is missing."
            )
        n.transaction_date = d
        n.posting_date = (
            parse_date(_get(row, c["posting_date"]), order)
            if c["posting_date"] is not None
            else None
        )
        if n.posting_date and d and n.posting_date < d:
            n.posting_date = d  # some banks print value date before trans date; never earlier
        narration = mask_sensitive(_get(row, c["description"]))[:500].strip()
        n.narration = narration or None
        ref = _get(row, c["reference"]).strip()[:128]
        n.external_ref = ref or None
        if c["balance"] is not None:
            try:
                n.balance_after_minor = parse_signed(_get(row, c["balance"]))
            except ValueError:
                n.balance_after_minor = None
        if n.error is None and n.direction and n.amount_minor and d:
            n.suggested_kind = suggest_kind(n.direction, narration)
            key = (d, n.direction, n.amount_minor, norm_text(narration))
            occ = seen.get(key, 0)
            seen[key] = occ + 1
            n.fingerprint = hashlib.sha256(
                f"{account_id}|{d.isoformat()}|{n.direction}|{n.amount_minor}|"
                f"{norm_text(narration)}|{occ}".encode()
            ).hexdigest()
        res.rows.append(n)

    good = [r for r in res.rows if r.error is None]
    if not good:
        if res.rows:
            res.warnings.append("No rows could be read. Check the column choices below.")
        else:
            res.warnings.append("No transactions found under the header row.")
        return res

    dates = [r.transaction_date for r in good if r.transaction_date]
    res.first_date, res.last_date = min(dates), max(dates)
    # Statements are newest-first or oldest-first; work in chronological order.
    first, last = good[0].transaction_date, good[-1].transaction_date
    chron = list(reversed(good)) if first and last and first > last else good
    _check_running_balance(chron, res)
    future = [r for r in good if r.transaction_date and r.transaction_date > date.today()]
    if future:
        res.warnings.append(f"{len(future)} row(s) are dated in the future. Check the date format.")
    return res


def _signed(r: NormRow) -> int:
    amt = r.amount_minor or 0
    return amt if r.direction == "credit" else -amt


def _bal(r: NormRow) -> int:
    return r.balance_after_minor or 0


def _check_running_balance(chron: list[NormRow], res: ParseResult) -> None:
    with_bal = [r for r in chron if r.balance_after_minor is not None]
    if len(with_bal) < 2 or len(with_bal) != len(chron):
        return
    mismatches = swapped_ok = 0
    for prev, cur in itertools.pairwise(chron):
        if _bal(prev) + _signed(cur) != _bal(cur):
            mismatches += 1
        if _bal(prev) - _signed(cur) == _bal(cur):
            swapped_ok += 1
    if mismatches == 0:
        res.opening_balance_minor = _bal(chron[0]) - _signed(chron[0])
        res.closing_balance_minor = _bal(chron[-1])
        return
    if swapped_ok == len(chron) - 1:
        res.warnings.append(
            "Money in and money out look swapped: the running balance only adds up the other "
            "way round. Swap the debit and credit columns (or the sign setting)."
        )
    else:
        res.warnings.append(
            f"The running balance doesn't add up on {mismatches} row(s). Rows on the same day "
            "may be in a different order, or a column may be wrong. The statement's closing "
            "balance won't be used for checking."
        )
