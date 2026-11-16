"""Add organizer-managed events and roster entries."""

from alembic import op
import sqlalchemy

revision = "0003_events"
down_revision = "0002_no_signup_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sqlalchemy.Column("id", sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column("admin_id", sqlalchemy.String(36), sqlalchemy.ForeignKey("users.id", ondelete="RESTRICT"),
                          nullable=False),
        sqlalchemy.Column("name", sqlalchemy.String(120), nullable=False),
        sqlalchemy.Column("exchange_date", sqlalchemy.Date(), nullable=False),
        sqlalchemy.Column("exchange_time", sqlalchemy.Time()),
        sqlalchemy.Column("time_zone", sqlalchemy.String(64), nullable=False),
        sqlalchemy.Column("location", sqlalchemy.String(255)),
        sqlalchemy.Column("description", sqlalchemy.Text()),
        sqlalchemy.Column("currency", sqlalchemy.String(3), nullable=False),
        sqlalchemy.Column("budget", sqlalchemy.Numeric(8, 2)),
        sqlalchemy.Column("drawing_enabled", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.Column("drawing_ever_enabled", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.Column("archived", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.Column("cancelled", sqlalchemy.Boolean(), nullable=False),
        sqlalchemy.CheckConstraint("currency IN ('EUR', 'PLN')", name="event_currency"),
        sqlalchemy.CheckConstraint("budget IS NULL OR (budget >= 0 AND budget <= 999999.99)", name="event_budget_range"),
        sqlalchemy.CheckConstraint("NOT drawing_enabled OR drawing_ever_enabled", name="event_drawing_history"),
    )
    op.create_index("ix_events_admin_id", "events", ["admin_id"])
    op.create_table(
        "event_participants",
        sqlalchemy.Column("id", sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column("event_id", sqlalchemy.String(36), sqlalchemy.ForeignKey("events.id", ondelete="CASCADE"),
                          nullable=False),
        sqlalchemy.Column("name", sqlalchemy.String(120), nullable=False),
        sqlalchemy.Column("user_id", sqlalchemy.String(36), sqlalchemy.ForeignKey("users.id", ondelete="SET NULL")),
        sqlalchemy.UniqueConstraint("event_id", "user_id", name="event_participant_user"),
        sqlalchemy.CheckConstraint("length(name) BETWEEN 1 AND 120", name="event_participant_name_length"),
    )
    op.create_index("ix_event_participants_event_id", "event_participants", ["event_id"])
    op.create_index("ix_event_participants_user_id", "event_participants", ["user_id"])


def downgrade() -> None:
    op.drop_table("event_participants")
    op.drop_table("events")
