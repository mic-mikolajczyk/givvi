"""Add revocable event invitation links."""

from alembic import op
import sqlalchemy

revision = "0004_event_invitations"
down_revision = "0003_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sqlalchemy.Column("invite_token_hash", sqlalchemy.String(64)))
    op.add_column("events", sqlalchemy.Column("invite_token_encrypted", sqlalchemy.String(512)))
    op.create_unique_constraint("event_invite_token_hash", "events", ["invite_token_hash"])


def downgrade() -> None:
    op.drop_constraint("event_invite_token_hash", "events", type_="unique")
    op.drop_column("events", "invite_token_encrypted")
    op.drop_column("events", "invite_token_hash")
