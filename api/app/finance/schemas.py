import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import MAX_MINOR

AccountType = Literal["bank", "wallet", "cash", "savings", "card", "loan"]
EntryKind = Literal["income", "expense", "fee", "refund", "adjustment"]
EditableStatus = Literal["pending", "posted", "failed"]
Direction = Literal["debit", "credit"]

MIN_DATE = date(1970, 1, 1)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------- accounts ----------------


class AccountIn(Strict):
    type: AccountType
    display_name: str = Field(min_length=1, max_length=80)
    institution_name: str | None = Field(default=None, max_length=80)
    mask: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    opening_balance_minor: int = Field(ge=-MAX_MINOR, le=MAX_MINOR, strict=True)
    opening_balance_date: date

    @field_validator("institution_name", "mask", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        return v or None if isinstance(v, str) else v

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class AccountPatch(Strict):
    type: AccountType | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    institution_name: str | None = Field(default=None, max_length=80)
    mask: str | None = Field(default=None, pattern=r"^[0-9]{4}$|^$")
    opening_balance_minor: int | None = Field(
        default=None, ge=-MAX_MINOR, le=MAX_MINOR, strict=True
    )
    opening_balance_date: date | None = None
    is_archived: bool | None = None


class BalanceOut(BaseModel):
    posted_minor: int
    pending_in: int
    pending_out: int
    available_incl_pending: int
    status: Literal["estimated", "reconciled", "stale"]
    as_of: date


class AccountOut(BaseModel):
    id: uuid.UUID
    type: str
    display_name: str
    institution_name: str | None
    mask: str | None
    currency: str
    opening_balance_minor: int
    opening_balance_date: date
    source: str
    is_archived: bool
    created_at: datetime
    transaction_count: int
    balance: BalanceOut


# ---------------- transactions ----------------


class _TxnCommon(Strict):
    amount_minor: int = Field(gt=0, le=MAX_MINOR, strict=True)
    status: EditableStatus = "posted"
    transaction_date: date
    posting_date: date | None = None
    narration: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dates(self) -> "_TxnCommon":
        if self.transaction_date < MIN_DATE:
            raise ValueError("Transaction date is too far in the past.")
        if self.posting_date and self.posting_date < self.transaction_date:
            raise ValueError("Posting date cannot be before the transaction date.")
        return self


class TransactionIn(_TxnCommon):
    account_id: uuid.UUID
    kind: EntryKind
    direction: Direction | None = None  # only for adjustments
    merchant: str | None = Field(default=None, max_length=120)
    refund_of_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _direction(self) -> "TransactionIn":
        if self.kind == "adjustment" and self.direction is None:
            raise ValueError("Choose whether the adjustment adds or removes money.")
        if self.kind != "adjustment" and self.direction is not None:
            raise ValueError("Direction is set automatically for this type.")
        if self.refund_of_id is not None and self.kind != "refund":
            raise ValueError("Only refunds can be linked to an original purchase.")
        return self


class TransferIn(_TxnCommon):
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID

    @model_validator(mode="after")
    def _different(self) -> "TransferIn":
        if self.from_account_id == self.to_account_id:
            raise ValueError("Choose two different accounts.")
        return self


class TransactionPatch(Strict):
    account_id: uuid.UUID | None = None
    kind: EntryKind | None = None
    direction: Direction | None = None
    amount_minor: int | None = Field(default=None, gt=0, le=MAX_MINOR, strict=True)
    status: EditableStatus | None = None
    transaction_date: date | None = None
    posting_date: date | None = None
    merchant: str | None = Field(default=None, max_length=120)
    narration: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=200)


class ReverseIn(Strict):
    reversal_date: date | None = None
    reason: str | None = Field(default=None, max_length=200)


class DeleteIn(Strict):
    reason: str | None = Field(default=None, max_length=200)


class TransactionOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str
    kind: str
    direction: str
    amount_minor: int
    currency: str
    status: str
    transaction_date: date
    posting_date: date | None
    merchant: str | None
    narration: str | None
    notes: str | None
    source: str
    transfer_group_id: uuid.UUID | None
    counterpart_account_id: uuid.UUID | None = None
    counterpart_account_name: str | None = None
    reverses_id: uuid.UUID | None = None
    reversed_by_id: uuid.UUID | None = None
    refund_of_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class RevisionOut(BaseModel):
    action: str
    changes: dict[str, Any]
    reason: str | None
    created_at: datetime


class TransactionDetailOut(TransactionOut):
    revisions: list[RevisionOut]


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class TransferOut(BaseModel):
    transfer_group_id: uuid.UUID
    debit: TransactionOut
    credit: TransactionOut


# ---------------- summary ----------------


class CurrencySummaryOut(BaseModel):
    currency: str
    income: int
    gross_spending: int
    fees: int
    refunds: int
    net_spending: int
    net_cash_flow: int
    pending_in: int
    pending_out: int
    transaction_count: int


class SummaryOut(BaseModel):
    date_from: date
    date_to: date
    timezone: str
    summaries: list[CurrencySummaryOut]
    accounts: list[AccountOut]
    balance_totals: dict[str, int]
    balances_are_estimated: bool
