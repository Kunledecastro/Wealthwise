import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ingestion.detect import ROLES


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MappingIn(Strict):
    header_row: int = Field(ge=0, le=200)
    columns: dict[str, int | None]
    amount_mode: Literal["debit_credit", "signed", "indicator"]
    date_order: Literal["DMY", "MDY", "YMD"] = "DMY"

    @field_validator("columns")
    @classmethod
    def _roles(cls, v: dict[str, int | None]) -> dict[str, int | None]:
        unknown = set(v) - set(ROLES)
        if unknown:
            raise ValueError(f"Unknown column roles: {', '.join(sorted(unknown))}")
        for idx in v.values():
            if idx is not None and not 0 <= idx < 60:
                raise ValueError("Column numbers must be between 0 and 59.")
        used = [i for i in v.values() if i is not None]
        if len(used) != len(set(used)):
            raise ValueError("Each column can only be used once.")
        return {r: v.get(r) for r in ROLES}


class RowUpdate(Strict):
    id: uuid.UUID
    include: bool | None = None
    kind: str | None = Field(default=None, max_length=16)
    # Explicit null = leave uncategorised on purpose; omit to keep the suggestion.
    category_id: uuid.UUID | None = None


class RowUpdatesIn(Strict):
    updates: list[RowUpdate] = Field(min_length=1, max_length=5000)


class CommitIn(Strict):
    set_opening_from_statement: bool = False
    save_mapping: bool = True


class SimulateIn(Strict):
    days: int = Field(default=30, ge=1, le=120)


class ImportRowOut(BaseModel):
    id: uuid.UUID
    row_number: int
    outcome: str
    include: bool
    error: str | None
    note: str | None
    transaction_date: date | None
    posting_date: date | None
    direction: str | None
    amount_minor: int | None
    narration: str | None
    external_ref: str | None
    balance_after_minor: int | None
    suggested_kind: str | None
    kind: str | None
    allowed_kinds: list[str]
    transaction_id: uuid.UUID | None = None
    merchant_normalised: str | None = None
    category_id: uuid.UUID | None = None
    category_name: str | None = None
    category_source: str = "none"
    category_confidence: int = 0
    category_reason: str | None = None


class ImportBatchOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str
    adapter: str
    filename: str
    sheet_name: str | None
    status: str
    counts: dict[str, int]
    warnings: list[str]
    statement_first_date: date | None
    statement_last_date: date | None
    statement_opening_balance_minor: int | None
    statement_closing_balance_minor: int | None
    can_set_opening: bool
    created_at: datetime
    committed_at: datetime | None
    finished_at: datetime | None
    same_file_imported_at: datetime | None = None


class ImportDetailOut(ImportBatchOut):
    mapping: dict[str, Any] | None
    headers: list[str]
    preview: list[list[str]]
    rows: list[ImportRowOut]
    rows_total: int
    page: int
    page_size: int


class CommitOut(BaseModel):
    created: int
    transfers_linked: int
    reversals_linked: int
    opening_balance_set: bool
    reconciliation: dict[str, Any] | None
    batch: ImportBatchOut
