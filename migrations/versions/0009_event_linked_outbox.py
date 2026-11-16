"""Associate invitation messages with their event."""

from alembic import op
import sqlalchemy

revision = "0009_event_linked_outbox"
down_revision = "0008_account_deletion_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("email_outbox") as batch_op:
            batch_op.add_column(sqlalchemy.Column("event_id", sqlalchemy.String(36)))
            batch_op.create_foreign_key(
                "fk_email_outbox_event_id_events", "events", ["event_id"], ["id"], ondelete="CASCADE",
            )
    else:
        op.add_column("email_outbox", sqlalchemy.Column("event_id", sqlalchemy.String(36)))
        op.create_foreign_key(
            "email_outbox_event_id_fkey", "email_outbox", "events", ["event_id"], ["id"], ondelete="CASCADE",
        )
    op.create_index("ix_email_outbox_event_id", "email_outbox", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_event_id", table_name="email_outbox")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("email_outbox") as batch_op:
            batch_op.drop_constraint("fk_email_outbox_event_id_events", type_="foreignkey")
            batch_op.drop_column("event_id")
    else:
        op.drop_constraint("email_outbox_event_id_fkey", "email_outbox", type_="foreignkey")
        op.drop_column("email_outbox", "event_id")
