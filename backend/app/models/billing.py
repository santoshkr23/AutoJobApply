import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, Timestamps, UUIDPk


class Plan(UUIDPk, Timestamps, Base):
    __tablename__ = "plans"

    key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)  # free | pro | premium
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price_inr: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # paise
    price_usd: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # cents
    interval: Mapped[str] = mapped_column(String(16), default="month", nullable=False)
    limits: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    features: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    razorpay_plan_id: Mapped[str | None] = mapped_column(String(64))
    stripe_price_id: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Subscription(UUIDPk, Timestamps, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_id", name="uq_subscriptions_provider_sub"),
        Index("ix_subscriptions_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("plans.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)  # razorpay | stripe | sandbox
    provider_subscription_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="incomplete", nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_payment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Payment(UUIDPk, Timestamps, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_payment"),
        Index("ix_payments_user", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("subscriptions.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # minor units
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)  # succeeded|failed|refunded|partially_refunded
    refunded_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(32), unique=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEvent(UUIDPk, Base):
    """Deduplicates provider webhook deliveries."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),)

    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="processed", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UsageRecord(UUIDPk, Timestamps, Base):
    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("user_id", "metric", "period", name="uq_usage_user_metric_period"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    metric: Mapped[str] = mapped_column(String(48), nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM (or YYYY-MM-DD for daily)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
