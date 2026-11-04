"""AI-heavy background tasks (queue: ai)."""

import logging
import uuid

from app.core.db import session_scope
from app.tasks.celery_app import ReliableTask, celery_app

log = logging.getLogger(__name__)


@celery_app.task(base=ReliableTask, name="app.tasks.ai_tasks.parse_resume_task", max_retries=2)
def parse_resume_task(resume_id: str) -> None:
    from app.services.resumes import parse_resume_now

    with session_scope() as db:
        parse_resume_now(db, uuid.UUID(resume_id))


@celery_app.task(base=ReliableTask, name="app.tasks.ai_tasks.match_user", max_retries=2)
def match_user(user_id: str) -> None:
    from app.models import User
    from app.services import matching
    from app.services.notifications import notify

    with session_scope() as db:
        user = db.get(User, uuid.UUID(user_id))
        if user is None or user.deleted_at is not None:
            return
        try:
            stats = matching.match_user_now(db, user)
        except matching.ProfileMissing:
            return
        if stats.saved:
            notify(db, user, "new_matches", f"{stats.saved} new job match(es)",
                   "We found new jobs that match your profile.", {"count": stats.saved})


@celery_app.task(base=ReliableTask, name="app.tasks.ai_tasks.match_all_users")
def match_all_users() -> int:
    """Beat entry: queue matching for users whose plan frequency says it is due."""
    from datetime import timedelta

    from sqlalchemy import select

    from app.models import User, UserPreferences
    from app.models.base import utcnow
    from app.services import quotas

    queued = 0
    with session_scope() as db:
        rows = db.execute(
            select(User, UserPreferences).join(UserPreferences, UserPreferences.user_id == User.id)
            .where(User.deleted_at.is_(None), User.email_verified_at.is_not(None))
        ).all()
        for user, prefs in rows:
            hours = int(quotas.get_plan_for_user(db, user).limits.get("discovery_interval_hours", 24))
            if prefs.last_match_run_at is None or prefs.last_match_run_at <= utcnow() - timedelta(hours=hours):
                match_user.delay(str(user.id))
                queued += 1
    return queued
