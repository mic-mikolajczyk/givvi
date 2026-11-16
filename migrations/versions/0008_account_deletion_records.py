"""Retain minimal account deletion records for backup restoration."""

from alembic import op
import sqlalchemy

revision = "0008_account_deletion_records"
down_revision = "0007_nullable_event_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_records",
        sqlalchemy.Column("user_id", sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column("deleted_at", sqlalchemy.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_deletion_records")
