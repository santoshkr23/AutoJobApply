"""Run an approved application through an automation adapter. Single-flight, idempotent, honest outcomes."""

import logging
import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Application, ApplicationDocument, Job, User
from app.models.application import ApplicationStatus as S
from app.models.base import utcnow
from app.services import applications as svc
from app.services import profiles, quotas
from app.services.notifications import notify
from app.services.storage import get_storage

log = logging.getLogger(__name__)
CLAIMABLE = (S.PENDING_APPROVAL.value, S.FAILED.value, S.MANUAL_REQUIRED.value)


class RetryLater(Exception):
    """Transient failure; the Celery task should retry with backoff."""


def claim(db: Session, app_id: uuid.UUID) -> bool:
    """Atomically move an approved application to APPLYING. Returns False if somebody else holds it / not eligible."""
    res = db.execute(
        update(Application)
        .where(Application.id == app_id, Application.status.in_(CLAIMABLE), Application.approved_at.is_not(None),
               Application.deleted_at.is_(None))
        .values(status=S.APPLYING.value, attempts=Application.attempts + 1, last_attempt_at=utcnow(), needs_user_action=False)
    )
    return res.rowcount == 1


def submit_now(db: Session, app_id: uuid.UUID) -> str:
    """Returns the final status string of this attempt. Raises RetryLater for retryable failures."""
    from career_automation.base import Applicant, Outcome, SubmissionContext
    from career_automation.registry import pick_adapter

    s = get_settings()
    app = db.get(Application, app_id)
    if app is None:
        return "missing"
    if not claim(db, app_id):
        return app.status  # already applying/applied or not approved: do nothing (idempotent)
    db.refresh(app)
    svc.add_event(db, app, "attempt_started", f"Attempt {app.attempts}", from_status=None, to_status=S.APPLYING.value,
                  data={"attempt": app.attempts})
    db.commit()

    user = db.get(User, app.user_id)
    job = db.get(Job, app.job_id)
    # Re-check consent at execution time: it may have been withdrawn since approval.
    if not profiles.has_consent(db, user.id, "auto_apply"):
        return _manual(db, app, user, job, "consent_withdrawn", "Automated applications consent was withdrawn.")
    docs = {d.kind: d for d in svc.get_documents(db, app)}
    if not {"resume", "cover_letter"} <= docs.keys() or any(d.status != "approved" for d in docs.values()):
        return _manual(db, app, user, job, "documents_not_approved", "Approved documents are missing.")
    try:
        quotas.ensure_quota(db, user, "applications_per_month")
    except Exception as exc:  # QuotaExceeded
        return _manual(db, app, user, job, "quota_exceeded", str(exc))

    profile = profiles.get_profile(db, user.id)
    url = job.apply_url or job.url
    adapter = pick_adapter(url, s.automation_domain_list)
    app.adapter = adapter.name
    storage = get_storage()
    resume_doc: ApplicationDocument = docs["resume"]
    letter = docs["cover_letter"].content or {}
    letter_text = "\n\n".join([letter.get("greeting", ""), *letter.get("paragraphs", []), letter.get("closing", "")]).strip()
    ctx = SubmissionContext(
        application_id=str(app.id), job_title=job.title, company=job.company, apply_url=url,
        applicant=Applicant(full_name=profile.full_name or "", email=profile.email or user.email, phone=profile.phone,
                            location=profile.location),
        resume_bytes=storage.get(resume_doc.pdf_key), resume_filename="resume.pdf", cover_letter_text=letter_text,
        allowed_domains=s.automation_domain_list, headless=s.automation_headless,
    )
    db.commit()
    result = adapter.submit(ctx)
    db.refresh(app)
    data = {"code": result.code, "adapter": adapter.name, **result.evidence}

    if result.outcome == Outcome.SUBMITTED:
        app.submitted_at, app.confirmation_ref = utcnow(), result.confirmation_ref
        app.failure_code = app.failure_reason = None
        svc.transition(db, app, S.APPLIED.value, "Submission verified by the employer site's confirmation page", data=data)
        quotas.increment_usage(db, user.id, "applications")
        notify(db, user, "application_submitted", f"Applied: {job.title} at {job.company}", "Your application was submitted and confirmed.",
               {"application_id": str(app.id)})
    elif result.outcome == Outcome.MANUAL_REQUIRED:
        return _manual(db, app, user, job, result.code, result.message, data)
    elif result.outcome == Outcome.RETRYABLE and app.attempts < s.automation_max_attempts:
        app.failure_code, app.failure_reason = result.code, result.message
        svc.transition(db, app, S.FAILED.value, f"{result.message} Will retry.", data={**data, "will_retry": True})
        db.commit()
        raise RetryLater(result.message)
    else:
        app.failure_code, app.failure_reason = result.code, result.message
        svc.transition(db, app, S.FAILED.value, result.message, data=data)
        notify(db, user, "manual_required", f"Application failed: {job.title}", result.message, {"application_id": str(app.id)})
    db.commit()
    return app.status


def _manual(db, app, user, job, code, message, data=None) -> str:
    db.refresh(app)
    app.failure_code, app.failure_reason, app.needs_user_action = code, message, True
    app.approved_at = None  # a human acts now; a retry needs a fresh approval
    svc.transition(db, app, S.MANUAL_REQUIRED.value, message, data={"code": code, **(data or {})})
    notify(db, user, "manual_required", f"Action needed: {job.title} at {job.company}", message,
           {"application_id": str(app.id), "url": job.apply_url or job.url}, always_email=True)
    db.commit()
    return app.status
