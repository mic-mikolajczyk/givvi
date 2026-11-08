"""Remove signup email verification while retaining email-change confirmation."""

from alembic import op
import sqlalchemy

revision = "0002_no_signup_verification"
down_revision = "0001_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tokens = sqlalchemy.table("account_tokens", sqlalchemy.column("purpose"))
    op.execute(tokens.delete().where(tokens.c.purpose == "verify"))
    with op.batch_alter_table("account_tokens") as batch:
        batch.drop_constraint("token_purpose", type_="check")
        batch.create_check_constraint("token_purpose", "purpose IN ('reset', 'email')")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("verified_at")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sqlalchemy.Column("verified_at", sqlalchemy.DateTime(timezone=True)))
    with op.batch_alter_table("account_tokens") as batch:
        batch.drop_constraint("token_purpose", type_="check")
        batch.create_check_constraint("token_purpose", "purpose IN ('verify', 'reset', 'email')")
