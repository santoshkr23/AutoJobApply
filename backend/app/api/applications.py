"""Applications: tracking, document preparation, approval, submission and export."""

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.core.deps import DB, VerifiedUser
from app.core.errors import AppError, NotFound
from app.core.ratelimit import rate_limit
from app.models import Application, ApplicationEvent, ApplicationStatus, Job, JobMatch, JobSource, ResumeVersion
from app.models.application import ApplicationStatus as S
from app.services import applications as svc
from app.services import quotas
from app.services.storage import get_storage
from app.tasks.application_tasks import submit_application
from app.tasks.celery_app import enqueue_after_commit

router = APIRouter(prefix="/applications", tags=["applications"])
STATUS_VALUES = [s.value for s in ApplicationStatus]


class CreateIn(BaseModel):
    job_id: uuid.UUID


class UpdateIn(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=5000)
    interview_at: datetime | None = None


class CoverLetterIn(BaseModel):
    paragraphs: list[str] = Field(min_length=1, max_length=8)
    greeting: str | None = Field(default=None, max_length=120)
    closing: str | None = Field(default=None, max_length=200)


def _app_row(a: Application, job: Job, source: str, score: int | None) -> dict:
    return {
        "id": str(a.id), "job_id": str(a.job_id), "status": a.status, "title": job.title, "company": job.company,
        "location": job.location_text, "job_url": job.url, "source": source, "match_score": score,
        "needs_user_action": a.needs_user_action, "approved": a.approved_at is not None,
        "failure_code": a.failure_code, "failure_reason": a.failure_reason, "attempts": a.attempts,
        "submitted_at": a.submitted_at, "confirmation_ref": a.confirmation_ref, "notes": a.notes,
        "interview_at": a.interview_at, "created_at": a.created_at, "updated_at": a.updated_at, "is_sample": job.is_sample,
    }


def _joined(db, user, extra=()):
    return (
        select(Application, Job, JobSource.name, JobMatch.score)
        .join(Job, Job.id == Application.job_id).join(JobSource, JobSource.id == Job.source_id)
        .outerjoin(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == user.id))
        .where(Application.user_id == user.id, Application.deleted_at.is_(None), *extra)
    )


def _detail(db, user, a: Application) -> dict:
    job = db.get(Job, a.job_id)
    src = db.get(JobSource, job.source_id)
    score = db.execute(select(JobMatch.score).where(JobMatch.user_id == user.id, JobMatch.job_id == job.id)).scalar_one_or_none()
    docs = svc.get_documents(db, a)
    events = db.execute(select(ApplicationEvent).where(ApplicationEvent.application_id == a.id).order_by(ApplicationEvent.created_at)).scalars()
    out = _app_row(a, job, src.name if src else "", score)
    out["documents"] = []
    for d in docs:
        item = {"id": str(d.id), "kind": d.kind, "status": d.status, "content": d.content if d.kind == "cover_letter" else None}
        if d.resume_version_id:
            rv = db.get(ResumeVersion, d.resume_version_id)
            item.update(resume=rv.content, change_log=rv.change_log, validation=rv.validation)
        elif d.content:
            item["change_log"] = d.content.get("change_log", [])
        out["documents"].append(item)
    out["events"] = [{"type": e.event_type, "message": e.message, "from": e.from_status, "to": e.to_status,
                      "at": e.created_at, "data": e.data} for e in events]
    return out


@router.post("", status_code=201)
def create(body: CreateIn, response: Response, db: DB, user: VerifiedUser) -> dict:
    a, created = svc.create_application(db, user, body.job_id)
    db.commit()
    if not created:
        response.status_code = 200
    return _detail(db, user, a)


@router.get("")
def list_applications(
    db: DB, user: VerifiedUser,
    status: str | None = Query(default=None), q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1, le=1000), page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    extra = []
    if status:
        if status not in STATUS_VALUES:
            raise AppError("Unknown status", code="validation_error", status_code=422)
        extra.append(Application.status == status)
    if q:
        like = f"%{q.strip()}%"
        extra.append(or_(Job.title.ilike(like), Job.company.ilike(like)))
    base = _joined(db, user, extra)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(Application.updated_at.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    return {"items": [_app_row(a, j, s, sc) for a, j, s, sc in rows], "total": total, "page": page, "page_size": page_size}


# ----------------------------------------------------------------------------- export (declared before /{id})
EXPORT_COLUMNS = ["job_id", "company", "job_title", "location", "salary", "match_score", "job_url", "job_source",
                  "job_description", "custom_resume_path", "cover_letter_path", "application_status", "application_date",
                  "failure_reason", "notes"]


def _salary(j: Job) -> str:
    if j.salary_min is None and j.salary_max is None:
        return ""
    lo, hi = j.salary_min, j.salary_max
    rng = f"{lo:,}-{hi:,}" if lo and hi and lo != hi else f"{(lo or hi):,}"
    return f"{rng} {j.salary_currency or ''}{('/' + j.salary_period) if j.salary_period else ''}".strip()


def _safe_cell(v):
    """Neutralise spreadsheet formula injection."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def export_rows(db, user) -> list[list]:
    rows = db.execute(_joined(db, user).order_by(Application.created_at.desc())).all()
    out = []
    for a, j, src, score in rows:
        docs = {d.kind: d for d in svc.get_documents(db, a)}
        def path(k: str, a=a, docs=docs) -> str:
            return f"/api/applications/{a.id}/documents/{k}/pdf" if k in docs else ""

        when = a.submitted_at or None
        out.append([str(j.id), j.company, j.title, j.location_text or "", _salary(j), score if score is not None else "", j.url, src,
                    j.description, path("resume"), path("cover_letter"), a.status, when.isoformat() if when else "",
                    a.failure_reason or "", a.notes or ""])
    return [[_safe_cell(c) for c in r] for r in out]


@router.get("/export.csv", dependencies=[Depends(rate_limit("export", 10))])
def export_csv(db: DB, user: VerifiedUser) -> Response:
    quotas.require_feature(db, user, "csv_export", "CSV export is not included in your plan.")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(EXPORT_COLUMNS)
    w.writerows(export_rows(db, user))
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="applications.csv"'})


@router.get("/export.xlsx", dependencies=[Depends(rate_limit("export", 10))])
def export_xlsx(db: DB, user: VerifiedUser) -> Response:
    from openpyxl import Workbook

    quotas.require_feature(db, user, "csv_export", "Export is not included in your plan.")
    wb = Workbook()
    ws = wb.active
    ws.title = "Applications"
    ws.append(EXPORT_COLUMNS)
    for r in export_rows(db, user):
        ws.append([str(c)[:32000] if isinstance(c, str) else c for c in r])
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="applications.xlsx"'})


# ----------------------------------------------------------------------------- single application
@router.get("/{app_id}")
def get_one(app_id: uuid.UUID, db: DB, user: VerifiedUser) -> dict:
    return _detail(db, user, svc.get_app(db, user, app_id))


@router.post("/{app_id}/prepare", dependencies=[Depends(rate_limit("prepare", 20))])
def prepare(app_id: uuid.UUID, db: DB, user: VerifiedUser) -> dict:
    a = svc.get_app(db, user, app_id)
    svc.prepare_documents(db, user, a)
    db.commit()
    return _detail(db, user, a)


@router.put("/{app_id}/cover-letter")
def edit_letter(app_id: uuid.UUID, body: CoverLetterIn, db: DB, user: VerifiedUser) -> dict:
    a = svc.get_app(db, user, app_id)
    svc.edit_cover_letter(db, a, body.paragraphs, body.greeting, body.closing)
    db.commit()
    return _detail(db, user, a)


@router.post("/{app_id}/approve-documents")
def approve_documents(app_id: uuid.UUID, db: DB, user: VerifiedUser) -> dict:
    a = svc.get_app(db, user, app_id)
    svc.approve_documents(db, user, a)
    db.commit()
    return _detail(db, user, a)


@router.post("/{app_id}/submit", dependencies=[Depends(rate_limit("submit", 20))], status_code=202)
def submit(app_id: uuid.UUID, db: DB, user: VerifiedUser) -> dict:
    """Explicit user approval + queue the automated submission. Needs consent, plan feature and quota."""
    a = svc.get_app(db, user, app_id)
    if a.status == S.APPLYING.value:
        return _detail(db, user, a)
    quotas.ensure_quota(db, user, "applications_per_month")
    svc.approve_submission(db, user, a)
    enqueue_after_commit(db, submit_application, str(a.id))
    db.commit()
    return _detail(db, user, a)


@router.patch("/{app_id}")
def update(app_id: uuid.UUID, body: UpdateIn, db: DB, user: VerifiedUser) -> dict:
    a = svc.get_app(db, user, app_id)
    if body.status:
        svc.user_set_status(db, user, a, body.status, body.notes)
    elif body.notes is not None:
        a.notes = body.notes
    if body.interview_at is not None:
        a.interview_at = body.interview_at
    db.commit()
    return _detail(db, user, a)


@router.delete("/{app_id}", status_code=204)
def delete(app_id: uuid.UUID, db: DB, user: VerifiedUser) -> Response:
    svc.delete_application(db, svc.get_app(db, user, app_id))
    db.commit()
    return Response(status_code=204)


@router.get("/{app_id}/documents/{kind}/{fmt}")
def document_link(app_id: uuid.UUID, kind: str, fmt: str, db: DB, user: VerifiedUser) -> dict:
    a = svc.get_app(db, user, app_id)
    if kind not in ("resume", "cover_letter") or fmt not in ("pdf", "docx"):
        raise NotFound("Document not found")
    doc = next((d for d in svc.get_documents(db, a) if d.kind == kind), None)
    key = (doc.pdf_key if fmt == "pdf" else doc.docx_key) if doc else None
    if not key:
        raise NotFound("Document not found")
    ctype = "application/pdf" if fmt == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return {"url": get_storage().signed_url(key, f"{kind}.{fmt}", ctype), "status": doc.status}
