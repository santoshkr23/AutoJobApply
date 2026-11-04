"""Master resume upload, parsing and deletion."""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.core.errors import AppError, QuotaExceeded
from app.models.base import utcnow
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ParsedResume, ResumeOut
from app.services import ai_service, resume_files
from app.services.llm import LLMError
from app.services.quotas import get_plan_for_user
from app.services.storage import get_storage, safe_filename

log = logging.getLogger(__name__)


def _seal(parsed: dict) -> dict:
    """Encrypt the phone number before the parsed JSON is stored."""
    out = dict(parsed)
    if out.get("phone"):
        out["phone"] = encrypt(out["phone"])
    return out


def _unseal(parsed: dict | None) -> dict | None:
    if not parsed:
        return parsed
    out = dict(parsed)
    if out.get("phone"):
        try:
            out["phone"] = decrypt(out["phone"])
        except ValueError:
            out["phone"] = None
    return out


def resume_out(r: Resume) -> ResumeOut:
    parsed = _unseal(r.parsed_data)
    return ResumeOut(
        id=r.id,
        label=r.label,
        original_filename=r.original_filename,
        content_type=r.content_type,
        size_bytes=r.size_bytes,
        parse_status=r.parse_status,
        parse_error=r.parse_error,
        parsed_data=ParsedResume.model_validate(parsed) if parsed else None,
        ai_provider=r.ai_provider,
        confirmed_at=r.confirmed_at,
        created_at=r.created_at,
    )


def list_resumes(db: Session, user: User) -> list[Resume]:
    return list(
        db.execute(
            select(Resume).where(Resume.user_id == user.id, Resume.deleted_at.is_(None)).order_by(Resume.created_at.desc())
        ).scalars()
    )


def create_resume(db: Session, user: User, filename: str, data: bytes, label: str | None) -> Resume:
    ext, mime, digest = resume_files.validate_upload(filename, data)
    plan = get_plan_for_user(db, user)
    count = db.execute(
        select(func.count()).select_from(Resume).where(Resume.user_id == user.id, Resume.deleted_at.is_(None))
    ).scalar_one()
    max_resumes = int(plan.limits.get("max_resumes", 1))
    if count >= max_resumes:
        raise QuotaExceeded(
            f"Your {plan.name} plan allows {max_resumes} resume(s). Delete one or upgrade to add more.",
            code="resume_limit",
            details={"limit": max_resumes, "plan": plan.key},
        )
    resume_id = uuid.uuid4()
    key = f"users/{user.id}/resumes/{resume_id}.{ext}"
    get_storage().put(key, data, mime)
    r = Resume(
        id=resume_id,
        user_id=user.id,
        label=(label or ("Master resume" if count == 0 else f"Resume {count + 1}"))[:120],
        is_master=count == 0,
        original_filename=safe_filename(filename, f"resume.{ext}"),
        content_type=mime,
        size_bytes=len(data),
        sha256=digest,
        storage_key=key,
        parse_status="pending",
    )
    db.add(r)
    db.flush()
    return r


def parse_resume_now(db: Session, resume_id: uuid.UUID) -> None:
    """Extract text and structured data. Failures are stored on the row with a user-safe message."""
    r = db.get(Resume, resume_id)
    if r is None or r.deleted_at is not None:
        return
    r.parse_status, r.parse_error = "parsing", None
    db.flush()
    try:
        data = get_storage().get(r.storage_key)
        ext = "pdf" if r.content_type == resume_files.PDF_MIME else "docx"
        text = resume_files.extract_text(data, ext)
        llm_result, usage, warnings = ai_service.parse_resume(db, r.user_id, text)
        parsed = ParsedResume.model_validate(llm_result.model_dump())
        r.parsed_data = _seal(parsed.model_dump(mode="json"))
        r.ai_provider = usage.provider
        r.parse_status = "parsed"
        if warnings:
            r.parse_error = "Warning: this document contains text that looks like instructions to an AI. It was ignored."
    except AppError as exc:
        r.parse_status, r.parse_error = "failed", exc.message
    except LLMError as exc:
        r.parse_status, r.parse_error = "failed", f"Automatic extraction failed: {exc}. You can retry."
    except Exception:  # noqa: BLE001
        log.exception("Unexpected resume parsing failure resume_id=%s", resume_id)
        r.parse_status, r.parse_error = "failed", "Unexpected error while reading the resume. Please try again."
    db.flush()


def delete_resume(db: Session, r: Resume) -> None:
    try:
        get_storage().delete(r.storage_key)
    except Exception:  # noqa: BLE001
        log.warning("Could not delete stored resume object %s", r.storage_key)
    r.deleted_at = utcnow()
    r.parsed_data = None
