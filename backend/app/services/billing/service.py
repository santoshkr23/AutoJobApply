"""Billing state changes. The ONLY path that activates a paid plan is a verified provider webhook."""

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.errors import AppError, NotFound, ServiceNotConfigured
from app.models import Payment, Plan, Subscription, User, WebhookEvent
from app.models.base import utcnow
from app.services.billing.base import BillingEvent, BillingProvider
from app.services.billing.razorpay import RazorpayProvider
from app.services.billing.sandbox import SandboxProvider
from app.services.billing.stripe import StripeProvider
from app.services.notifications import notify

log = logging.getLogger(__name__)


def get_provider(name: str) -> BillingProvider:
    providers = {"razorpay": RazorpayProvider, "stripe": StripeProvider, "sandbox": SandboxProvider}
    if name not in providers:
        raise NotFound("Unknown billing provider")
    return providers[name]()


def available_providers() -> list[str]:
    return [n for n in ("razorpay", "stripe", "sandbox") if get_provider(n).configured()]


def plan_by_key(db: Session, key: str | None) -> Plan | None:
    return db.execute(select(Plan).where(Plan.key == key)).scalar_one_or_none() if key else None


def invoice_number() -> str:
    return f"INV-{utcnow():%Y%m}-{uuid.uuid4().hex[:8].upper()}"


def start_checkout(db: Session, user: User, plan_key: str, provider_name: str) -> dict:
    plan = plan_by_key(db, plan_key)
    if plan is None or not plan.is_active or plan.key == "free":
        raise AppError("Choose a paid plan.", code="invalid_plan", status_code=422)
    provider = get_provider(provider_name)
    if not provider.configured():
        raise ServiceNotConfigured(f"{provider_name.title()} payments are not configured on this server.")
    from app.core.config import get_settings

    base = get_settings().frontend_url
    co = provider.create_checkout(user_id=user.id, email=user.email, plan=plan,
                                  success_url=f"{base}/dashboard/subscription?checkout=success",
                                  cancel_url=f"{base}/dashboard/subscription?checkout=cancelled")
    audit(db, action="billing.checkout_started", actor_type="user", actor_id=user.id, meta={"plan": plan.key, "provider": provider_name})
    # The subscription stays 'incomplete' (not entitling) until a verified webhook says it is paid.
    if co.provider_subscription_id:
        db.add(Subscription(user_id=user.id, plan_id=plan.id, provider=provider_name,
                            provider_subscription_id=co.provider_subscription_id, status="incomplete"))
    return {"checkout_url": co.url, "provider": provider_name}


def process_event(db: Session, ev: BillingEvent) -> str:
    """Idempotent. Returns 'processed' | 'duplicate' | 'ignored'."""
    try:
        with db.begin_nested():
            db.add(WebhookEvent(provider=ev.provider, event_id=ev.event_id, event_type=ev.raw_type or ev.type, status="processed",
                                received_at=utcnow()))
            db.flush()
    except IntegrityError:
        return "duplicate"
    if ev.type == "ignored":
        return "ignored"
    handler = {"subscription_activated": _activated, "payment_succeeded": _paid, "payment_failed": _failed,
               "subscription_canceled": _canceled, "refund": _refund}[ev.type]
    handler(db, ev)
    return "processed"


def _find_sub(db, ev: BillingEvent) -> Subscription | None:
    if not ev.provider_subscription_id:
        return None
    return db.execute(select(Subscription).where(Subscription.provider == ev.provider,
                                                 Subscription.provider_subscription_id == ev.provider_subscription_id)).scalar_one_or_none()


def _user(db, ev, sub) -> User | None:
    uid = ev.user_id or (sub.user_id if sub else None)
    return db.get(User, uid) if uid else None


def _activated(db: Session, ev: BillingEvent) -> None:
    sub = _find_sub(db, ev)
    plan = plan_by_key(db, ev.plan_key) or (db.get(Plan, sub.plan_id) if sub else None)
    user = _user(db, ev, sub)
    if user is None or plan is None:
        raise AppError("Webhook references an unknown user or plan", code="webhook_unmatched", status_code=422)
    if sub is None:
        sub = Subscription(user_id=user.id, plan_id=plan.id, provider=ev.provider, provider_subscription_id=ev.provider_subscription_id or ev.event_id,
                           status="incomplete")
        db.add(sub)
    elif sub.user_id != user.id:
        raise AppError("Webhook user mismatch", code="webhook_unmatched", status_code=422)
    sub.plan_id, sub.status = plan.id, "active"
    sub.current_period_start = ev.period_start or sub.current_period_start or utcnow()
    sub.current_period_end = ev.period_end or sub.current_period_end or (utcnow() + timedelta(days=31))
    sub.failed_payment_count = 0
    db.flush()
    for other in db.execute(select(Subscription).where(Subscription.user_id == user.id, Subscription.id != sub.id,
                                                       Subscription.status.in_(["active", "trialing", "past_due"]))).scalars():
        other.status, other.canceled_at = "canceled", utcnow()  # plan change replaces the previous subscription
    audit(db, action="billing.subscription_activated", actor_type="system", target_type="subscription", target_id=sub.id,
          meta={"plan": plan.key, "provider": ev.provider})
    notify(db, user, "subscription_payment", f"{plan.name} plan active", f"Your {plan.name} subscription is now active.", {"plan": plan.key})


def _paid(db: Session, ev: BillingEvent) -> None:
    sub = _find_sub(db, ev)
    user = _user(db, ev, sub)
    if user is None or not ev.provider_payment_id:
        raise AppError("Payment webhook cannot be matched to a user", code="webhook_unmatched", status_code=422)
    if sub is not None and sub.status != "canceled":
        sub.status, sub.failed_payment_count = "active", 0
        sub.current_period_start = ev.period_start or sub.current_period_start
        sub.current_period_end = ev.period_end or sub.current_period_end
    pay = db.execute(select(Payment).where(Payment.provider == ev.provider, Payment.provider_payment_id == ev.provider_payment_id)).scalar_one_or_none()
    if pay is None:
        pay = Payment(user_id=user.id, subscription_id=sub.id if sub else None, provider=ev.provider,
                      provider_payment_id=ev.provider_payment_id, amount=ev.amount or 0, currency=(ev.currency or "INR").upper(),
                      status="succeeded", paid_at=utcnow(), invoice_number=invoice_number())
        db.add(pay)
    else:
        pay.status, pay.paid_at = "succeeded", pay.paid_at or utcnow()
        pay.invoice_number = pay.invoice_number or invoice_number()
    notify(db, user, "subscription_payment", "Payment received", f"We received your payment ({pay.invoice_number}).", {"invoice": pay.invoice_number})


def _failed(db: Session, ev: BillingEvent) -> None:
    sub = _find_sub(db, ev)
    user = _user(db, ev, sub)
    if user is None:
        raise AppError("Payment webhook cannot be matched to a user", code="webhook_unmatched", status_code=422)
    if sub is not None and sub.status in ("active", "trialing", "past_due"):
        sub.status, sub.failed_payment_count = "past_due", sub.failed_payment_count + 1
    if ev.provider_payment_id:
        exists = db.execute(select(Payment).where(Payment.provider == ev.provider, Payment.provider_payment_id == ev.provider_payment_id)).scalar_one_or_none()
        if exists is None:
            db.add(Payment(user_id=user.id, subscription_id=sub.id if sub else None, provider=ev.provider,
                           provider_payment_id=ev.provider_payment_id, amount=ev.amount or 0, currency=(ev.currency or "INR").upper(),
                           status="failed", failure_reason=ev.failure_reason))
    notify(db, user, "subscription_payment", "Payment failed",
           "We could not process your subscription payment. Update your payment method to keep your plan.", {}, always_email=True)


def _canceled(db: Session, ev: BillingEvent) -> None:
    sub = _find_sub(db, ev)
    if sub is None:
        return
    sub.status, sub.canceled_at = "canceled", utcnow()
    sub.cancel_at_period_end = bool(sub.current_period_end and sub.current_period_end > utcnow())
    user = db.get(User, sub.user_id)
    notify(db, user, "subscription_expiry", "Subscription cancelled",
           "Your subscription was cancelled. You keep access until the end of the paid period.", {})


def _refund(db: Session, ev: BillingEvent) -> None:
    pay = db.execute(select(Payment).where(Payment.provider == ev.provider, Payment.provider_payment_id == ev.provider_payment_id)).scalar_one_or_none()
    if pay is None:
        return
    pay.refunded_amount = min(ev.refunded_amount or pay.amount, pay.amount)
    pay.status = "refunded" if pay.refunded_amount >= pay.amount else "partially_refunded"


def cancel_subscription(db: Session, user: User) -> Subscription:
    from app.services.quotas import get_active_subscription

    sub = get_active_subscription(db, user.id)
    if sub is None or sub.status == "canceled":
        raise NotFound("No active subscription")
    get_provider(sub.provider).cancel(sub.provider_subscription_id)
    sub.cancel_at_period_end = True
    audit(db, action="billing.cancel_requested", actor_type="user", actor_id=user.id, target_type="subscription", target_id=sub.id)
    return sub


def refund_payment(db: Session, payment: Payment, amount: int | None, admin_id: uuid.UUID | None) -> Payment:
    if payment.status not in ("succeeded", "partially_refunded"):
        raise AppError("Only successful payments can be refunded.", code="not_refundable", status_code=409)
    remaining = payment.amount - payment.refunded_amount
    if amount is not None and not (0 < amount <= remaining):
        raise AppError("Invalid refund amount.", code="validation_error", status_code=422)
    get_provider(payment.provider).refund(payment.provider_payment_id, amount)
    # Final state is set when the provider's refund webhook arrives; sandbox has none, so settle it directly.
    if payment.provider == "sandbox":
        payment.refunded_amount += amount or remaining
        payment.status = "refunded" if payment.refunded_amount >= payment.amount else "partially_refunded"
    audit(db, action="billing.refund_requested", actor_type="admin", actor_id=admin_id, target_type="payment", target_id=payment.id,
          meta={"amount": amount or remaining})
    return payment
