"""Per-user job matches. All queries are scoped to the current user."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.jobs import job_out
from app.core.deps import DB, VerifiedUser
from app.core.errors import NotFound
from app.core.ratelimit import rate_limit
from app.models.job import Job, JobMatch, JobSource
from app.schemas.matches import MatchOut, MatchPage, MatchRunOut, MatchStatusIn
from app.services import matching

router = APIRouter(prefix="/matches", tags=["matches"])
STATUSES = {"new", "saved", "dismissed"}


def match_out(m: JobMatch, job: Job, source_name: str) -> MatchOut:
    d = m.details or {}
    return MatchOut(
        id=m.id, score=m.score, status=m.status, recommendation=d.get("recommendation", ""),
        skills_matched=d.get("skills_matched", []), missing_skills=d.get("missing_skills", []),
        experience_match=d.get("experience_match", {}), location_match=d.get("location_match", {}),
        salary_match=d.get("salary_match", {}), explanation=d.get("explanation", ""), details=d,
        created_at=m.created_at, job=job_out(job, source_name, m.score),
    )


@router.get("", response_model=MatchPage)
def list_matches(
    db: DB, user: VerifiedUser,
    status: str | None = Query(default=None, pattern="^(new|saved|dismissed)$"),
    min_score: int = Query(default=0, ge=0, le=100),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=20, ge=1, le=100),
) -> MatchPage:
    cond = [JobMatch.user_id == user.id, JobMatch.score >= min_score]
    cond.append(JobMatch.status == status if status else JobMatch.status != "dismissed")
    total = db.execute(select(func.count()).select_from(JobMatch).where(*cond)).scalar_one()
    rows = db.execute(
        select(JobMatch, Job, JobSource.name).join(Job, Job.id == JobMatch.job_id).join(JobSource, JobSource.id == Job.source_id)
        .where(*cond).order_by(JobMatch.score.desc(), JobMatch.created_at.desc())
        .limit(page_size).offset((page - 1) * page_size)
    ).all()
    return MatchPage(items=[match_out(m, j, n) for m, j, n in rows], total=total, page=page, page_size=page_size)


@router.post("/run", response_model=MatchRunOut, dependencies=[Depends(rate_limit("match_run", 6))])
def run_matching(db: DB, user: VerifiedUser) -> MatchRunOut:
    stats = matching.match_user_now(db, user)
    db.commit()
    return MatchRunOut(**stats.__dict__)


def _owned(db, user, match_id: uuid.UUID) -> JobMatch:
    m = db.get(JobMatch, match_id)
    if m is None or m.user_id != user.id:
        raise NotFound("Match not found")
    return m


@router.get("/{match_id}", response_model=MatchOut)
def get_match(match_id: uuid.UUID, db: DB, user: VerifiedUser) -> MatchOut:
    m = _owned(db, user, match_id)
    job = db.get(Job, m.job_id)
    src = db.get(JobSource, job.source_id)
    return match_out(m, job, src.name if src else "")


@router.patch("/{match_id}", response_model=MatchOut)
def update_match(match_id: uuid.UUID, body: MatchStatusIn, db: DB, user: VerifiedUser) -> MatchOut:
    from app.core.errors import AppError

    if body.status not in STATUSES:
        raise AppError("Invalid status", code="validation_error", status_code=422)
    m = _owned(db, user, match_id)
    m.status = body.status
    db.commit()
    job = db.get(Job, m.job_id)
    src = db.get(JobSource, job.source_id)
    return match_out(m, job, src.name if src else "")
