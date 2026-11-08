"""Add prioritized wishlist gifts."""

from alembic import op
import sqlalchemy

revision = "0005_wishlist_gifts"
down_revision = "0004_event_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wishlists", sqlalchemy.Column("order_version", sqlalchemy.Integer(), server_default="0", nullable=False))
    op.create_table(
        "gifts",
        sqlalchemy.Column("id", sqlalchemy.String(36), primary_key=True),
        sqlalchemy.Column("wishlist_id", sqlalchemy.String(36), nullable=False),
        sqlalchemy.Column("name", sqlalchemy.String(120), nullable=False),
        sqlalchemy.Column("description", sqlalchemy.Text()),
        sqlalchemy.Column("price", sqlalchemy.Numeric(8, 2)),
        sqlalchemy.Column("currency", sqlalchemy.String(3)),
        sqlalchemy.Column("link", sqlalchemy.String(2048)),
        sqlalchemy.Column("position", sqlalchemy.Integer(), nullable=False),
        sqlalchemy.ForeignKeyConstraint(["wishlist_id"], ["wishlists.user_id"], ondelete="CASCADE"),
        sqlalchemy.CheckConstraint("length(name) BETWEEN 1 AND 120", name="gift_name_length"),
        sqlalchemy.CheckConstraint("description IS NULL OR length(description) <= 2000", name="gift_description_length"),
        sqlalchemy.CheckConstraint("link IS NULL OR length(link) <= 2048", name="gift_link_length"),
        sqlalchemy.CheckConstraint("price IS NULL OR (price >= 0 AND price <= 999999.99)", name="gift_price_range"),
        sqlalchemy.CheckConstraint("currency IS NULL OR currency IN ('EUR', 'PLN')", name="gift_currency"),
        sqlalchemy.CheckConstraint(
            "(price IS NULL AND currency IS NULL) OR (price IS NOT NULL AND currency IS NOT NULL)",
            name="gift_price_currency",
        ),
        sqlalchemy.CheckConstraint("position >= 0", name="gift_position_nonnegative"),
        sqlalchemy.UniqueConstraint("wishlist_id", "position", name="gift_wishlist_position"),
    )
    op.create_index("ix_gifts_wishlist_id", "gifts", ["wishlist_id"])


def downgrade() -> None:
    op.drop_index("ix_gifts_wishlist_id", table_name="gifts")
    op.drop_table("gifts")
    op.drop_column("wishlists", "order_version")
