import logging
import uuid

from app.core.db import session_scope
from app.models.base import utcnow
from app.models.misc import Notification
from app.services import email as email_service
from app.tasks.celery_app import ReliableTask, celery_app

log = logging.getLogger(__name__)


@celery_app.task(base=ReliableTask, name="app.tasks.email_tasks.send_email_task")
def send_email_task(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Transactional email (verification, password reset). Retried with backoff on failure."""
    email_service.send_email(to, subject, text, html)


@celery_app.task(base=ReliableTask, name="app.tasks.email_tasks.send_notification_email")
def send_notification_email(notification_id: str) -> None:
    from app.models.user import User

    with session_scope() as db:
        n = db.get(Notification, uuid.UUID(notification_id))
        if n is None or n.email_status != "pending":
            return
        user = db.get(User, n.user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            n.email_status = "skipped"
            return
        text, html = email_service.render(n.title, [n.body])
        try:
            email_service.send_email(user.email, n.title, text, html)
        except Exception as exc:
            n.email_status = "failed"
            n.email_error = str(exc)[:500]
            raise
        n.email_status = "sent"
        n.email_sent_at = utcnow()
