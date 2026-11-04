"""Job discovery tasks (queue: discovery)."""

import logging
import uuid

from app.core.db import session_scope
from app.tasks.celery_app import ReliableTask, celery_app, enqueue

log = logging.getLogger(__name__)


@celery_app.task(base=ReliableTask, name="app.tasks.job_tasks.discover_source", max_retries=2)
def discover_source(source_id: str) -> dict:
    from app.models.job import JobSource
    from app.services.jobs_service import run_source

    with session_scope() as db:
        source = db.get(JobSource, uuid.UUID(source_id))
        if source is None or not source.enabled:
            return {"skipped": True}
        run = run_source(db, source)
        return {"status": run.status, "created": run.created, "updated": run.updated, "duplicates": run.duplicates}


@celery_app.task(base=ReliableTask, name="app.tasks.job_tasks.run_scheduled_discovery")
def run_scheduled_discovery() -> int:
    """Beat entrypoint: enqueue every enabled source whose interval has elapsed."""
    from app.services.jobs_service import due_sources

    with session_scope() as db:
        ids = [str(s.id) for s in due_sources(db)]
    for sid in ids:
        enqueue(discover_source, sid)
    return len(ids)


@celery_app.task(base=ReliableTask, name="app.tasks.job_tasks.expire_stale_jobs")
def expire_stale_jobs_task() -> int:
    from app.services.jobs_service import expire_stale_jobs

    with session_scope() as db:
        return expire_stale_jobs(db)
