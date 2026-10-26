"""Ledger engine: pure, deterministic money calculations (see RULES.md).

No database access, no floats. Callers load rows, convert them to `Entry`, and call these
functions. Keeping this pure makes every rule unit-testable in isolation.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

INCOME_KINDS = frozenset({"income"})
SPEND_KINDS = frozenset({"expense", "fee"})
REFUND_KINDS = frozenset({"refund"})
NON_PNL_KINDS = frozenset({"transfer", "adjustment"})


@dataclass(frozen=True, slots=True)
class Entry:
    kind: str
    direction: str  # "debit" | "credit"
    amount_minor: int
    currency: str
    status: str  # "pending" | "posted" | "failed" | "reversed"
    transaction_date: date
    account_id: int = 0
    deleted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise TypeError("amount_minor must be an int (minor units)")
        if self.amount_minor <= 0:
            raise ValueError("amount_minor must be positive; direction carries the sign")
        if self.direction not in ("debit", "credit"):
            raise ValueError(f"invalid direction {self.direction!r}")

    @property
    def signed(self) -> int:
        return self.amount_minor if self.direction == "credit" else -self.amount_minor


def is_live(e: Entry) -> bool:
    """R3, R4, R5: failed, deleted, reversed originals and reversal rows count nowhere."""
    return not e.deleted and e.status in ("posted", "pending") and e.kind != "reversal"


def in_period(e: Entry, date_from: date | None, date_to: date | None) -> bool:
    """R12: inclusive on both ends."""
    if date_from is not None and e.transaction_date < date_from:
        return False
    return not (date_to is not None and e.transaction_date > date_to)


@dataclass(slots=True)
class Summary:
    currency: str
    income: int = 0
    gross_spending: int = 0
    fees: int = 0
    refunds: int = 0
    pending_in: int = 0
    pending_out: int = 0
    transaction_count: int = 0

    @property
    def net_spending(self) -> int:
        return self.gross_spending - self.refunds  # R8

    @property
    def net_cash_flow(self) -> int:
        return self.income - self.net_spending  # R11

    def as_dict(self) -> dict[str, int | str]:
        return {
            "currency": self.currency,
            "income": self.income,
            "gross_spending": self.gross_spending,
            "fees": self.fees,
            "refunds": self.refunds,
            "net_spending": self.net_spending,
            "net_cash_flow": self.net_cash_flow,
            "pending_in": self.pending_in,
            "pending_out": self.pending_out,
            "transaction_count": self.transaction_count,
        }


def summarize(
    entries: Iterable[Entry], date_from: date | None = None, date_to: date | None = None
) -> dict[str, Summary]:
    """Income/spending summary per currency for a period (R1-R12)."""
    out: dict[str, Summary] = {}
    for e in entries:
        if not is_live(e) or not in_period(e, date_from, date_to):
            continue
        s = out.setdefault(e.currency, Summary(currency=e.currency))
        if e.kind in NON_PNL_KINDS:  # R9, R10
            continue
        if e.status == "pending":  # R2
            if e.direction == "credit":
                s.pending_in += e.amount_minor
            else:
                s.pending_out += e.amount_minor
            continue
        s.transaction_count += 1
        if e.kind in INCOME_KINDS:  # R6
            s.income += e.amount_minor
        elif e.kind in SPEND_KINDS:  # R7
            s.gross_spending += e.amount_minor
            if e.kind == "fee":
                s.fees += e.amount_minor
        elif e.kind in REFUND_KINDS:  # R8
            s.refunds += e.amount_minor
        else:
            raise ValueError(f"unknown transaction kind {e.kind!r}")
    return out


@dataclass(frozen=True, slots=True)
class Balance:
    currency: str
    opening_minor: int
    posted_minor: int  # B1
    pending_in: int
    pending_out: int

    @property
    def available_incl_pending(self) -> int:  # B3
        return self.posted_minor + self.pending_in - self.pending_out


def account_balance(
    *,
    currency: str,
    opening_minor: int,
    opening_date: date,
    entries: Iterable[Entry],
    as_of: date | None = None,
) -> Balance:
    """Balance of one account (B1-B3). `entries` must all belong to that account."""
    posted = opening_minor
    p_in = p_out = 0
    for e in entries:
        if e.currency != currency:
            raise ValueError("entry currency differs from account currency")
        if not is_live(e) or e.transaction_date < opening_date:
            continue
        if as_of is not None and e.transaction_date > as_of:
            continue
        if e.status == "posted":
            posted += e.signed
        elif e.direction == "credit":
            p_in += e.amount_minor
        else:
            p_out += e.amount_minor
    return Balance(
        currency=currency,
        opening_minor=opening_minor,
        posted_minor=posted,
        pending_in=p_in,
        pending_out=p_out,
    )


def total_balances(balances: Iterable[Balance]) -> dict[str, int]:
    """Sum account balances per currency. Never adds different currencies together."""
    out: dict[str, int] = defaultdict(int)
    for b in balances:
        out[b.currency] += b.posted_minor
    return dict(out)
