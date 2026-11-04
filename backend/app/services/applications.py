"""Application lifecycle: state machine, events, tailored documents, consent-gated approval.

Honesty rules enforced here:
* APPLIED is only set by (a) the automation engine after a verified confirmation, or (b) the user explicitly
  reporting that they applied themselves (recorded as such in the event log).
* Nothing is submitted without the `auto_apply` consent AND a per-application approval.
"""

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.errors import AppError, Conflict, NotFound
from app.models import Application, ApplicationDocument, ApplicationEvent, Job, JobMatch, ResumeVersion, User
from app.models.application import ApplicationStatus as S
from app.models.base import utcnow
from app.services import ai_service, documents, profiles, quotas
from app.services.grounding import numbers_in, validate_cover_letter, validate_tailored_resume
from app.services.llm.base import LLMError
from app.services.notifications import notify
from app.services.storage import get_storage

ALLOWED: dict[str, set[str]] = {
    S.DISCOVERED.value: {S.MATCHED.value, S.WITHDRAWN.value},
    S.MATCHED.value: {S.RESUME_GENERATED.value, S.PENDING_APPROVAL.value, S.APPLIED.value, S.WITHDRAWN.value},
    S.RESUME_GENERATED.value: {S.PENDING_APPROVAL.value, S.APPLIED.value, S.WITHDRAWN.value},
    S.PENDING_APPROVAL.value: {S.RESUME_GENERATED.value, S.APPLYING.value, S.APPLIED.value, S.WITHDRAWN.value},
    S.APPLYING.value: {S.APPLIED.value, S.MANUAL_REQUIRED.value, S.FAILED.value},
    S.MANUAL_REQUIRED.value: {S.PENDING_APPROVAL.value, S.APPLYING.value, S.APPLIED.value, S.FAILED.value, S.WITHDRAWN.value},
    S.FAILED.value: {S.PENDING_APPROVAL.value, S.APPLYING.value, S.APPLIED.value, S.WITHDRAWN.value},
    S.APPLIED.value: {S.REJECTED.value, S.INTERVIEW.value, S.OFFER.value, S.WITHDRAWN.value},
    S.INTERVIEW.value: {S.REJECTED.value, S.OFFER.value, S.WITHDRAWN.value},
    S.OFFER.value: {S.WITHDRAWN.value, S.REJECTED.value},
    S.REJECTED.value: set(),
    S.WITHDRAWN.value: set(),
}
# statuses a user may set directly through the API (APPLYING/FAILED/MANUAL_REQUIRED belong to the engine)
USER_SETTABLE = {S.APPLIED.value, S.REJECTED.value, S.INTERVIEW.value, S.OFFER.value, S.WITHDRAWN.value}


class InvalidTransition(AppError):
    status_code = 409
    code = "invalid_transition"


def idempotency_key(user_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return hashlib.sha256(f"{user_id}:{job_id}".encode()).hexdigest()


def add_event(db: Session, app: Application, event_type: str, message: str | None = None, *,
              from_status: str | None = None, to_status: str | None = None, data: dict | None = None) -> None:
    db.add(ApplicationEvent(application_id=app.id, user_id=app.user_id, event_type=event_type, message=message,
                            from_status=from_status, to_status=to_status, data=data or {}, created_at=utcnow()))


def transition(db: Session, app: Application, to: str, message: str | None = None, *, data: dict | None = None) -> None:
    if to == app.status:
        return
    if to not in ALLOWED.get(app.status, set()):
        raise InvalidTransition(f"Cannot move an application from {app.status} to {to}.")
    prev, app.status = app.status, to
    add_event(db, app, "status_change", message, from_status=prev, to_status=to, data=data)


def get_app(db: Session, user: User, app_id: uuid.UUID) -> Application:
    a = db.get(Application, app_id)
    if a is None or a.user_id != user.id or a.deleted_at is not None:
        raise NotFound("Application not found")
    return a


def create_application(db: Session, user: User, job_id: uuid.UUID) -> tuple[Application, bool]:
    job = db.get(Job, job_id)
    if job is None or job.status == "duplicate":
        raise NotFound("Job not found")
    existing = db.execute(select(Application).where(Application.user_id == user.id, Application.job_id == job_id)).scalar_one_or_none()
    if existing is not None:
        if existing.deleted_at is not None:  # restore a previously removed record
            existing.deleted_at = None
            add_event(db, existing, "restored", "Application restored")
        return existing, False
    match = db.execute(select(JobMatch).where(JobMatch.user_id == user.id, JobMatch.job_id == job_id)).scalar_one_or_none()
    a = Application(user_id=user.id, job_id=job_id, match_id=match.id if match else None, status=S.MATCHED.value,
                    idempotency_key=idempotency_key(user.id, job_id), attempts=0, needs_user_action=False)
    db.add(a)
    db.flush()
    add_event(db, a, "created", "Application created", to_status=S.MATCHED.value)
    return a, True


def _docs(db: Session, app: Application, kind: str | None = None) -> list[ApplicationDocument]:
    q = select(ApplicationDocument).where(ApplicationDocument.application_id == app.id, ApplicationDocument.deleted_at.is_(None))
    if kind:
        q = q.where(ApplicationDocument.kind == kind)
    return list(db.execute(q.order_by(ApplicationDocument.created_at)).scalars())


def get_documents(db: Session, app: Application) -> list[ApplicationDocument]:
    return _docs(db, app)


def prepare_documents(db: Session, user: User, app: Application, *, advanced: bool = False) -> Application:
    """Generate a tailored resume + cover letter (drafts). Facts are grounded in the verified profile."""
    if app.status not in (S.MATCHED.value, S.RESUME_GENERATED.value, S.PENDING_APPROVAL.value, S.MANUAL_REQUIRED.value, S.FAILED.value):
        raise InvalidTransition(f"Documents cannot be generated while the application is {app.status}.")
    profile = profiles.get_profile(db, user.id)
    if profile is None or profile.verified_at is None:
        raise AppError("Confirm your profile before generating documents.", code="profile_not_ready", status_code=409)
    quotas.ensure_quota(db, user, "resume_customizations_per_month")
    quotas.ensure_quota(db, user, "cover_letters_per_month")
    job = db.get(Job, app.job_id)
    prof = profiles.profile_to_dict(profile)
    jd = {"title": job.title, "company": job.company, "description": job.description}
    analysis = job.analysis or {}
    try:
        tailored, usage = ai_service.tailor_resume(db, user.id, prof, analysis, jd, advanced=advanced)
        letter, usage2 = ai_service.write_cover_letter(db, user.id, prof, analysis, jd, advanced=advanced)
    except LLMError as exc:
        raise AppError(f"AI service unavailable: {exc}", code="ai_unavailable", status_code=503) from exc

    grounded = validate_tailored_resume(prof, tailored)
    letter_content, letter_log = validate_cover_letter(prof, numbers_in(job.description), letter)
    if not letter_content["paragraphs"]:
        letter_content["paragraphs"] = [
            f"I am applying for the {job.title} role at {job.company}. My background is described in the attached resume, "
            "and I would welcome the opportunity to discuss how it fits the position."
        ]
        letter_log.append({"section": "cover_letter", "kind": "fallback", "reason": "all generated paragraphs failed grounding checks"})
    letter_content["greeting"] = letter_content["greeting"] or "Dear Hiring Team,"
    letter_content["closing"] = letter_content["closing"] or f"Sincerely,\n{prof.get('full_name') or ''}".strip()

    storage = get_storage()
    for d in _docs(db, app):  # supersede earlier drafts
        d.deleted_at = utcnow()
    rv = ResumeVersion(user_id=user.id, job_id=job.id, match_id=app.match_id, status="draft", content=grounded.content,
                       change_log=grounded.change_log, validation={"rejected_items": grounded.rejected, "passed": grounded.passed},
                       ai_provider=usage.provider, model=usage.model)
    db.add(rv)
    db.flush()
    base = f"generated/{user.id}/{app.id}/{rv.id}"
    pdf, docx = documents.render_resume_pdf(grounded.content), documents.render_resume_docx(grounded.content)
    rv.pdf_key, rv.docx_key = f"{base}/resume.pdf", f"{base}/resume.docx"
    storage.put(rv.pdf_key, pdf, "application/pdf")
    storage.put(rv.docx_key, docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    sender = {k: prof.get(k) for k in ("full_name", "email", "phone", "location", "links")}
    jobd = {"title": job.title, "company": job.company}
    cl = ApplicationDocument(user_id=user.id, application_id=app.id, kind="cover_letter", status="draft",
                             content={**letter_content, "change_log": letter_log}, ai_provider=usage2.provider)
    cl.pdf_key, cl.docx_key = f"{base}/cover_letter.pdf", f"{base}/cover_letter.docx"
    storage.put(cl.pdf_key, documents.render_cover_letter_pdf(letter_content, sender, jobd), "application/pdf")
    storage.put(cl.docx_key, documents.render_cover_letter_docx(letter_content, sender, jobd),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    rd = ApplicationDocument(user_id=user.id, application_id=app.id, kind="resume", status="draft", resume_version_id=rv.id,
                             pdf_key=rv.pdf_key, docx_key=rv.docx_key, ai_provider=usage.provider)
    db.add_all([cl, rd])
    quotas.increment_usage(db, user.id, "resume_customizations")
    quotas.increment_usage(db, user.id, "cover_letters")
    add_event(db, app, "documents_generated", "Tailored resume and cover letter drafted; review required",
              data={"resume_version_id": str(rv.id), "rejected_items": grounded.rejected, "provider": usage.provider})
    if app.status == S.MATCHED.value:
        transition(db, app, S.RESUME_GENERATED.value)
    if app.status == S.RESUME_GENERATED.value:
        transition(db, app, S.PENDING_APPROVAL.value, "Waiting for your review and approval")
    app.approved_at = None  # any regeneration voids earlier approval
    notify(db, user, "resume_generated", f"Documents ready: {job.title} at {job.company}",
           "Your tailored resume and cover letter are ready for review.", {"application_id": str(app.id)})
    audit(db, action="application.documents_generated", actor_type="user", actor_id=user.id, target_type="application", target_id=app.id)
    db.flush()
    return app


def edit_cover_letter(db: Session, app: Application, paragraphs: list[str], greeting: str | None, closing: str | None) -> ApplicationDocument:
    docs = _docs(db, app, "cover_letter")
    if not docs:
        raise NotFound("No cover letter yet")
    d = docs[-1]
    c = dict(d.content or {})
    c["paragraphs"] = [p.strip() for p in paragraphs if p.strip()]
    if greeting:
        c["greeting"] = greeting
    if closing:
        c["closing"] = closing
    c.setdefault("change_log", []).append({"section": "cover_letter", "kind": "user_edit"})
    d.content, d.status = c, "draft"
    app.approved_at = None
    return d


def approve_documents(db: Session, user: User, app: Application) -> list[ApplicationDocument]:
    docs = _docs(db, app)
    if not {d.kind for d in docs} >= {"resume", "cover_letter"}:
        raise AppError("Generate documents before approving them.", code="no_documents", status_code=409)
    now = utcnow()
    for d in docs:
        d.status, d.approved_at = "approved", now
        if d.resume_version_id:
            rv = db.get(ResumeVersion, d.resume_version_id)
            rv.status, rv.approved_at = "approved", now
    add_event(db, app, "documents_approved", "You approved the resume and cover letter")
    return docs


def approve_submission(db: Session, user: User, app: Application) -> Application:
    """Explicit per-application consent to let the platform submit. Requires global consent + plan feature."""
    quotas.require_feature(db, user, "auto_apply", "Automated applications are not included in your plan.")
    if not profiles.has_consent(db, user.id, "auto_apply"):
        raise AppError("Grant the 'automated applications' consent in Settings first.", code="consent_required", status_code=403)
    docs = _docs(db, app)
    if not docs or any(d.status != "approved" for d in docs):
        raise AppError("Approve the tailored resume and cover letter first.", code="documents_not_approved", status_code=409)
    if app.status not in (S.PENDING_APPROVAL.value, S.MANUAL_REQUIRED.value, S.FAILED.value):
        raise InvalidTransition(f"Cannot approve submission while the application is {app.status}.")
    app.approved_at = utcnow()
    add_event(db, app, "submission_approved", "You approved submitting this application")
    audit(db, action="application.submission_approved", actor_type="user", actor_id=user.id, target_type="application", target_id=app.id)
    return app


def user_set_status(db: Session, user: User, app: Application, to: str, note: str | None) -> Application:
    if to not in USER_SETTABLE:
        raise InvalidTransition(f"You cannot set the status to {to}.")
    if to == S.APPLIED.value:
        if app.status == S.APPLYING.value:
            raise InvalidTransition("The platform is submitting right now.")
        app.submitted_at = app.submitted_at or utcnow()
        app.needs_user_action = False
        transition(db, app, to, "You reported that you applied yourself (not verified by the platform)", data={"self_reported": True})
    else:
        transition(db, app, to, note)
    if note:
        app.notes = note
    return app


def delete_application(db: Session, app: Application) -> None:
    if app.status in (S.APPLYING.value,):
        raise Conflict("Application is being submitted right now.")
    app.deleted_at = utcnow()
