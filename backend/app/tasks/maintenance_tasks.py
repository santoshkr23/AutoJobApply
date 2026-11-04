"""Periodic housekeeping (queue: default)."""

import logging
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.db import session_scope
from app.tasks.celery_app import ReliableTask, celery_app

log = logging.getLogger(__name__)


@celery_app.task(base=ReliableTask, name="app.tasks.maintenance_tasks.sync_subscriptions")
def sync_subscriptions() -> int:
    """Expire subscriptions whose paid period (plus grace) is over; notify once."""
    from app.models import Subscription, User
    from app.models.base import utcnow
    from app.services.notifications import notify
    from app.services.quotas import PAST_DUE_GRACE_DAYS

    n = 0
    now = utcnow()
    with session_scope() as db:
        for sub in db.execute(select(Subscription).where(Subscription.status.in_(["active", "trialing", "past_due", "canceled"]))).scalars():
            end = sub.current_period_end
            if end is None:
                continue
            grace = timedelta(days=PAST_DUE_GRACE_DAYS) if sub.status == "past_due" else timedelta(0)
            if end + grace < now and sub.status != "expired":
                was_canceled = sub.status == "canceled"
                sub.status = "expired"
                n += 1
                user = db.get(User, sub.user_id)
                if user and not was_canceled:
                    notify(db, user, "subscription_expiry", "Subscription expired",
                           "Your subscription has ended and your account moved to the Free plan.", {})
    return n


@celery_app.task(base=ReliableTask, name="app.tasks.maintenance_tasks.send_interview_reminders")
def send_interview_reminders() -> int:
    from app.models import Application, ApplicationEvent, Job, User
    from app.models.base import utcnow
    from app.services.notifications import notify

    n = 0
    now = utcnow()
    with session_scope() as db:
        rows = db.execute(select(Application).where(
            Application.status == "INTERVIEW", Application.deleted_at.is_(None), Application.interview_at.is_not(None),
            Application.interview_at > now, Application.interview_at <= now + timedelta(hours=24))).scalars().all()
        for a in rows:
            already = db.execute(select(ApplicationEvent.id).where(
                ApplicationEvent.application_id == a.id, ApplicationEvent.event_type == "interview_reminder")).first()
            if already:
                continue
            user, job = db.get(User, a.user_id), db.get(Job, a.job_id)
            notify(db, user, "interview_reminder", f"Interview soon: {job.title} at {job.company}",
                   f"Your interview is scheduled for {a.interview_at:%Y-%m-%d %H:%M} UTC.", {"application_id": str(a.id)})
            from app.services.applications import add_event
            add_event(db, a, "interview_reminder", "Reminder sent")
            n += 1
    return n


@celery_app.task(base=ReliableTask, name="app.tasks.maintenance_tasks.retention_cleanup")
def retention_cleanup() -> dict:
    """Delete expired tokens/sessions, old audit logs and old failed-task records per retention settings."""
    from app.models import AuditLog, EmailToken, FailedTask
    from app.models.base import utcnow
    from app.models.user import AuthSession as UserSession

    s = get_settings()
    now = utcnow()
    with session_scope() as db:
        tokens = db.execute(delete(EmailToken).where(EmailToken.expires_at < now - timedelta(days=7))).rowcount
        sessions = db.execute(delete(UserSession).where(UserSession.expires_at < now - timedelta(days=7))).rowcount
        audit_n = db.execute(delete(AuditLog).where(AuditLog.created_at < now - timedelta(days=s.retention_audit_log_days))).rowcount
        failed = db.execute(delete(FailedTask).where(FailedTask.created_at < now - timedelta(days=90))).rowcount
    return {"email_tokens": tokens, "sessions": sessions, "audit_logs": audit_n, "failed_tasks": failed}
