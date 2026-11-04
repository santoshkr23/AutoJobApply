"""Job ingestion: normalize, de-duplicate, detect expiry; plus search for the API."""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorError, DiscoveryQuery
from app.connectors.normalize import normalize
from app.connectors.registry import DEFAULT_SOURCES, build_connector
from app.core.config import get_settings
from app.models.base import utcnow
from app.models.job import DiscoveryRun, Job, JobSource
from app.services import heuristics
from app.services.settings_store import get_setting

log = logging.getLogger(__name__)
MAX_CONSECUTIVE_FAILURES_BEFORE_ALERT = 5


def seed_job_sources(db: Session) -> None:
    s = get_settings()
    for spec in DEFAULT_SOURCES:
        if spec["key"] == "mock" and (not s.enable_mock_connector or s.is_production_like):
            continue
        if db.execute(select(JobSource).where(JobSource.key == spec["key"])).scalar_one_or_none() is None:
            from app.connectors.registry import CONNECTORS

            c = CONNECTORS[spec["connector_type"]]
            db.add(JobSource(**spec, terms_url=c.terms_url or None, terms_note=c.terms_note or None))
    db.flush()


@dataclass
class IngestStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    expired: int = 0
    skipped: int = 0


def _job_fields(norm: dict) -> dict:
    fields = {k: v for k, v in norm.items() if k not in ("external_id", "fingerprint", "is_sample")}
    analysis = heuristics.analyze_job_text(norm["title"], norm["description"])
    fields["analysis"] = {**analysis, "analyzed_by": "heuristics"}
    fields["skills"] = list(dict.fromkeys(analysis["required_skills"] + analysis["preferred_skills"]))
    fields["experience_min"] = analysis["min_years_experience"]
    fields["experience_max"] = analysis["max_years_experience"]
    fields["visa_sponsorship"] = analysis["visa_sponsorship"]
    if not fields.get("work_mode") and analysis.get("work_mode"):
        fields["work_mode"] = analysis["work_mode"]
    return fields


def ingest(db: Session, source: JobSource, raw_jobs, stats: IngestStats | None = None) -> IngestStats:
    stats = stats or IngestStats()
    now = utcnow()
    categories = get_setting(db, "job_categories") or []
    existing = {j.external_id: j for j in db.execute(select(Job).where(Job.source_id == source.id)).scalars()}

    normalized: list[dict] = []
    for raw in raw_jobs:
        stats.fetched += 1
        n = normalize(raw, categories)
        if n is None:
            stats.skipped += 1
            continue
        normalized.append(n)

    fps = {n["fingerprint"] for n in normalized}
    by_fp: dict[str, Job] = {}
    if fps:
        for j in db.execute(
            select(Job).where(Job.fingerprint.in_(fps), Job.status == "active").order_by(Job.first_seen_at)
        ).scalars():
            by_fp.setdefault(j.fingerprint, j)

    seen_external: set[str] = set()
    for n in normalized:
        ext = n["external_id"]
        seen_external.add(ext)
        fields = _job_fields(n)
        is_expired = bool(n["expires_at"] and n["expires_at"] <= now)
        job = existing.get(ext)
        if job is not None:
            for k, v in fields.items():
                setattr(job, k, v)
            job.fingerprint = n["fingerprint"]
            job.last_seen_at, job.missed_runs = now, 0
            if is_expired and job.status != "expired":
                job.status = "expired"
                stats.expired += 1
            elif not is_expired and job.status == "expired":
                job.status = "active"  # reposted
            stats.updated += 1
            continue

        canonical = by_fp.get(n["fingerprint"])
        job = Job(
            source_id=source.id, external_id=ext, fingerprint=n["fingerprint"], first_seen_at=now, last_seen_at=now,
            is_sample=n["is_sample"], status="expired" if is_expired else "active", **fields,
        )
        if canonical is not None and not is_expired:
            job.status = "duplicate"
            job.canonical_job_id = canonical.id
            stats.duplicates += 1
        else:
            if is_expired:
                stats.expired += 1
        db.add(job)
        db.flush()
        if job.status == "active":
            by_fp[n["fingerprint"]] = job
        stats.created += 1

    # Jobs that disappeared from the feed: expire after several consecutive misses.
    threshold = get_settings().job_missing_runs_before_expiry
    for ext, job in existing.items():
        if ext in seen_external or job.status == "expired":
            continue
        job.missed_runs += 1
        if job.missed_runs >= threshold:
            job.status = "expired"
            stats.expired += 1
    db.flush()
    return stats


def run_source(db: Session, source: JobSource) -> DiscoveryRun:
    """Run one discovery cycle for a source and record the outcome for monitoring."""
    run = DiscoveryRun(source_id=source.id, started_at=utcnow(), status="running")
    db.add(run)
    db.flush()
    stats = IngestStats()
    try:
        connector = build_connector(source.connector_type, source.config)
        if not connector.is_configured():
            raise ConnectorError(f"{source.key}: credentials not configured")
        raw = list(connector.fetch(DiscoveryQuery(keywords=source.config.get("keywords", []), countries=source.config.get("countries", []))))
        ingest(db, source, raw, stats)
        run.status = "success"
        source.last_status, source.last_error, source.consecutive_failures = "success", None, 0
    except (ConnectorError, PermissionError, KeyError) as exc:
        run.status, run.error = "failed", str(exc)[:500]
        source.last_status, source.last_error = "failed", str(exc)[:500]
        source.consecutive_failures += 1
        log.warning("Discovery failed for %s: %s", source.key, exc)
    run.fetched, run.created, run.updated = stats.fetched, stats.created, stats.updated
    run.duplicates, run.expired = stats.duplicates, stats.expired
    run.finished_at = source.last_run_at = utcnow()
    db.flush()
    return run


def expire_stale_jobs(db: Session) -> int:
    """Expire jobs past their expiry date or older than the configured maximum age."""
    from datetime import timedelta

    now = utcnow()
    cutoff = now - timedelta(days=get_settings().job_max_age_days)
    n = 0
    for job in db.execute(
        select(Job).where(
            Job.status == "active",
            or_(Job.expires_at <= now, and_(Job.posted_at.is_not(None), Job.posted_at < cutoff, Job.last_seen_at < cutoff)),
        )
    ).scalars():
        job.status = "expired"
        n += 1
    db.flush()
    return n


def due_sources(db: Session) -> list[JobSource]:
    from datetime import timedelta

    now = utcnow()
    due = []
    for s in db.execute(select(JobSource).where(JobSource.enabled.is_(True))).scalars():
        if s.last_run_at is None or s.last_run_at + timedelta(minutes=s.interval_minutes) <= now:
            due.append(s)
    return due


# --------------------------------------------------------------------------- search
@dataclass
class JobFilters:
    q: str | None = None
    country: str | None = None
    work_mode: str | None = None
    category: str | None = None
    employment_type: str | None = None
    min_salary: int | None = None
    posted_within_days: int | None = None
    source: str | None = None


def search_jobs(db: Session, f: JobFilters, page: int, page_size: int, user_id: uuid.UUID | None = None):
    from datetime import timedelta

    from sqlalchemy import Integer, cast, null

    from app.models.job import JobMatch

    score_col = JobMatch.score if user_id else cast(null(), Integer)
    stmt = select(Job, JobSource.name, score_col).join(JobSource, JobSource.id == Job.source_id)
    if user_id:
        stmt = stmt.outerjoin(JobMatch, and_(JobMatch.job_id == Job.id, JobMatch.user_id == user_id))
    stmt = stmt.where(Job.status == "active")
    if f.q:
        like = f"%{f.q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Job.title).like(like), func.lower(Job.company).like(like), func.lower(Job.description).like(like)))
    if f.country:
        stmt = stmt.where(Job.country == f.country.upper())
    if f.work_mode:
        stmt = stmt.where(Job.work_mode == f.work_mode)
    if f.category:
        stmt = stmt.where(Job.category == f.category)
    if f.employment_type:
        stmt = stmt.where(Job.employment_type == f.employment_type)
    if f.min_salary:
        stmt = stmt.where(or_(Job.salary_max >= f.min_salary, Job.salary_min >= f.min_salary))
    if f.posted_within_days:
        stmt = stmt.where(Job.posted_at >= utcnow() - timedelta(days=f.posted_within_days))
    if f.source:
        stmt = stmt.where(JobSource.key == f.source)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Job.posted_at.desc().nulls_last(), Job.id).limit(page_size).offset((page - 1) * page_size)
    ).all()
    return rows, total
