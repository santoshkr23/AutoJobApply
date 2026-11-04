"""LOCAL DEVELOPMENT ONLY. Simulates a payment provider; no real money moves. Refused in production-like environments.

It still goes through the real webhook path: the sandbox signs its own events with a secret and the handler
verifies the signature exactly as it would for Razorpay/Stripe.
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.errors import ServiceNotConfigured
from app.services.billing.base import BillingEvent, BillingProvider, Checkout, WebhookError


def sign(raw: bytes) -> str:
    return hmac.new(get_settings().billing_sandbox_secret.encode(), raw, hashlib.sha256).hexdigest()


def build_event(*, kind: str, user_id: uuid.UUID, plan_key: str, amount: int, currency: str, sub_id: str) -> bytes:
    now = datetime.now(UTC)
    return json.dumps({
        "id": f"sbx_evt_{uuid.uuid4().hex}", "type": kind, "user_id": str(user_id), "plan_key": plan_key,
        "subscription_id": sub_id, "payment_id": f"sbx_pay_{uuid.uuid4().hex[:12]}", "amount": amount, "currency": currency,
        "period_start": now.isoformat(), "period_end": (now + timedelta(days=30)).isoformat(), "t": int(time.time()),
    }).encode()


class SandboxProvider(BillingProvider):
    name = "sandbox"

    def configured(self) -> bool:
        return get_settings().billing_sandbox_enabled and not get_settings().is_production_like

    def create_checkout(self, *, user_id, email, plan, success_url, cancel_url) -> Checkout:
        if not self.configured():
            raise ServiceNotConfigured("Sandbox billing is disabled.")
        sub_id = f"sbx_sub_{uuid.uuid4().hex[:12]}"
        return Checkout(url=f"{get_settings().frontend_url}/dashboard/subscription?sandbox_sub={sub_id}&plan={plan.key}",
                        provider_subscription_id=sub_id)

    def parse_webhook(self, raw: bytes, headers: dict[str, str]) -> BillingEvent:
        if not self.configured():
            raise ServiceNotConfigured("Sandbox billing is disabled.")
        if not hmac.compare_digest(headers.get("x-sandbox-signature", ""), sign(raw)):
            raise WebhookError("invalid signature")
        b = json.loads(raw)
        return BillingEvent(
            provider="sandbox", event_id=b["id"], type=b["type"], provider_subscription_id=b["subscription_id"],
            provider_payment_id=b.get("payment_id"), user_id=uuid.UUID(b["user_id"]), plan_key=b["plan_key"],
            amount=b.get("amount"), currency=b.get("currency"),
            period_start=datetime.fromisoformat(b["period_start"]), period_end=datetime.fromisoformat(b["period_end"]),
        )

    def cancel(self, provider_subscription_id: str) -> None:
        return None

    def refund(self, provider_payment_id: str, amount: int | None) -> None:
        return None
