"""Master resume upload, review and deletion."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.core.audit import audit
from app.core.config import get_settings
from app.core.deps import DB, VerifiedUser, get_owned
from app.core.errors import AppError
from app.core.ratelimit import rate_limit
from app.models.resume import Resume
from app.schemas.resume import ProfileIn, ProfileOut, ResumeOut
from app.services import profiles, resumes
from app.services.storage import get_storage
from app.tasks.ai_tasks import parse_resume_task
from app.tasks.celery_app import enqueue_after_commit

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.get("", response_model=list[ResumeOut])
def list_resumes(db: DB, user: VerifiedUser) -> list[ResumeOut]:
    return [resumes.resume_out(r) for r in resumes.list_resumes(db, user)]


@router.post("", response_model=ResumeOut, status_code=202, dependencies=[Depends(rate_limit("resume_upload", 10))])
async def upload_resume(
    request: Request, db: DB, user: VerifiedUser, file: UploadFile = File(...), label: str | None = Form(default=None)
) -> ResumeOut:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)  # never buffer more than the limit
    r = resumes.create_resume(db, user, file.filename or "resume", data, label)
    audit(db, action="resume.uploaded", actor_type="user", actor_id=user.id, target_type="resume", target_id=r.id, request=request)
    enqueue_after_commit(db, parse_resume_task, str(r.id))  # fires once the commit below succeeds
    db.commit()
    db.refresh(r)
    return resumes.resume_out(r)


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: uuid.UUID, db: DB, user: VerifiedUser) -> ResumeOut:
    return resumes.resume_out(get_owned(db, Resume, resume_id, user))


@router.post("/{resume_id}/reparse", response_model=ResumeOut, status_code=202)
def reparse(resume_id: uuid.UUID, db: DB, user: VerifiedUser) -> ResumeOut:
    r = get_owned(db, Resume, resume_id, user)
    r.parse_status, r.parse_error = "pending", None
    enqueue_after_commit(db, parse_resume_task, str(r.id))
    db.commit()
    db.refresh(r)
    return resumes.resume_out(r)


@router.post("/{resume_id}/confirm", response_model=ProfileOut)
def confirm_resume(resume_id: uuid.UUID, body: ProfileIn, request: Request, db: DB, user: VerifiedUser) -> ProfileOut:
    """The user verifies (and may correct) the extracted data. This becomes the verified profile."""
    r = get_owned(db, Resume, resume_id, user)
    if r.parse_status not in ("parsed", "confirmed"):
        raise AppError("This resume has not been processed yet.", code="resume_not_ready")
    p = profiles.upsert_profile(db, user, body, source_resume_id=r.id)
    from app.models.base import utcnow

    r.confirmed_at = utcnow()
    r.parse_status = "confirmed"
    user.onboarding_step = max(user.onboarding_step, 3)
    audit(db, action="profile.verified", actor_type="user", actor_id=user.id, target_type="resume", target_id=r.id, request=request)
    db.commit()
    return profiles.profile_out(p)


@router.get("/{resume_id}/download")
def download_resume(resume_id: uuid.UUID, db: DB, user: VerifiedUser) -> dict:
    r = get_owned(db, Resume, resume_id, user)
    s = get_settings()
    url = get_storage().signed_url(r.storage_key, r.original_filename, r.content_type)
    return {"url": url, "expires_in": s.signed_url_ttl_seconds}


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: uuid.UUID, request: Request, db: DB, user: VerifiedUser) -> None:
    r = get_owned(db, Resume, resume_id, user)
    resumes.delete_resume(db, r)
    audit(db, action="resume.deleted", actor_type="user", actor_id=user.id, target_type="resume", target_id=r.id, request=request)
    db.commit()
