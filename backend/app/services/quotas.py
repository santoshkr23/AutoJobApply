"""Plans, entitlements and usage metering. Limits are data (editable by admins), never hard-coded."""

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import QuotaExceeded
from app.models.base import utcnow
from app.models.billing import Plan, Subscription, UsageRecord
from app.models.user import User

# Subscriptions that still grant paid features. past_due gets a short grace period.
ENTITLING_STATUSES = {"active", "trialing"}
PAST_DUE_GRACE_DAYS = 3

DEFAULT_PLANS = [
    {
        "key": "free", "name": "Free", "price_inr": 0, "price_usd": 0, "sort_order": 0,
        "description": "Try AI job matching with a small monthly allowance.",
        "limits": {
            "matched_jobs_per_month": 10, "applications_per_month": 0, "resume_customizations_per_month": 0,
            "cover_letters_per_month": 0, "discovery_interval_hours": 168, "max_resumes": 1,
            "csv_export": True, "auto_apply": False, "advanced_matching": False, "priority_processing": False,
        },
        "features": ["10 matched jobs / month", "Basic job matching", "CSV export", "No automated applications"],
    },
    {
        "key": "pro", "name": "Pro", "price_inr": 49900, "price_usd": 600, "sort_order": 1,
        "description": "Daily discovery, tailored resumes and application tracking.",
        "limits": {
            "matched_jobs_per_month": 300, "applications_per_month": 50, "resume_customizations_per_month": 100,
            "cover_letters_per_month": 100, "discovery_interval_hours": 24, "max_resumes": 1,
            "csv_export": True, "auto_apply": True, "advanced_matching": False, "priority_processing": False,
        },
        "features": [
            "Daily job discovery", "AI resume customization", "Cover letter generation",
            "Application tracking", "50 applications / month (configurable)",
        ],
    },
    {
        "key": "premium", "name": "Premium", "price_inr": 99900, "price_usd": 1200, "sort_order": 2,
        "description": "Everything in Pro with higher limits and advanced AI matching.",
        "limits": {
            "matched_jobs_per_month": 1000, "applications_per_month": 200, "resume_customizations_per_month": 400,
            "cover_letters_per_month": 400, "discovery_interval_hours": 6, "max_resumes": 5,
            "csv_export": True, "auto_apply": True, "advanced_matching": True, "priority_processing": True,
        },
        "features": [
            "Everything in Pro", "Higher discovery limits", "Higher application allowance",
            "Multiple resume versions", "Advanced AI matching", "Priority job processing",
        ],
    },
]

# limits key -> (usage metric, period granularity)
LIMIT_METRICS = {
    "matched_jobs_per_month": "matched_jobs",
    "applications_per_month": "applications",
    "resume_customizations_per_month": "resume_customizations",
    "cover_letters_per_month": "cover_letters",
}
INT_LIMIT_KEYS = set(LIMIT_METRICS) | {"discovery_interval_hours", "max_resumes"}
BOOL_LIMIT_KEYS = {"csv_export", "auto_apply", "advanced_matching", "priority_processing"}


def validate_limits(limits: dict) -> dict:
    """Admin input validation. There is deliberately no 'unlimited' value."""
    clean: dict = {}
    for k, v in limits.items():
        if k in INT_LIMIT_KEYS:
            if isinstance(v, bool) or not isinstance(v, int) or v < 0 or v > 10_000_000:
                raise ValueError(f"{k} must be a non-negative integer (no unlimited plans)")
            clean[k] = v
        elif k in BOOL_LIMIT_KEYS:
            if not isinstance(v, bool):
                raise ValueError(f"{k} must be true or false")
            clean[k] = v
        else:
            raise ValueError(f"Unknown limit '{k}'")
    return clean


def current_period() -> str:
    return utcnow().strftime("%Y-%m")


def get_free_plan(db: Session) -> Plan:
    plan = db.execute(select(Plan).where(Plan.key == "free")).scalar_one_or_none()
    if plan is None:
        raise RuntimeError("Plans are not seeded. Run scripts/seed.py")
    return plan


def get_active_subscription(db: Session, user_id: uuid.UUID) -> Subscription | None:
    now = utcnow()
    subs = db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status.in_(["active", "trialing", "past_due", "canceled"]))
        .order_by(Subscription.created_at.desc())
    ).scalars()
    for sub in subs:
        end = sub.current_period_end
        if sub.status in ENTITLING_STATUSES:
            if end is None or end > now:
                return sub
        elif sub.status == "past_due" and end and end + timedelta(days=PAST_DUE_GRACE_DAYS) > now:
            return sub
        elif sub.status == "canceled" and sub.cancel_at_period_end and end and end > now:
            return sub  # cancelled but paid through the end of the period
    return None


def get_plan_for_user(db: Session, user: User) -> Plan:
    sub = get_active_subscription(db, user.id)
    if sub is not None:
        plan = db.get(Plan, sub.plan_id)
        if plan is not None:
            return plan
    return get_free_plan(db)


def get_usage(db: Session, user_id: uuid.UUID, metric: str, period: str | None = None) -> int:
    row = db.execute(
        select(UsageRecord.count).where(
            UsageRecord.user_id == user_id, UsageRecord.metric == metric, UsageRecord.period == (period or current_period())
        )
    ).scalar_one_or_none()
    return int(row or 0)


def increment_usage(db: Session, user_id: uuid.UUID, metric: str, amount: int = 1, period: str | None = None) -> None:
    period = period or current_period()
    stmt = (
        update(UsageRecord)
        .where(UsageRecord.user_id == user_id, UsageRecord.metric == metric, UsageRecord.period == period)
        .values(count=UsageRecord.count + amount, updated_at=utcnow())
    )
    if db.execute(stmt).rowcount:
        return
    try:
        with db.begin_nested():
            db.add(UsageRecord(user_id=user_id, metric=metric, period=period, count=amount))
            db.flush()
    except IntegrityError:  # concurrent insert won the race
        db.execute(stmt)


def require_feature(db: Session, user: User, feature: str, message: str | None = None) -> Plan:
    plan = get_plan_for_user(db, user)
    if not plan.limits.get(feature):
        raise QuotaExceeded(
            message or "This feature is not included in your plan. Upgrade to unlock it.",
            code="feature_not_in_plan",
            details={"feature": feature, "plan": plan.key},
        )
    return plan


def remaining(db: Session, user: User, limit_key: str) -> int:
    plan = get_plan_for_user(db, user)
    limit = int(plan.limits.get(limit_key, 0))
    used = get_usage(db, user.id, LIMIT_METRICS[limit_key])
    return max(limit - used, 0)


def ensure_quota(db: Session, user: User, limit_key: str, amount: int = 1) -> Plan:
    plan = get_plan_for_user(db, user)
    limit = int(plan.limits.get(limit_key, 0))
    used = get_usage(db, user.id, LIMIT_METRICS[limit_key])
    if used + amount > limit:
        raise QuotaExceeded(
            f"Your {plan.name} plan allows {limit} per month and {used} have been used."
            + (" Upgrade for a higher allowance." if plan.key != "premium" else ""),
            code="quota_exceeded",
            details={"limit_key": limit_key, "limit": limit, "used": used, "plan": plan.key},
        )
    return plan


def usage_summary(db: Session, user: User) -> dict:
    plan = get_plan_for_user(db, user)
    out = {}
    for limit_key, metric in LIMIT_METRICS.items():
        limit = int(plan.limits.get(limit_key, 0))
        used = get_usage(db, user.id, metric)
        out[limit_key] = {"limit": limit, "used": used, "remaining": max(limit - used, 0)}
    return out
