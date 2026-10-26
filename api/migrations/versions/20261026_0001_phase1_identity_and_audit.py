"""Phase 1: identity, sessions, invites, preferences, rate limiting, audit, currencies.

Hand-reviewed (not blind autogenerate). Adds: citext extension, NGN seed,
privilege grants for the app role, and append-only audit_events.

Revision ID: 0001
Revises:
Create Date: 2026-10-26 20:34:39.018188
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from app.core.config import get_settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _app_role() -> str:
    role = make_url(get_settings().database_url).username
    if not role or not role.replace("_", "").isalnum():
        raise RuntimeError("DATABASE_URL must contain a simple role name")
    return role


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)
    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("identifier_hash", sa.String(length=64), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_attempts_ident",
        "auth_attempts",
        ["kind", "identifier_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_attempts_ip", "auth_attempts", ["kind", "ip", "created_at"], unique=False
    )
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=False),
        sa.Column("exponent", sa.SmallInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint("exponent BETWEEN 0 AND 4", name="ck_currency_exponent"),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="member", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_users_role"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_users_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_table(
        "invites",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("note", sa.String(length=120), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.BigInteger(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"), "password_reset_tokens", ["user_id"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="NGN", nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="Africa/Lagos", nullable=False),
        sa.Column("week_start", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "budget_alert_thresholds",
            sa.ARRAY(sa.Integer()),
            server_default="{70,90,100}",
            nullable=False,
        ),
        sa.Column("notify_in_app", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("notify_email", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ai_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("external_ai_consent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("week_start BETWEEN 1 AND 7", name="ck_prefs_week_start"),
        sa.ForeignKeyConstraint(
            ["currency"],
            ["currencies.code"],
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.execute(
        "INSERT INTO currencies (code, name, symbol, exponent) VALUES "
        "('NGN', 'Nigerian naira', '₦', 2)"
    )

    role = _app_role()
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"')
    op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"')
    # Audit trail is append-only for the application.
    op.execute(f'REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM "{role}"')
    # Reference data is read-only for the application.
    op.execute(f'REVOKE INSERT, UPDATE, DELETE ON currencies FROM "{role}"')
    op.execute(f'REVOKE ALL ON alembic_version FROM "{role}"')


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("invites")
    op.drop_table("users")
    op.drop_table("currencies")
    op.drop_index("ix_auth_attempts_ip", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_ident", table_name="auth_attempts")
    op.drop_table("auth_attempts")
    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_table("audit_events")
