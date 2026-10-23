from datetime import date
from datetime import datetime
from datetime import time
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import Time
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("language IN ('en', 'pl')", name="user_language"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    language: Mapped[str] = mapped_column(String(2), default="en")
    pending_email: Mapped[str | None] = mapped_column(String(254), unique=True)


class Wishlist(Base):
    __tablename__ = "wishlists"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    order_version: Mapped[int] = mapped_column(Integer, default=0)


class Gift(Base):
    __tablename__ = "gifts"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 120", name="gift_name_length"),
        CheckConstraint("description IS NULL OR length(description) <= 2000", name="gift_description_length"),
        CheckConstraint("link IS NULL OR length(link) <= 2048", name="gift_link_length"),
        CheckConstraint("price IS NULL OR (price >= 0 AND price <= 999999.99)", name="gift_price_range"),
        CheckConstraint("currency IS NULL OR currency IN ('EUR', 'PLN')", name="gift_currency"),
        CheckConstraint(
            "(price IS NULL AND currency IS NULL) OR (price IS NOT NULL AND currency IS NOT NULL)",
            name="gift_price_currency",
        ),
        CheckConstraint("position >= 0", name="gift_position_nonnegative"),
        UniqueConstraint("wishlist_id", "position", name="gift_wishlist_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    wishlist_id: Mapped[str] = mapped_column(ForeignKey("wishlists.user_id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    link: Mapped[str | None] = mapped_column(String(2048))
    position: Mapped[int] = mapped_column(Integer)


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AccountToken(Base):
    __tablename__ = "account_tokens"
    __table_args__ = (CheckConstraint("purpose IN ('reset', 'email')", name="token_purpose"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(10))
    target_email: Mapped[str | None] = mapped_column(String(254))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EmailMessage(Base):
    __tablename__ = "email_outbox"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    payload: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_id: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RateBucket(Base):
    __tablename__ = "rate_buckets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("currency IN ('EUR', 'PLN')", name="event_currency"),
        CheckConstraint("budget IS NULL OR (budget >= 0 AND budget <= 999999.99)", name="event_budget_range"),
        CheckConstraint("NOT drawing_enabled OR drawing_ever_enabled", name="event_drawing_history"),
        UniqueConstraint("invite_token_hash", name="event_invite_token_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    admin_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    exchange_date: Mapped[date] = mapped_column(Date)
    exchange_time: Mapped[time | None] = mapped_column(Time)
    time_zone: Mapped[str] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    budget: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    drawing_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    drawing_ever_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_token_hash: Mapped[str | None] = mapped_column(String(64))
    invite_token_encrypted: Mapped[str | None] = mapped_column(String(512))


class EventParticipant(Base):
    __tablename__ = "event_participants"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="event_participant_user"),
        CheckConstraint("length(name) BETWEEN 1 AND 120", name="event_participant_name_length"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
