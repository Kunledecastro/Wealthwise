"""Phase 3: statement import (batches, rows, profiles) and reconciliation points.

Hand-reviewed. Adds: named FK on transactions.import_batch_id, 'xls' transaction source,
and app-role grants.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 17:14:12.421701
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from app.core.config import get_settings

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("adapter", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("sheet_name", sa.String(length=100), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="staged", nullable=False),
        sa.Column("grid", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("header_signature", sa.String(length=64), nullable=True),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "warnings", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "counts", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("statement_closing_balance_minor", sa.BigInteger(), nullable=True),
        sa.Column("statement_opening_balance_minor", sa.BigInteger(), nullable=True),
        sa.Column("statement_first_date", sa.Date(), nullable=True),
        sa.Column("statement_last_date", sa.Date(), nullable=True),
        sa.Column(
            "side_effects",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "adapter IN ('csv', 'xlsx', 'xls', 'simulated')", name="ck_import_adapter"
        ),
        sa.CheckConstraint(
            "status IN ('staged', 'committed', 'discarded', 'undone')", name="ck_import_status"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_import_batches_account_same_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_import_batches_user_id"), "import_batches", ["user_id"], unique=False)
    op.create_table(
        "import_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("header_signature", sa.String(length=64), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_import_profiles_account_same_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "header_signature", name="uq_import_profile_sig"),
    )
    op.create_table(
        "reconciliation_points",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("statement_balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("computed_balance_minor", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("import_batch_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source IN ('statement', 'manual')", name="ck_recon_source"),
        sa.CheckConstraint(
            "abs(statement_balance_minor) <= 1000000000000000", name="ck_recon_statement_range"
        ),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["user_id", "account_id"],
            ["accounts.user_id", "accounts.id"],
            name="fk_recon_account_same_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_recon_account_date", "reconciliation_points", ["account_id", "as_of_date"], unique=False
    )
    op.create_table(
        "import_rows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("include", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("direction", sa.String(length=6), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("narration", sa.String(length=500), nullable=True),
        sa.Column("external_ref", sa.String(length=128), nullable=True),
        sa.Column("balance_after_minor", sa.BigInteger(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("suggested_kind", sa.String(length=16), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=True),
        sa.Column("duplicate_of_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("transfer_match_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("reversal_of_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("reversal_of_row_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "outcome IN ('new', 'duplicate', 'possible_duplicate', 'error', 'skipped')",
            name="ck_import_row_outcome",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["duplicate_of_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["reversal_of_row_id"], ["import_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["reversal_of_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["transfer_match_transaction_id"], ["transactions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(op.f("ix_import_rows_batch_id"), "import_rows", ["batch_id"], unique=False)
    op.create_index(
        "ix_import_rows_batch_row", "import_rows", ["batch_id", "row_number"], unique=False
    )
    op.add_column("transactions", sa.Column("import_batch_id", sa.BigInteger(), nullable=True))
    op.create_index(
        op.f("ix_transactions_import_batch_id"), "transactions", ["import_batch_id"], unique=False
    )
    op.create_foreign_key(
        "fk_transactions_import_batch",
        "transactions",
        "import_batches",
        ["import_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("ck_txn_source", "transactions", type_="check")
    op.create_check_constraint(
        "ck_txn_source",
        "transactions",
        "source IN ('manual', 'csv', 'xlsx', 'xls', 'pdf', 'simulated', 'email', 'open_banking')",
    )

    role = make_url(get_settings().database_url).username
    if not role or not role.replace("_", "").isalnum():
        raise RuntimeError("DATABASE_URL must contain a simple role name")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON import_batches, import_rows, import_profiles "
        f'TO "{role}"'
    )
    # Reconciliation points are a record of what the statement said: insert/read only
    # (DELETE kept so account deletion can cascade).
    op.execute(f'GRANT SELECT, INSERT, DELETE ON reconciliation_points TO "{role}"')
    op.execute(f'REVOKE UPDATE, TRUNCATE ON reconciliation_points FROM "{role}"')
    op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"')


def downgrade() -> None:
    # WARNING: constraint name is None; this directive will fail as
    # rendered.  Add a name, or use a naming convention; see
    # https://alembic.sqlalchemy.org/en/latest/naming.html
    op.execute("UPDATE transactions SET source = 'xlsx' WHERE source = 'xls'")
    op.drop_constraint("ck_txn_source", "transactions", type_="check")
    op.create_check_constraint(
        "ck_txn_source",
        "transactions",
        "source IN ('manual', 'csv', 'xlsx', 'pdf', 'simulated', 'email', 'open_banking')",
    )
    op.drop_constraint("fk_transactions_import_batch", "transactions", type_="foreignkey")
    op.drop_index(op.f("ix_transactions_import_batch_id"), table_name="transactions")
    op.drop_column("transactions", "import_batch_id")
    op.drop_index("ix_import_rows_batch_row", table_name="import_rows")
    op.drop_index(op.f("ix_import_rows_batch_id"), table_name="import_rows")
    op.drop_table("import_rows")
    op.drop_index("ix_recon_account_date", table_name="reconciliation_points")
    op.drop_table("reconciliation_points")
    op.drop_table("import_profiles")
    op.drop_index(op.f("ix_import_batches_user_id"), table_name="import_batches")
    op.drop_table("import_batches")
