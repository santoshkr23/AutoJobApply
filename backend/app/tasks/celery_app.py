"""Celery application: reliable background processing for discovery, AI, automation and email."""

import logging
import traceback

from celery import Celery, Task
from celery.signals import task_failure

from app.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "career",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.email_tasks",
        "app.tasks.job_tasks",
        "app.tasks.ai_tasks",
        "app.tasks.application_tasks",
        "app.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=False,
    task_acks_late=True,  # a crashed worker returns the task to the queue
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    task_default_queue="default",
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    timezone="UTC",
    task_routes={
        "app.tasks.ai_tasks.*": {"queue": "ai"},
        "app.tasks.application_tasks.*": {"queue": "automation"},
        "app.tasks.email_tasks.*": {"queue": "default"},
        "app.tasks.job_tasks.*": {"queue": "discovery"},
        "app.tasks.maintenance_tasks.*": {"queue": "default"},
    },
)

# Periodic schedule (run `celery beat`). Intervals per source are enforced inside the tasks.
celery_app.conf.beat_schedule = {
    "discover-jobs": {"task": "app.tasks.job_tasks.run_scheduled_discovery", "schedule": 900.0},
    "match-new-jobs": {"task": "app.tasks.ai_tasks.match_all_users", "schedule": 3600.0},
    "expire-jobs": {"task": "app.tasks.job_tasks.expire_stale_jobs", "schedule": 6 * 3600.0},
    "sync-subscriptions": {"task": "app.tasks.maintenance_tasks.sync_subscriptions", "schedule": 3600.0},
    "interview-reminders": {"task": "app.tasks.maintenance_tasks.send_interview_reminders", "schedule": 3600.0},
    "retention-cleanup": {"task": "app.tasks.maintenance_tasks.retention_cleanup", "schedule": 24 * 3600.0},
}


class ReliableTask(Task):
    """Base task: exponential-backoff retries; exhausted tasks land in the failed_tasks table."""

    autoretry_for = (Exception,)
    retry_backoff = 5
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 3


@task_failure.connect
def _record_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, einfo=None, **_):
    """Dead-letter record once a task has failed for good."""
    try:
        retries = getattr(getattr(sender, "request", None), "retries", 0) or 0
        max_retries = getattr(sender, "max_retries", 0) or 0
        if retries < max_retries and getattr(sender, "autoretry_for", None):
            return  # will be retried; only record the final failure
        from app.core.db import session_scope
        from app.models.base import utcnow
        from app.models.misc import FailedTask

        with session_scope() as db:
            db.add(
                FailedTask(
                    task_name=getattr(sender, "name", "unknown"),
                    task_id=task_id,
                    args_summary=(repr(args)[:300] + " " + repr(list((kwargs or {}).keys()))),
                    error=("".join(traceback.format_exception_only(type(exception), exception)))[:4000],
                    retries=retries,
                    created_at=utcnow(),
                )
            )
    except Exception:  # never let the dead-letter recorder crash the worker
        log.exception("Could not record failed task")


def enqueue_after_commit(db, task, *args, **kwargs) -> None:
    """Queue `task` only once the current transaction has committed (the worker must see the rows)."""
    from sqlalchemy import event

    @event.listens_for(db, "after_commit", once=True)
    def _go(_session):  # noqa: ANN001
        enqueue(task, *args, **kwargs)


def enqueue(task, *args, **kwargs):
    """Queue a task. A broker outage must not break the API request that triggered it."""
    try:
        return task.delay(*args, **kwargs)
    except Exception:
        log.exception("Failed to enqueue %s", getattr(task, "name", task))
        return None
