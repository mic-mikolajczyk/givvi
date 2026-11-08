"""Allow canceled events to outlive account deletion."""

from alembic import op
import sqlalchemy

revision = "0007_nullable_event_admin"
down_revision = "0006_private_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("events", naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }) as batch_op:
            batch_op.drop_constraint("fk_events_admin_id_users", type_="foreignkey")
            batch_op.alter_column("admin_id", existing_type=sqlalchemy.String(36), nullable=True)
            batch_op.create_foreign_key(
                "fk_events_admin_id_users", "users", ["admin_id"], ["id"], ondelete="SET NULL",
            )
    else:
        op.drop_constraint("events_admin_id_fkey", "events", type_="foreignkey")
        op.alter_column("events", "admin_id", existing_type=sqlalchemy.String(36), nullable=True)
        op.create_foreign_key(
            "events_admin_id_fkey", "events", "users", ["admin_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_events_admin_id_users" if op.get_bind().dialect.name == "sqlite" else "events_admin_id_fkey",
        "events",
        type_="foreignkey",
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("events", naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        }) as batch_op:
            batch_op.alter_column("admin_id", existing_type=sqlalchemy.String(36), nullable=False)
            batch_op.create_foreign_key(
                "fk_events_admin_id_users", "users", ["admin_id"], ["id"], ondelete="RESTRICT",
            )
    else:
        op.alter_column("events", "admin_id", existing_type=sqlalchemy.String(36), nullable=False)
        op.create_foreign_key(
            "events_admin_id_fkey", "events", "users", ["admin_id"], ["id"], ondelete="RESTRICT",
        )
