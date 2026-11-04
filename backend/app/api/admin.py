"""Admin API. Admins are a separate identity (admin_users) with their own session cookie; users can never reach these routes."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select

from app.api.auth import clear_session_cookies, set_session_cookies
from app.core.audit import audit
from app.core.config import get_settings
from app.core.db import session_scope  # noqa: F401
from app.core.deps import DB, CurrentAdmin
from app.core.errors import AppError, NotFound, Unauthorized
from app.core.ratelimit import client_ip, rate_limit
from app.core.security import verify_password
from app.models import (
    Application,
    AuditLog,
    FailedTask,
    FeatureFlag,
    Job,
    JobMatch,
    JobSource,
    Payment,
    Plan,
    Subscription,
    SupportRequest,
    User,
)
from app.models.base import utcnow
from app.models.user import AdminUser
from app.services import jobs_service, quotas
from app.services import settings_store as store
from app.services.billing import service as billing
from app.services.sessions import create_session, revoke_session

router = APIRouter(prefix="/admin", tags=["admin"])
ADMIN_CSRF = "admin_csrf"


class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", dependencies=[Depends(rate_limit("admin_login", 5))])
def login(body: AdminLoginIn, request: Request, response: Response, db: DB) -> dict:
    s = get_settings()
    admin = db.execute(select(AdminUser).where(AdminUser.email == body.email.lower())).scalar_one_or_none()
    if not verify_password(body.password, admin.password_hash if admin else None) or admin is None or not admin.is_active:
        audit(db, action="admin.login_failed", request=request)
        db.commit()
        raise Unauthorized("Invalid email or password")
    token, row = create_session(db, subject_type="admin", subject_id=admin.id, ip=client_ip(request), user_agent=request.headers.get("user-agent"))
    admin.last_login_at = utcnow()
    set_session_cookies(response, token, row.csrf_token, s.admin_session_ttl_hours * 3600, cookie_name="admin_session", csrf_cookie=ADMIN_CSRF)
    audit(db, action="admin.login", actor_type="admin", actor_id=admin.id, request=request)
    db.commit()
    return {"admin": {"id": str(admin.id), "email": admin.email, "role": admin.role}, "csrf_token": row.csrf_token,
            "token": token if request.headers.get("x-return-token") == "1" else None}


@router.post("/logout")
def logout(request: Request, response: Response, db: DB, admin: CurrentAdmin) -> dict:
    revoke_session(db, request.state.session)
    db.commit()
    clear_session_cookies(response, cookie_name="admin_session", csrf_cookie=ADMIN_CSRF)
    return {"message": "Signed out"}


@router.get("/me")
def me(admin: CurrentAdmin) -> dict:
    return {"id": str(admin.id), "email": admin.email, "role": admin.role, "full_name": admin.full_name}


def _require_role(admin: AdminUser, *roles: str) -> None:
    if admin.role not in roles:
        raise AppError("Your admin role cannot do this.", code="forbidden", status_code=403)


# ----------------------------------------------------------------------------- overview
@router.get("/stats")
def stats(db: DB, admin: CurrentAdmin) -> dict:
    def count(model, *where):
        return db.execute(select(func.count()).select_from(model).where(*where)).scalar_one()

    by_status = dict(db.execute(select(Application.status, func.count()).group_by(Application.status)).all())
    plans = dict(db.execute(select(Plan.key, func.count()).select_from(Subscription).join(Plan, Plan.id == Subscription.plan_id)
                            .where(Subscription.status.in_(["active", "past_due"])).group_by(Plan.key)).all())
    mrr = db.execute(select(func.coalesce(func.sum(Plan.price_inr), 0)).select_from(Subscription).join(Plan, Plan.id == Subscription.plan_id)
                     .where(Subscription.status == "active", Subscription.provider != "sandbox")).scalar_one()
    return {
        "users": {"total": count(User, User.deleted_at.is_(None)), "verified": count(User, User.email_verified_at.is_not(None), User.deleted_at.is_(None))},
        "jobs": {"active": count(Job, Job.status == "active"), "expired": count(Job, Job.status == "expired")},
        "matches": count(JobMatch), "applications": by_status, "paid_subscriptions": plans,
        "mrr_inr_paise": int(mrr), "failed_tasks": count(FailedTask), "open_support": count(SupportRequest, SupportRequest.status == "open"),
    }


@router.get("/health")
def health(db: DB, admin: CurrentAdmin) -> dict:
    s = get_settings()
    out = {"environment": s.environment, "ai_provider": s.ai_provider, "ai_configured": s.ai_provider == "mock" or bool(s.openai_api_key),
           "email_provider": s.email_provider, "storage_backend": s.storage_backend, "billing": billing.available_providers()}
    try:
        import redis
        redis.Redis.from_url(s.redis_url, socket_connect_timeout=1).ping()
        out["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        out["redis"] = f"error: {type(exc).__name__}"
    return out


# ----------------------------------------------------------------------------- users
@router.get("/users")
def users(db: DB, admin: CurrentAdmin, q: str | None = Query(default=None, max_length=100), page: int = Query(default=1, ge=1),
          page_size: int = Query(default=25, ge=1, le=100)) -> dict:
    cond = [User.deleted_at.is_(None)]
    if q:
        cond.append(or_(User.email.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    total = db.execute(select(func.count()).select_from(User).where(*cond)).scalar_one()
    rows = db.execute(select(User).where(*cond).order_by(User.created_at.desc()).limit(page_size).offset((page - 1) * page_size)).scalars()
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {"id": str(u.id), "email": u.email, "full_name": u.full_name, "is_active": u.is_active, "verified": u.email_verified_at is not None,
         "plan": quotas.get_plan_for_user(db, u).key, "created_at": u.created_at, "last_login_at": u.last_login_at} for u in rows]}


class UserPatch(BaseModel):
    is_active: bool


@router.patch("/users/{user_id}")
def patch_user(user_id: uuid.UUID, body: UserPatch, request: Request, db: DB, admin: CurrentAdmin) -> dict:
    _require_role(admin, "superadmin", "admin")
    u = db.get(User, user_id)
    if u is None or u.deleted_at is not None:
        raise NotFound("User not found")
    u.is_active = body.is_active
    if not body.is_active:
        from app.services.sessions import revoke_all_for_subject
        revoke_all_for_subject(db, "user", u.id)
    audit(db, action="admin.user_active_changed", actor_type="admin", actor_id=admin.id, target_type="user", target_id=u.id,
          request=request, meta={"is_active": body.is_active})
    db.commit()
    return {"id": str(u.id), "is_active": u.is_active}


# ----------------------------------------------------------------------------- plans
class PlanPatch(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    description: str | None = None
    price_inr: int | None = Field(default=None, ge=0, le=100_000_000)
    price_usd: int | None = Field(default=None, ge=0, le=100_000_000)
    limits: dict | None = None
    features: list[str] | None = None
    is_active: bool | None = None
    razorpay_plan_id: str | None = Field(default=None, max_length=64)
    stripe_price_id: str | None = Field(default=None, max_length=64)


@router.get("/plans")
def admin_plans(db: DB, admin: CurrentAdmin) -> list[dict]:
    return [{"key": p.key, "name": p.name, "description": p.description, "price_inr": p.price_inr, "price_usd": p.price_usd, "limits": p.limits,
             "features": p.features, "is_active": p.is_active, "razorpay_plan_id": p.razorpay_plan_id, "stripe_price_id": p.stripe_price_id}
            for p in db.execute(select(Plan).order_by(Plan.sort_order)).scalars()]


@router.patch("/plans/{key}")
def patch_plan(key: str, body: PlanPatch, request: Request, db: DB, admin: CurrentAdmin) -> dict:
    _require_role(admin, "superadmin", "admin")
    p = db.execute(select(Plan).where(Plan.key == key)).scalar_one_or_none()
    if p is None:
        raise NotFound("Plan not found")
    data = body.model_dump(exclude_unset=True)
    if "limits" in data:
        try:
            p.limits = quotas.validate_limits({**p.limits, **data.pop("limits")})
        except ValueError as exc:
            raise AppError(str(exc), code="validation_error", status_code=422) from exc
    for k, v in data.items():
        setattr(p, k, v)
    audit(db, action="admin.plan_updated", actor_type="admin", actor_id=admin.id, target_type="plan", target_id=p.id, request=request)
    db.commit()
    return {"key": p.key, "limits": p.limits}


# ----------------------------------------------------------------------------- job sources
class SourcePatch(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    config: dict | None = None


def _src(s: JobSource) -> dict:
    return {"id": str(s.id), "key": s.key, "name": s.name, "connector_type": s.connector_type, "enabled": s.enabled,
            "interval_minutes": s.interval_minutes, "last_run_at": s.last_run_at, "last_status": s.last_status, "last_error": s.last_error,
            "consecutive_failures": s.consecutive_failures, "terms_url": s.terms_url, "terms_note": s.terms_note}


@router.get("/sources")
def sources(db: DB, admin: CurrentAdmin) -> list[dict]:
    return [_src(s) for s in db.execute(select(JobSource).order_by(JobSource.key)).scalars()]


@router.patch("/sources/{source_id}")
def patch_source(source_id: uuid.UUID, body: SourcePatch, request: Request, db: DB, admin: CurrentAdmin) -> dict:
    _require_role(admin, "superadmin", "admin")
    s = db.get(JobSource, source_id)
    if s is None:
        raise NotFound("Source not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    audit(db, action="admin.source_updated", actor_type="admin", actor_id=admin.id, target_type="job_source", target_id=s.id, request=request)
    db.commit()
    return _src(s)


@router.post("/sources/{source_id}/run")
def run_source_now(source_id: uuid.UUID, db: DB, admin: CurrentAdmin) -> dict:
    s = db.get(JobSource, source_id)
    if s is None:
        raise NotFound("Source not found")
    run = jobs_service.run_source(db, s)
    db.commit()
    return {"status": run.status, "fetched": run.fetched, "created": run.created, "updated": run.updated, "error": run.error}


# ----------------------------------------------------------------------------- logs, payments, flags, settings, support
@router.get("/audit-logs")
def audit_logs(db: DB, admin: CurrentAdmin, action: str | None = Query(default=None, max_length=80), page: int = Query(default=1, ge=1),
               page_size: int = Query(default=50, ge=1, le=200)) -> dict:
    cond = [AuditLog.action.like(f"{action}%")] if action else []
    total = db.execute(select(func.count()).select_from(AuditLog).where(*cond)).scalar_one()
    rows = db.execute(select(AuditLog).where(*cond).order_by(AuditLog.created_at.desc()).limit(page_size).offset((page - 1) * page_size)).scalars()
    return {"total": total, "items": [{"at": r.created_at, "actor_type": r.actor_type, "actor_id": str(r.actor_id) if r.actor_id else None,
                                       "action": r.action, "target": f"{r.target_type}:{r.target_id}" if r.target_type else None, "ip": r.ip_address,
                                       "meta": r.meta} for r in rows]}


@router.get("/failed-tasks")
def failed_tasks(db: DB, admin: CurrentAdmin) -> list[dict]:
    rows = db.execute(select(FailedTask).order_by(FailedTask.created_at.desc()).limit(100)).scalars()
    return [{"at": r.created_at, "task": r.task_name, "error": r.error[:500], "retries": r.retries} for r in rows]


@router.get("/payments")
def admin_payments(db: DB, admin: CurrentAdmin, page: int = Query(default=1, ge=1)) -> list[dict]:
    rows = db.execute(select(Payment).order_by(Payment.created_at.desc()).limit(50).offset((page - 1) * 50)).scalars()
    return [{"id": str(p.id), "user_id": str(p.user_id), "amount": p.amount, "currency": p.currency, "status": p.status, "provider": p.provider,
             "invoice_number": p.invoice_number, "refunded_amount": p.refunded_amount, "paid_at": p.paid_at} for p in rows]


class RefundIn(BaseModel):
    amount: int | None = Field(default=None, gt=0)


@router.post("/payments/{payment_id}/refund")
def refund(payment_id: uuid.UUID, body: RefundIn, db: DB, admin: CurrentAdmin) -> dict:
    _require_role(admin, "superadmin", "admin")
    p = db.get(Payment, payment_id)
    if p is None:
        raise NotFound("Payment not found")
    billing.refund_payment(db, p, body.amount, admin.id)
    db.commit()
    return {"status": p.status, "refunded_amount": p.refunded_amount}


class FlagIn(BaseModel):
    enabled: bool
    description: str | None = Field(default=None, max_length=255)


@router.get("/feature-flags")
def flags(db: DB, admin: CurrentAdmin) -> list[dict]:
    return [{"key": f.key, "enabled": f.enabled, "description": f.description} for f in db.execute(select(FeatureFlag).order_by(FeatureFlag.key)).scalars()]


@router.put("/feature-flags/{key}")
def set_flag(key: str, body: FlagIn, db: DB, admin: CurrentAdmin) -> dict:
    _require_role(admin, "superadmin", "admin")
    f = db.execute(select(FeatureFlag).where(FeatureFlag.key == key)).scalar_one_or_none()
    if f is None:
        raise NotFound("Unknown flag")
    f.enabled = body.enabled
    if body.description is not None:
        f.description = body.description
    audit(db, action="admin.flag_changed", actor_type="admin", actor_id=admin.id, target_type="feature_flag", target_id=key, meta={"enabled": body.enabled})
    db.commit()
    return {"key": f.key, "enabled": f.enabled}


@router.get("/settings/matching-weights")
def get_weights(db: DB, admin: CurrentAdmin) -> dict:
    return store.matching_weights(db)


@router.put("/settings/matching-weights")
def set_weights(body: dict[str, float], db: DB, admin: CurrentAdmin) -> dict:
    _require_role(admin, "superadmin", "admin")
    known = set(store.DEFAULT_MATCHING_WEIGHTS)
    if set(body) - known or any(v < 0 or v > 100 for v in body.values()):
        raise AppError(f"Weights must be 0-100 for: {sorted(known)}", code="validation_error", status_code=422)
    store.set_setting(db, "matching_weights", {**store.matching_weights(db), **body})
    audit(db, action="admin.weights_changed", actor_type="admin", actor_id=admin.id)
    db.commit()
    return store.matching_weights(db)


@router.get("/support")
def support(db: DB, admin: CurrentAdmin, status: str | None = Query(default=None, pattern="^(open|closed)$")) -> list[dict]:
    q = select(SupportRequest).order_by(SupportRequest.created_at.desc()).limit(100)
    if status:
        q = q.where(SupportRequest.status == status)
    return [{"id": str(r.id), "email": r.email, "subject": r.subject, "message": r.message, "status": r.status, "created_at": r.created_at}
            for r in db.execute(q).scalars()]


@router.patch("/support/{rid}")
def close_support(rid: uuid.UUID, db: DB, admin: CurrentAdmin) -> dict:
    r = db.get(SupportRequest, rid)
    if r is None:
        raise NotFound("Request not found")
    r.status = "closed"
    db.commit()
    return {"id": str(r.id), "status": r.status}
