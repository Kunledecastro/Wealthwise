"""Phase 1 tables: identity, sessions, invites, preferences, rate limiting, audit, currencies.

Conventions (docs/DATABASE.md): BIGINT identity PKs kept internal, UUID public ids exposed,
TIMESTAMPTZ in UTC, every user-owned row carries user_id.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utcnow, nullable=False
    )


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    exponent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (CheckConstraint("exponent BETWEEN 0 AND 4", name="ck_currency_exponent"),)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="member")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    preferences: Mapped["UserPreferences"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'member')", name="ck_users_role"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
    )


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    currency: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False, server_default="NGN"
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Africa/Lagos")
    week_start: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    budget_alert_thresholds: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default="{70,90,100}"
    )
    notify_in_app: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    external_ai_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="preferences")

    __table_args__ = (CheckConstraint("week_start BETWEEN 1 AND 7", name="ck_prefs_week_start"),)


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(256))


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT)
    note: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    identifier_hash: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(INET)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_auth_attempts_ident", "kind", "identifier_hash", "created_at"),
        Index("ix_auth_attempts_ip", "kind", "ip", "created_at"),
    )


class AuditEvent(Base):
    """Append-only. The app database role has no UPDATE/DELETE on this table."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(INET)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Phase 2: accounts, transactions, revisions
# Money: positive BIGINT minor units + direction + currency (docs/DATABASE.md, D-004).
# ---------------------------------------------------------------------------

ACCOUNT_TYPES = ("bank", "wallet", "cash", "savings", "card", "loan")
ACCOUNT_SOURCES = ("manual", "imported", "simulated", "connected")
TXN_KINDS = ("income", "expense", "fee", "refund", "transfer", "reversal", "adjustment")
TXN_STATUSES = ("pending", "posted", "failed", "reversed")
CATEGORY_SOURCES = ("none", "user", "rule", "system", "linked", "ai")
TXN_SOURCES = ("manual", "csv", "xlsx", "xls", "pdf", "simulated", "email", "open_banking")
MAX_MINOR = 10**15  # ₦10 trillion in kobo; well inside JSON's safe-integer range


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(80))
    mask: Mapped[str | None] = mapped_column(String(4))
    currency: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), nullable=False)
    opening_balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opening_balance_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="manual")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_accounts_user_id_id"),
        CheckConstraint(_in("type", ACCOUNT_TYPES), name="ck_accounts_type"),
        CheckConstraint(_in("source", ACCOUNT_SOURCES), name="ck_accounts_source"),
        CheckConstraint("mask IS NULL OR mask ~ '^[0-9]{4}$'", name="ck_accounts_mask"),
        CheckConstraint(
            f"abs(opening_balance_minor) <= {MAX_MINOR}", name="ck_accounts_opening_range"
        ),
    )


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(6), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    posting_date: Mapped[date | None] = mapped_column(Date)
    merchant: Mapped[str | None] = mapped_column(String(120))
    narration: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="manual")
    external_ref: Mapped[str | None] = mapped_column(String(128))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reverses_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    refund_of_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    import_batch_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("import_batches.id", ondelete="SET NULL", name="fk_transactions_import_batch"),
        index=True,
    )
    merchant_normalised: Mapped[str | None] = mapped_column(String(120))
    category_id: Mapped[int | None] = mapped_column(BigInteger)
    category_source: Mapped[str] = mapped_column(String(8), nullable=False, server_default="none")
    category_confidence: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    category_reason: Mapped[str | None] = mapped_column(String(200))
    category_rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("category_rules.id", ondelete="SET NULL", name="fk_txn_category_rule"),
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (
        # The account must belong to the same user as the transaction.
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_transactions_account_same_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "category_id"],
            ["categories.user_id", "categories.id"],
            name="fk_transactions_category_same_user",
        ),
        CheckConstraint(_in("category_source", CATEGORY_SOURCES), name="ck_txn_category_source"),
        CheckConstraint("category_confidence BETWEEN 0 AND 100", name="ck_txn_category_confidence"),
        Index("ix_txn_user_review", "user_id", "needs_review"),
        Index("ix_txn_category", "category_id"),
        CheckConstraint(_in("kind", TXN_KINDS), name="ck_txn_kind"),
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_txn_direction"),
        CheckConstraint(_in("status", TXN_STATUSES), name="ck_txn_status"),
        CheckConstraint(_in("source", TXN_SOURCES), name="ck_txn_source"),
        CheckConstraint(
            f"amount_minor > 0 AND amount_minor <= {MAX_MINOR}", name="ck_txn_amount_range"
        ),
        # Kind/direction pairs that are always fixed.
        CheckConstraint(
            "(kind IN ('income', 'refund') AND direction = 'credit')"
            " OR (kind IN ('expense', 'fee') AND direction = 'debit')"
            " OR kind IN ('transfer', 'reversal', 'adjustment')",
            name="ck_txn_kind_direction",
        ),
        CheckConstraint(
            "(kind = 'transfer') = (transfer_group_id IS NOT NULL)", name="ck_txn_transfer_group"
        ),
        CheckConstraint(
            "(kind = 'reversal') = (reverses_transaction_id IS NOT NULL)",
            name="ck_txn_reversal_link",
        ),
        CheckConstraint(
            "refund_of_transaction_id IS NULL OR kind = 'refund'", name="ck_txn_refund_link"
        ),
        Index("ix_txn_user_date", "user_id", "transaction_date", "id"),
        Index("ix_txn_account", "account_id"),
        Index("ix_txn_transfer_group", "transfer_group_id"),
        Index(
            "uq_txn_account_external_ref",
            "account_id",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
        Index(
            "uq_txn_account_fingerprint",
            "account_id",
            "fingerprint",
            unique=True,
            postgresql_where=text("fingerprint IS NOT NULL"),
        ),
    )


class TransactionRevision(Base):
    """One row per create/update/delete/reverse of a transaction, written in the same DB
    transaction as the change itself."""

    __tablename__ = "transaction_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete', 'reverse')", name="ck_rev_action"
        ),
    )


# ---------------------------------------------------------------------------
# Phase 3: statement import and reconciliation
# ---------------------------------------------------------------------------

IMPORT_ADAPTERS = ("csv", "xlsx", "xls", "simulated")
IMPORT_STATUSES = ("staged", "committed", "discarded", "undone")
ROW_OUTCOMES = ("new", "duplicate", "possible_duplicate", "error", "skipped")


class ImportProfile(TimestampMixin, Base):
    """Remembered column mapping for an account, keyed by the file's header signature."""

    __tablename__ = "import_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    header_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_import_profiles_account_same_user",
            ondelete="CASCADE",
        ),
        UniqueConstraint("account_id", "header_signature", name="uq_import_profile_sig"),
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adapter: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(100))
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="staged")
    # Raw cell grid, kept only while staged so the column mapping can be changed.
    # Cleared on commit or discard (the original file itself is never stored).
    grid: Mapped[list[list[str]] | None] = mapped_column(JSONB(none_as_null=True))
    header_signature: Mapped[str | None] = mapped_column(String(64))
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, server_default="{}")
    statement_closing_balance_minor: Mapped[int | None] = mapped_column(BigInteger)
    statement_opening_balance_minor: Mapped[int | None] = mapped_column(BigInteger)
    statement_first_date: Mapped[date | None] = mapped_column(Date)
    statement_last_date: Mapped[date | None] = mapped_column(Date)
    # What commit changed outside its own new rows, so undo can put it back exactly.
    side_effects: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_import_batches_account_same_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("adapter", IMPORT_ADAPTERS), name="ck_import_adapter"),
        CheckConstraint(_in("status", IMPORT_STATUSES), name="ck_import_status"),
    )


class ImportRow(Base):
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based, as in the file
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    include: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(String(300))
    transaction_date: Mapped[date | None] = mapped_column(Date)
    posting_date: Mapped[date | None] = mapped_column(Date)
    direction: Mapped[str | None] = mapped_column(String(6))
    amount_minor: Mapped[int | None] = mapped_column(BigInteger)
    narration: Mapped[str | None] = mapped_column(String(500))
    external_ref: Mapped[str | None] = mapped_column(String(128))
    balance_after_minor: Mapped[int | None] = mapped_column(BigInteger)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    suggested_kind: Mapped[str | None] = mapped_column(String(16))
    kind: Mapped[str | None] = mapped_column(String(16))
    duplicate_of_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    transfer_match_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    reversal_of_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    reversal_of_row_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("import_rows.id", ondelete="SET NULL")
    )
    transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    merchant_normalised: Mapped[str | None] = mapped_column(String(120))
    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="SET NULL", name="fk_import_rows_category")
    )
    category_source: Mapped[str] = mapped_column(String(8), nullable=False, server_default="none")
    category_confidence: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )
    category_reason: Mapped[str | None] = mapped_column(String(200))
    category_rule_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("category_rules.id", ondelete="SET NULL", name="fk_import_rows_rule"),
    )

    __table_args__ = (
        CheckConstraint(_in("outcome", ROW_OUTCOMES), name="ck_import_row_outcome"),
        Index("ix_import_rows_batch_row", "batch_id", "row_number"),
    )


class ReconciliationPoint(Base):
    __tablename__ = "reconciliation_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    statement_balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    computed_balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    import_batch_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_recon_account_same_user",
            ondelete="CASCADE",
        ),
        CheckConstraint("source IN ('statement', 'manual')", name="ck_recon_source"),
        CheckConstraint(
            f"abs(statement_balance_minor) <= {MAX_MINOR}", name="ck_recon_statement_range"
        ),
        Index("ix_recon_account_date", "account_id", "as_of_date"),
    )


# ---------------------------------------------------------------------------
# Phase 4: categories and rules
# ---------------------------------------------------------------------------

CATEGORY_KINDS = ("expense", "income", "transfer")
RULE_MATCH_TYPES = ("contains", "starts_with", "equals")


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(CITEXT, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, server_default="#94a3b8")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_categories_user_id_id"),
        UniqueConstraint("user_id", "name", name="uq_categories_user_name"),
        Index(
            "uq_categories_user_slug",
            "user_id",
            "slug",
            unique=True,
            postgresql_where=text("slug IS NOT NULL"),
        ),
        CheckConstraint(_in("kind", CATEGORY_KINDS), name="ck_category_kind"),
        CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="ck_category_color"),
        CheckConstraint("length(name) BETWEEN 1 AND 60", name="ck_category_name_len"),
    )


class CategoryRule(TimestampMixin, Base):
    """User rule: when a transaction's text matches `pattern`, use `category_id`."""

    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    match_type: Mapped[str] = mapped_column(String(12), nullable=False)
    pattern: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(6))
    account_id: Mapped[int | None] = mapped_column(BigInteger)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    created_from: Mapped[str] = mapped_column(String(16), nullable=False, server_default="manual")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "category_id"],
            ["categories.user_id", "categories.id"],
            name="fk_rules_category_same_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_rules_account_same_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(_in("match_type", RULE_MATCH_TYPES), name="ck_rule_match_type"),
        CheckConstraint(
            "direction IS NULL OR direction IN ('debit', 'credit')", name="ck_rule_dir"
        ),
        CheckConstraint(
            "created_from IN ('manual', 'user_correction')", name="ck_rule_created_from"
        ),
        CheckConstraint("length(pattern) BETWEEN 2 AND 100", name="ck_rule_pattern_len"),
    )


class Budget(TimestampMixin, Base):
    """A monthly budget (Phase 6). Figures are always computed live by app.ledger.engine."""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)  # always the 1st
    currency: Mapped[str] = mapped_column(
        String(3), ForeignKey("currencies.code"), nullable=False, server_default="NGN"
    )
    rollover_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    alert_thresholds: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))

    lines: Mapped[list["BudgetLine"]] = relationship(
        back_populates="budget", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "month", "currency", name="uq_budgets_user_month"),
        UniqueConstraint("user_id", "id", name="uq_budgets_user_id_id"),
        CheckConstraint("extract(day from month) = 1", name="ck_budget_month_first"),
        CheckConstraint(
            "alert_thresholds IS NULL OR (cardinality(alert_thresholds) BETWEEN 1 AND 5 "
            "AND 1 <= ALL(alert_thresholds) AND 200 >= ALL(alert_thresholds))",
            name="ck_budget_thresholds",
        ),
    )


class BudgetLine(TimestampMixin, Base):
    """Planned spending for one category (NULL category = the overall limit)."""

    __tablename__ = "budget_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    budget_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    planned_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    budget: Mapped[Budget] = relationship(back_populates="lines")

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "budget_id"],
            ["budgets.user_id", "budgets.id"],
            name="fk_budget_lines_budget_same_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "category_id"],
            ["categories.user_id", "categories.id"],
            name="fk_budget_lines_category_same_user",
            ondelete="CASCADE",  # only reachable when the whole user is deleted
        ),
        Index(
            "uq_budget_lines_budget_category",
            "budget_id",
            "category_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "planned_minor > 0 AND planned_minor <= 1000000000000000", name="ck_budget_line_amount"
        ),
    )
