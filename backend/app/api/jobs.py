"""Job browsing/search. Jobs are shared reference data; match scores are per user."""

import uuid

from fastapi import APIRouter, Query

from app.core.deps import DB, VerifiedUser
from app.core.errors import NotFound
from app.models.job import Job, JobMatch, JobSource
from app.schemas.jobs import JobDetailOut, JobOut, JobPage
from app.services.jobs_service import JobFilters, search_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


def job_out(job: Job, source_name: str, score: int | None) -> JobOut:
    return JobOut(
        id=job.id, title=job.title, company=job.company, location_text=job.location_text, country=job.country,
        city=job.city, work_mode=job.work_mode, salary_min=job.salary_min, salary_max=job.salary_max,
        salary_currency=job.salary_currency, salary_period=job.salary_period, employment_type=job.employment_type,
        experience_min=job.experience_min, experience_max=job.experience_max, skills=list(job.skills or []),
        category=job.category, url=job.url, posted_at=job.posted_at, expires_at=job.expires_at, source=source_name,
        attribution=job.attribution, is_sample=job.is_sample, match_score=score,
    )


@router.get("", response_model=JobPage)
def list_jobs(
    db: DB,
    user: VerifiedUser,
    q: str | None = Query(default=None, max_length=100),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    work_mode: str | None = Query(default=None, pattern="^(remote|hybrid|onsite)$"),
    category: str | None = Query(default=None, max_length=64),
    employment_type: str | None = Query(default=None, max_length=32),
    min_salary: int | None = Query(default=None, ge=0),
    posted_within_days: int | None = Query(default=None, ge=1, le=365),
    source: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=20, ge=1, le=100),
) -> JobPage:
    filters = JobFilters(q, country, work_mode, category, employment_type, min_salary, posted_within_days, source)
    rows, total = search_jobs(db, filters, page, page_size, user.id)
    return JobPage(items=[job_out(j, name, score) for j, name, score in rows], total=total, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job(job_id: uuid.UUID, db: DB, user: VerifiedUser) -> JobDetailOut:
    job = db.get(Job, job_id)
    if job is None or job.status == "duplicate":
        raise NotFound("Job not found")
    source = db.get(JobSource, job.source_id)
    match = db.query(JobMatch).filter(JobMatch.user_id == user.id, JobMatch.job_id == job.id).one_or_none()
    base = job_out(job, source.name if source else "", match.score if match else None)
    return JobDetailOut(**base.model_dump(), description=job.description, analysis=job.analysis, visa_sponsorship=job.visa_sponsorship)
