"""Billing provider interface. Providers verify webhook signatures themselves; nothing the browser says is trusted."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


class WebhookError(Exception):
    """Bad signature / malformed payload."""


@dataclass
class BillingEvent:
    provider: str
    event_id: str
    type: str  # subscription_activated | payment_succeeded | payment_failed | subscription_canceled | refund | ignored
    provider_subscription_id: str | None = None
    provider_payment_id: str | None = None
    user_id: uuid.UUID | None = None
    plan_key: str | None = None
    amount: int | None = None
    currency: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    cancel_at_period_end: bool = False
    failure_reason: str | None = None
    refunded_amount: int | None = None
    raw_type: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Checkout:
    url: str
    provider_subscription_id: str | None = None
    extra: dict = field(default_factory=dict)


class BillingProvider:
    name = "base"

    def configured(self) -> bool:
        raise NotImplementedError

    def create_checkout(self, *, user_id: uuid.UUID, email: str, plan, success_url: str, cancel_url: str) -> Checkout:
        raise NotImplementedError

    def parse_webhook(self, raw: bytes, headers: dict[str, str]) -> BillingEvent:
        raise NotImplementedError

    def cancel(self, provider_subscription_id: str) -> None:
        raise NotImplementedError

    def refund(self, provider_payment_id: str, amount: int | None) -> None:
        raise NotImplementedError
