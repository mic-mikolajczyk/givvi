"""Add private assignment generations and recipient records."""

from alembic import op
import sqlalchemy

revision = "0006_private_assignments"
down_revision = "0005_wishlist_gifts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("event_participants") as batch_op:
        batch_op.create_unique_constraint("event_participant_id_event", ["id", "event_id"])

    op.create_table(
        "event_draws",
        sqlalchemy.Column("id", sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column("event_id", sqlalchemy.String(36), nullable=False),
        sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True), nullable=False),
        sqlalchemy.Column("reset_at", sqlalchemy.DateTime(timezone=True)),
        sqlalchemy.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sqlalchemy.UniqueConstraint("id", "event_id", name="event_draw_id_event"),
    )
    op.create_index("ix_event_draws_event_id", "event_draws", ["event_id"])
    op.create_index(
        "uq_event_draw_active",
        "event_draws",
        ["event_id"],
        unique=True,
        postgresql_where=sqlalchemy.text("reset_at IS NULL"),
        sqlite_where=sqlalchemy.text("reset_at IS NULL"),
    )
    op.create_table(
        "event_assignments",
        sqlalchemy.Column("draw_id", sqlalchemy.String(36), nullable=False),
        sqlalchemy.Column("giver_participant_id", sqlalchemy.String(36), nullable=False),
        sqlalchemy.Column("event_id", sqlalchemy.String(36), nullable=False),
        sqlalchemy.Column("recipient_participant_id", sqlalchemy.String(36), nullable=False),
        sqlalchemy.Column("revealed_at", sqlalchemy.DateTime(timezone=True)),
        sqlalchemy.ForeignKeyConstraint(
            ["draw_id", "event_id"], ["event_draws.id", "event_draws.event_id"], ondelete="CASCADE",
        ),
        sqlalchemy.ForeignKeyConstraint(
            ["giver_participant_id", "event_id"], ["event_participants.id", "event_participants.event_id"],
            ondelete="RESTRICT",
        ),
        sqlalchemy.ForeignKeyConstraint(
            ["recipient_participant_id", "event_id"], ["event_participants.id", "event_participants.event_id"],
            ondelete="RESTRICT",
        ),
        sqlalchemy.PrimaryKeyConstraint("draw_id", "giver_participant_id"),
        sqlalchemy.UniqueConstraint("draw_id", "recipient_participant_id", name="event_assignment_recipient"),
        sqlalchemy.CheckConstraint("giver_participant_id <> recipient_participant_id", name="event_assignment_no_self"),
    )


def downgrade() -> None:
    op.drop_table("event_assignments")
    op.drop_index("uq_event_draw_active", table_name="event_draws")
    op.drop_index("ix_event_draws_event_id", table_name="event_draws")
    op.drop_table("event_draws")
    with op.batch_alter_table("event_participants") as batch_op:
        batch_op.drop_constraint("event_participant_id_event", type_="unique")
