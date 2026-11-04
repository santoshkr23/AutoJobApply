"""Application submission tasks (queue: automation)."""

import uuid

from app.core.db import session_scope
from app.tasks.celery_app import ReliableTask, celery_app


@celery_app.task(base=ReliableTask, bind=True, name="app.tasks.application_tasks.submit_application", max_retries=3)
def submit_application(self, application_id: str) -> str:
    from app.services.submission import RetryLater, submit_now

    try:
        with session_scope() as db:
            return submit_now(db, uuid.UUID(application_id))
    except RetryLater as exc:
        raise self.retry(exc=exc, countdown=min(60 * 2 ** self.request.retries, 900)) from exc
