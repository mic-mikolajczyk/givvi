"""Create accounts, sessions, tokens, wishlist ownership, and delivery state."""

from alembic import op
import sqlalchemy

revision = "0001_accounts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sqlalchemy.Column("id", sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column("name", sqlalchemy.String(120), nullable=False),
        sqlalchemy.Column("email", sqlalchemy.String(254), nullable=False, unique=True),
        sqlalchemy.Column("password_hash", sqlalchemy.String(512), nullable=False),
        sqlalchemy.Column("language", sqlalchemy.String(2), nullable=False),
        sqlalchemy.Column("verified_at", sqlalchemy.DateTime(timezone=True)),
        sqlalchemy.Column("pending_email", sqlalchemy.String(254), unique=True),
        sqlalchemy.CheckConstraint("language IN ('en', 'pl')", name="user_language")
    )
    op.create_table("wishlists", sqlalchemy.Column("user_id", sqlalchemy.String(
        36), sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True))
    op.create_table(
        "login_sessions",
        sqlalchemy.Column("id", sqlalchemy.String(64), primary_key=True),
        sqlalchemy.Column("user_id", sqlalchemy.String(36), sqlalchemy.ForeignKey("users.id", ondelete="CASCADE")),
        sqlalchemy.Column("csrf_digest", sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column("expires_at", sqlalchemy.DateTime(timezone=True), nullable=False)
    )
    op.create_table(
        "account_tokens",
        sqlalchemy.Column("id", sqlalchemy.String(64), primary_key=True),
        sqlalchemy.Column("user_id", sqlalchemy.String(36), sqlalchemy.ForeignKey(
            "users.id", ondelete="CASCADE"), nullable=False),
        sqlalchemy.Column("purpose", sqlalchemy.String(10), nullable=False),
        sqlalchemy.Column("target_email", sqlalchemy.String(254)),
        sqlalchemy.Column("expires_at", sqlalchemy.DateTime(timezone=True), nullable=False),
        sqlalchemy.CheckConstraint("purpose IN ('verify', 'reset', 'email')", name="token_purpose")
    )
    op.create_table(
        "email_outbox",
        sqlalchemy.Column("id", sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column("user_id", sqlalchemy.String(36), sqlalchemy.ForeignKey("users.id", ondelete="CASCADE")),
        sqlalchemy.Column("payload", sqlalchemy.Text()),
        sqlalchemy.Column("available_at", sqlalchemy.DateTime(timezone=True), nullable=False),
        sqlalchemy.Column("expires_at", sqlalchemy.DateTime(timezone=True), nullable=False),
        sqlalchemy.Column("attempts", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column("lease_id", sqlalchemy.String(36)),
        sqlalchemy.Column("lease_until", sqlalchemy.DateTime(timezone=True)),
        sqlalchemy.Column("delivered_at", sqlalchemy.DateTime(timezone=True)),
        sqlalchemy.Column("failed_at", sqlalchemy.DateTime(timezone=True))
    )
    op.create_table(
        "rate_buckets",
        sqlalchemy.Column("id", sqlalchemy.String(64), primary_key=True),
        sqlalchemy.Column("count", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.Column("expires_at", sqlalchemy.DateTime(timezone=True), nullable=False)
    )
    for table, columns in {
        "login_sessions": ["user_id", "expires_at"], "account_tokens": ["user_id", "expires_at"],
        "email_outbox": ["user_id", "available_at"], "rate_buckets": ["expires_at"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ("rate_buckets", "email_outbox", "account_tokens", "login_sessions", "wishlists", "users"):
        op.drop_table(table)
