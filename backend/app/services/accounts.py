"""Account deletion: remove personal data immediately, keep only what the law requires (payments, consent log)."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.application import Application, ApplicationDocument
from app.models.base import utcnow
from app.models.job import JobMatch
from app.models.misc import Notification
from app.models.resume import Resume, ResumeVersion
from app.models.user import AuthSession, EmailToken, User, UserPreferences, UserProfile
from app.services.storage import get_storage

log = logging.getLogger(__name__)


def _delete_objects(keys: list[str | None]) -> None:
    storage = get_storage()
    for key in keys:
        if key:
            try:
                storage.delete(key)
            except Exception:  # noqa: BLE001
                log.warning("Could not delete stored object %s during account deletion", key)


def delete_account(db: Session, user: User) -> None:
    uid = user.id
    keys: list[str | None] = []
    for r in db.execute(select(Resume).where(Resume.user_id == uid)).scalars():
        keys.append(r.storage_key)
    for v in db.execute(select(ResumeVersion).where(ResumeVersion.user_id == uid)).scalars():
        keys += [v.pdf_key, v.docx_key]
    for d in db.execute(select(ApplicationDocument).where(ApplicationDocument.user_id == uid)).scalars():
        keys += [d.pdf_key, d.docx_key]
    _delete_objects(keys)

    # Order matters because of foreign keys. Applications cascade to events and documents.
    db.execute(delete(Application).where(Application.user_id == uid))
    db.execute(delete(ResumeVersion).where(ResumeVersion.user_id == uid))
    db.execute(delete(JobMatch).where(JobMatch.user_id == uid))
    db.execute(delete(UserProfile).where(UserProfile.user_id == uid))
    db.execute(delete(Resume).where(Resume.user_id == uid))
    db.execute(delete(UserPreferences).where(UserPreferences.user_id == uid))
    db.execute(delete(Notification).where(Notification.user_id == uid))
    db.execute(delete(EmailToken).where(EmailToken.user_id == uid))
    db.execute(delete(AuthSession).where(AuthSession.subject_type == "user", AuthSession.subject_id == uid))

    # The user row stays as an anonymized shell so payment records (legal retention) keep their reference.
    user.email = f"deleted+{uid.hex}@deleted.invalid"
    user.full_name = None
    user.password_hash = None
    user.google_sub = None
    user.stripe_customer_id = None
    user.razorpay_customer_id = None
    user.is_active = False
    user.deleted_at = utcnow()
    db.flush()
