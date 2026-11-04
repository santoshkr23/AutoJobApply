import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings
from app.core.errors import ServiceNotConfigured
from app.services.billing.base import BillingEvent, BillingProvider, Checkout, WebhookError

API = "https://api.stripe.com/v1"
TOLERANCE_SECONDS = 300


def _ts(v) -> datetime | None:
    return datetime.fromtimestamp(int(v), UTC) if v else None


def verify_signature(raw: bytes, header: str, secret: str, now: float | None = None) -> None:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t, v1 = parts["t"], [p.split("=", 1)[1] for p in header.split(",") if p.startswith("v1=")]
    except (KeyError, ValueError) as exc:
        raise WebhookError("malformed signature header") from exc
    if abs((now or time.time()) - int(t)) > TOLERANCE_SECONDS:
        raise WebhookError("timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in v1):
        raise WebhookError("invalid signature")


class StripeProvider(BillingProvider):
    name = "stripe"

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.stripe_secret_key and s.stripe_webhook_secret)

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {get_settings().stripe_secret_key}"}, timeout=20)

    def create_checkout(self, *, user_id, email, plan, success_url, cancel_url) -> Checkout:
        if not self.configured():
            raise ServiceNotConfigured("Stripe is not configured on this server.")
        if not plan.stripe_price_id:
            raise ServiceNotConfigured(f"Plan '{plan.key}' has no Stripe price id configured.")
        data = {"mode": "subscription", "line_items[0][price]": plan.stripe_price_id, "line_items[0][quantity]": "1",
                "success_url": success_url, "cancel_url": cancel_url, "client_reference_id": str(user_id),
                "customer_email": email, "metadata[user_id]": str(user_id), "metadata[plan_key]": plan.key,
                "subscription_data[metadata][user_id]": str(user_id), "subscription_data[metadata][plan_key]": plan.key}
        with self._client() as c:
            r = c.post("/checkout/sessions", data=data)
        if r.status_code >= 400:
            raise ServiceNotConfigured(f"Stripe rejected the request ({r.status_code}).")
        return Checkout(url=r.json()["url"])

    def parse_webhook(self, raw: bytes, headers: dict[str, str]) -> BillingEvent:
        secret = get_settings().stripe_webhook_secret
        if not secret:
            raise ServiceNotConfigured("Stripe webhook secret is not configured.")
        verify_signature(raw, headers.get("stripe-signature", ""), secret)
        try:
            body = json.loads(raw)
            etype, obj, event_id = body["type"], body["data"]["object"], body["id"]
        except (ValueError, KeyError) as exc:
            raise WebhookError("malformed payload") from exc
        meta = obj.get("metadata") or {}
        ev = BillingEvent(provider="stripe", event_id=event_id, type="ignored", raw_type=etype)
        if meta.get("user_id"):
            ev.user_id, ev.plan_key = uuid.UUID(meta["user_id"]), meta.get("plan_key")
        if etype == "checkout.session.completed" and obj.get("mode") == "subscription" and obj.get("payment_status") in ("paid", "no_payment_required"):
            ev.type, ev.provider_subscription_id = "subscription_activated", obj.get("subscription")
        elif etype in ("invoice.paid", "invoice.payment_failed"):
            line = (obj.get("lines", {}).get("data") or [{}])[0]
            lm = (line.get("metadata") or {}) or (obj.get("subscription_details", {}).get("metadata") or {})
            if lm.get("user_id"):
                ev.user_id, ev.plan_key = uuid.UUID(lm["user_id"]), lm.get("plan_key")
            ev.provider_subscription_id = obj.get("subscription")
            ev.provider_payment_id = obj.get("payment_intent") or obj.get("id")
            ev.amount, ev.currency = obj.get("amount_paid") if etype == "invoice.paid" else obj.get("amount_due"), (obj.get("currency") or "").upper()
            period = line.get("period") or {}
            ev.period_start, ev.period_end = _ts(period.get("start")), _ts(period.get("end"))
            ev.type = "payment_succeeded" if etype == "invoice.paid" else "payment_failed"
            if ev.type == "payment_failed":
                ev.failure_reason = "Payment failed"
        elif etype in ("customer.subscription.deleted", "customer.subscription.updated"):
            ev.provider_subscription_id = obj.get("id")
            ev.period_start, ev.period_end = _ts(obj.get("current_period_start")), _ts(obj.get("current_period_end"))
            ev.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
            if etype.endswith("deleted") or obj.get("status") in ("canceled", "unpaid", "incomplete_expired"):
                ev.type = "subscription_canceled"
        elif etype == "charge.refunded":
            ev.type, ev.provider_payment_id, ev.refunded_amount = "refund", obj.get("payment_intent"), obj.get("amount_refunded")
        return ev

    def cancel(self, provider_subscription_id: str) -> None:
        with self._client() as c:
            r = c.post(f"/subscriptions/{provider_subscription_id}", data={"cancel_at_period_end": "true"})
        if r.status_code >= 400:
            raise ServiceNotConfigured(f"Stripe could not cancel the subscription ({r.status_code}).")

    def refund(self, provider_payment_id: str, amount: int | None) -> None:
        data = {"payment_intent": provider_payment_id, **({"amount": str(amount)} if amount else {})}
        with self._client() as c:
            r = c.post("/refunds", data=data)
        if r.status_code >= 400:
            raise ServiceNotConfigured(f"Stripe refund failed ({r.status_code}).")
