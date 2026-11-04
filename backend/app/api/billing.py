"""Plans, checkout, subscription state and provider webhooks."""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, VerifiedUser
from app.core.errors import AppError, NotFound
from app.core.ratelimit import rate_limit
from app.models import Payment, Plan, Subscription
from app.services import quotas
from app.services.billing import sandbox
from app.services.billing import service as billing
from app.services.billing.base import WebhookError

router = APIRouter(tags=["billing"])


class CheckoutIn(BaseModel):
    plan_key: str
    provider: str


def plan_out(p: Plan) -> dict:
    return {"key": p.key, "name": p.name, "description": p.description, "price_inr": p.price_inr, "price_usd": p.price_usd,
            "interval": p.interval, "features": p.features, "limits": p.limits}


@router.get("/billing/plans")
def list_plans(db: DB) -> dict:
    plans = db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)).scalars()
    return {"plans": [plan_out(p) for p in plans], "providers": billing.available_providers()}


@router.get("/billing/subscription")
def my_subscription(db: DB, user: VerifiedUser) -> dict:
    plan = quotas.get_plan_for_user(db, user)
    sub = quotas.get_active_subscription(db, user.id)
    return {"plan": plan_out(plan), "usage": quotas.usage_summary(db, user),
            "subscription": None if sub is None else {
                "status": sub.status, "provider": sub.provider, "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end, "failed_payment_count": sub.failed_payment_count}}


@router.post("/billing/checkout", dependencies=[Depends(rate_limit("checkout", 10))])
def checkout(body: CheckoutIn, db: DB, user: VerifiedUser) -> dict:
    out = billing.start_checkout(db, user, body.plan_key, body.provider)
    db.commit()
    return out


@router.post("/billing/cancel")
def cancel(db: DB, user: VerifiedUser) -> dict:
    sub = billing.cancel_subscription(db, user)
    db.commit()
    return {"status": sub.status, "cancel_at_period_end": sub.cancel_at_period_end, "current_period_end": sub.current_period_end}


@router.get("/billing/payments")
def payments(db: DB, user: VerifiedUser) -> list[dict]:
    rows = db.execute(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(100)).scalars()
    return [{"id": str(p.id), "amount": p.amount, "currency": p.currency, "status": p.status, "invoice_number": p.invoice_number,
             "paid_at": p.paid_at, "refunded_amount": p.refunded_amount, "provider": p.provider} for p in rows]


@router.get("/billing/payments/{payment_id}/invoice")
def invoice(payment_id: uuid.UUID, db: DB, user: VerifiedUser) -> dict:
    p = db.get(Payment, payment_id)
    if p is None or p.user_id != user.id or not p.invoice_number:
        raise NotFound("Invoice not found")
    sub = db.get(Subscription, p.subscription_id) if p.subscription_id else None
    plan = db.get(Plan, sub.plan_id) if sub else None
    return {"invoice_number": p.invoice_number, "date": p.paid_at, "customer_email": user.email, "plan": plan.name if plan else None,
            "amount": p.amount, "currency": p.currency, "status": p.status, "refunded_amount": p.refunded_amount, "provider": p.provider}


async def _webhook(provider: str, request: Request, db) -> dict:
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    prov = billing.get_provider(provider)
    try:
        ev = prov.parse_webhook(raw, headers)
    except WebhookError as exc:
        raise AppError("Invalid webhook", code="invalid_webhook", status_code=400) from exc
    result = billing.process_event(db, ev)
    db.commit()
    return {"status": result}


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: DB) -> dict:
    return await _webhook("razorpay", request, db)


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: DB) -> dict:
    return await _webhook("stripe", request, db)


@router.post("/webhooks/sandbox")
async def sandbox_webhook(request: Request, db: DB) -> dict:
    return await _webhook("sandbox", request, db)


class SandboxPayIn(BaseModel):
    subscription_id: str
    outcome: str = "success"  # success | fail


@router.post("/billing/sandbox/complete")
async def sandbox_complete(body: SandboxPayIn, request: Request, db: DB, user: VerifiedUser) -> dict:
    """DEV ONLY: simulate the provider paying/failing, delivered through the signed webhook path."""
    if not get_settings().billing_sandbox_enabled or get_settings().is_production_like:
        raise NotFound("Not found")
    sub = db.execute(select(Subscription).where(Subscription.provider == "sandbox", Subscription.user_id == user.id,
                                                Subscription.provider_subscription_id == body.subscription_id)).scalar_one_or_none()
    if sub is None:
        raise NotFound("Subscription not found")
    plan = db.get(Plan, sub.plan_id)
    kinds = ["subscription_activated", "payment_succeeded"] if body.outcome == "success" else ["payment_failed"]
    results = []
    for kind in kinds:
        raw = sandbox.build_event(kind=kind, user_id=user.id, plan_key=plan.key, amount=plan.price_inr, currency="INR",
                                  sub_id=sub.provider_subscription_id)
        ev = billing.get_provider("sandbox").parse_webhook(raw, {"x-sandbox-signature": sandbox.sign(raw)})
        results.append(billing.process_event(db, ev))
    db.commit()
    return {"results": results}
