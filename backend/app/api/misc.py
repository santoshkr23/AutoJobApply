"""Notifications, dashboard statistics and the public contact form."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.core.deps import DB, VerifiedUser
from app.core.errors import NotFound
from app.core.ratelimit import rate_limit
from app.models import Application, Job, JobMatch, Notification, SupportRequest
from app.models.base import utcnow
from app.services import quotas
from app.services.notifications import NOTIFICATION_TYPES

router = APIRouter(tags=["misc"])


@router.get("/notifications")
def notifications(db: DB, user: VerifiedUser, unread_only: bool = False, limit: int = Query(default=30, ge=1, le=100)) -> dict:
    cond = [Notification.user_id == user.id]
    if unread_only:
        cond.append(Notification.read_at.is_(None))
    rows = db.execute(select(Notification).where(*cond).order_by(Notification.created_at.desc()).limit(limit)).scalars()
    unread = db.execute(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))).scalar_one()
    return {"unread": unread, "items": [{"id": str(n.id), "type": n.type, "title": n.title, "body": n.body, "data": n.data,
                                         "read": n.read_at is not None, "created_at": n.created_at} for n in rows]}


@router.post("/notifications/{nid}/read")
def mark_read(nid: uuid.UUID, db: DB, user: VerifiedUser) -> dict:
    n = db.get(Notification, nid)
    if n is None or n.user_id != user.id:
        raise NotFound("Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_read(db: DB, user: VerifiedUser) -> dict:
    for n in db.execute(select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))).scalars():
        n.read_at = utcnow()
    db.commit()
    return {"ok": True}


@router.get("/notification-types")
def notification_types() -> dict:
    return NOTIFICATION_TYPES


@router.get("/dashboard")
def dashboard(db: DB, user: VerifiedUser) -> dict:
    by_status = dict(db.execute(select(Application.status, func.count()).where(Application.user_id == user.id, Application.deleted_at.is_(None))
                                .group_by(Application.status)).all())
    since = utcnow() - timedelta(days=30)
    daily = db.execute(select(func.date(Application.created_at), func.count()).where(Application.user_id == user.id, Application.deleted_at.is_(None),
                                                                                    Application.created_at >= since)
                       .group_by(func.date(Application.created_at)).order_by(func.date(Application.created_at))).all()
    buckets = {"90-100": (90, 101), "80-89": (80, 90), "70-79": (70, 80), "<70": (0, 70)}
    dist = {k: db.execute(select(func.count()).select_from(JobMatch).where(JobMatch.user_id == user.id, JobMatch.score >= lo, JobMatch.score < hi,
                                                                            JobMatch.status != "dismissed")).scalar_one()
            for k, (lo, hi) in buckets.items()}
    top = db.execute(select(JobMatch, Job).join(Job, Job.id == JobMatch.job_id).where(JobMatch.user_id == user.id, JobMatch.status == "new")
                     .order_by(JobMatch.score.desc()).limit(5)).all()
    recent = db.execute(select(Application, Job).join(Job, Job.id == Application.job_id).where(Application.user_id == user.id, Application.deleted_at.is_(None))
                        .order_by(Application.updated_at.desc()).limit(8)).all()
    total_matches = db.execute(select(func.count()).select_from(JobMatch).where(JobMatch.user_id == user.id)).scalar_one()
    return {
        "totals": {"matches": total_matches, "applications": sum(by_status.values()), "applied": by_status.get("APPLIED", 0),
                   "interviews": by_status.get("INTERVIEW", 0), "offers": by_status.get("OFFER", 0),
                   "needs_action": by_status.get("MANUAL_REQUIRED", 0) + by_status.get("PENDING_APPROVAL", 0)},
        "applications_by_status": by_status, "applications_per_day": [{"date": str(d), "count": c} for d, c in daily],
        "match_score_distribution": dist, "usage": quotas.usage_summary(db, user),
        "top_matches": [{"match_id": str(m.id), "job_id": str(j.id), "score": m.score, "title": j.title, "company": j.company} for m, j in top],
        "recent_applications": [{"id": str(a.id), "status": a.status, "title": j.title, "company": j.company, "updated_at": a.updated_at} for a, j in recent],
    }


class ContactIn(BaseModel):
    email: EmailStr
    subject: str = Field(min_length=3, max_length=200)
    message: str = Field(min_length=10, max_length=5000)


@router.post("/contact", status_code=201, dependencies=[Depends(rate_limit("contact", 5))])
def contact(body: ContactIn, request: Request, db: DB) -> dict:
    db.add(SupportRequest(email=body.email.lower(), subject=body.subject.strip(), message=body.message.strip(), status="open"))
    db.commit()
    return {"message": "Thanks - we received your message."}
