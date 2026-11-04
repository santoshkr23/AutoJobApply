"""In-app notifications with optional email delivery that honours the user's preferences."""

import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.misc import Notification
from app.models.user import User, UserPreferences

NOTIFICATION_TYPES: dict[str, str] = {
    "high_match_jobs": "New high-match jobs",
    "resume_generated": "Resume generation completed",
    "application_submitted": "Application submitted",
    "manual_required": "Manual application required",
    "interview_reminder": "Interview reminders",
    "subscription_payment": "Subscription payments",
    "subscription_expiry": "Subscription expiry",
}


def default_prefs() -> dict:
    return {t: {"email": True, "in_app": True} for t in NOTIFICATION_TYPES}


def effective_prefs(db: Session, user_id: uuid.UUID) -> dict:
    prefs = default_prefs()
    row = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).one_or_none()
    if row and row.notification_prefs:
        for t, v in row.notification_prefs.items():
            if t in prefs and isinstance(v, dict):
                prefs[t].update({k: bool(val) for k, val in v.items() if k in ("email", "in_app")})
    return prefs


def notify(
    db: Session,
    user: User,
    type_: str,
    title: str,
    body: str,
    data: dict | None = None,
    *,
    always_email: bool = False,
) -> Notification | None:
    """Create a notification; email delivery is queued after the transaction commits."""
    prefs = effective_prefs(db, user.id).get(type_, {"email": True, "in_app": True})
    send_email = always_email or prefs.get("email", True)
    if not prefs.get("in_app", True) and not send_email:
        return None
    n = Notification(
        user_id=user.id,
        type=type_,
        title=title,
        body=body,
        data=data or {},
        email_status="pending" if send_email else "skipped",
        created_at=utcnow(),
    )
    db.add(n)
    db.flush()
    if send_email:
        notification_id = str(n.id)

        @event.listens_for(db, "after_commit", once=True)
        def _enqueue(_session):  # noqa: ANN001
            from app.tasks.celery_app import enqueue
            from app.tasks.email_tasks import send_notification_email

            enqueue(send_notification_email, notification_id)

    return n
