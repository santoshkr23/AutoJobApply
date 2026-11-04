import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings
from app.core.errors import ServiceNotConfigured
from app.services.billing.base import BillingEvent, BillingProvider, Checkout, WebhookError

API = "https://api.razorpay.com/v1"


def _ts(v) -> datetime | None:
    return datetime.fromtimestamp(int(v), UTC) if v else None


class RazorpayProvider(BillingProvider):
    name = "razorpay"

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.razorpay_key_id and s.razorpay_key_secret and s.razorpay_webhook_secret)

    def _client(self) -> httpx.Client:
        s = get_settings()
        return httpx.Client(base_url=API, auth=(s.razorpay_key_id, s.razorpay_key_secret), timeout=20)

    def create_checkout(self, *, user_id, email, plan, success_url, cancel_url) -> Checkout:
        if not self.configured():
            raise ServiceNotConfigured("Razorpay is not configured on this server.")
        if not plan.razorpay_plan_id:
            raise ServiceNotConfigured(f"Plan '{plan.key}' has no Razorpay plan id configured.")
        with self._client() as c:
            r = c.post("/subscriptions", json={"plan_id": plan.razorpay_plan_id, "total_count": 120, "customer_notify": 1,
                                               "notes": {"user_id": str(user_id), "plan_key": plan.key}})
        if r.status_code >= 400:
            raise ServiceNotConfigured(f"Razorpay rejected the request ({r.status_code}).")
        d = r.json()
        return Checkout(url=d["short_url"], provider_subscription_id=d["id"])

    def parse_webhook(self, raw: bytes, headers: dict[str, str]) -> BillingEvent:
        secret = get_settings().razorpay_webhook_secret
        if not secret:
            raise ServiceNotConfigured("Razorpay webhook secret is not configured.")
        sig = headers.get("x-razorpay-signature", "")
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise WebhookError("invalid signature")
        try:
            body = json.loads(raw)
            event_id = headers.get("x-razorpay-event-id") or body["id"]
            etype = body["event"]
            payload = body.get("payload", {})
        except (ValueError, KeyError) as exc:
            raise WebhookError("malformed payload") from exc
        sub = payload.get("subscription", {}).get("entity", {})
        pay = payload.get("payment", {}).get("entity", {})
        notes = sub.get("notes") or {}
        uid = notes.get("user_id")
        ev = BillingEvent(provider="razorpay", event_id=str(event_id), type="ignored", raw_type=etype,
                          provider_subscription_id=sub.get("id") or pay.get("subscription_id"),
                          user_id=uuid.UUID(uid) if uid else None, plan_key=notes.get("plan_key"),
                          period_start=_ts(sub.get("current_start")), period_end=_ts(sub.get("current_end")))
        if etype == "subscription.activated":
            ev.type = "subscription_activated"
        elif etype == "subscription.charged":
            ev.type, ev.provider_payment_id = "payment_succeeded", pay.get("id")
            ev.amount, ev.currency = pay.get("amount"), pay.get("currency")
        elif etype == "payment.failed":
            ev.type, ev.provider_payment_id = "payment_failed", pay.get("id")
            ev.amount, ev.currency, ev.failure_reason = pay.get("amount"), pay.get("currency"), (pay.get("error_description") or "")[:250]
        elif etype in ("subscription.cancelled", "subscription.completed", "subscription.halted"):
            ev.type = "subscription_canceled"
        elif etype == "refund.processed":
            ref = payload.get("refund", {}).get("entity", {})
            ev.type, ev.provider_payment_id, ev.refunded_amount = "refund", ref.get("payment_id"), ref.get("amount")
        return ev

    def cancel(self, provider_subscription_id: str) -> None:
        with self._client() as c:
            r = c.post(f"/subscriptions/{provider_subscription_id}/cancel", json={"cancel_at_cycle_end": 1})
        if r.status_code >= 400:
            raise ServiceNotConfigured(f"Razorpay could not cancel the subscription ({r.status_code}).")

    def refund(self, provider_payment_id: str, amount: int | None) -> None:
        with self._client() as c:
            r = c.post(f"/payments/{provider_payment_id}/refund", json={"amount": amount} if amount else {})
        if r.status_code >= 400:
            raise ServiceNotConfigured(f"Razorpay refund failed ({r.status_code}).")
