"""Server-side sessions. Tokens are random, stored only as SHA-256 hashes, and revocable."""

import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.models.base import utcnow
from app.models.user import AuthSession


def create_session(
    db: Session,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, AuthSession]:
    s = get_settings()
    hours = s.admin_session_ttl_hours if subject_type == "admin" else s.session_ttl_hours
    token = new_token(32)
    now = utcnow()
    row = AuthSession(
        subject_type=subject_type,
        subject_id=subject_id,
        token_hash=hash_token(token),
        csrf_token=new_token(24),
        ip_address=ip,
        user_agent=(user_agent or "")[:255],
        created_at=now,
        expires_at=now + timedelta(hours=hours),
    )
    db.add(row)
    db.flush()
    return token, row


def lookup_session(db: Session, token: str, subject_type: str) -> AuthSession | None:
    row = db.execute(select(AuthSession).where(AuthSession.token_hash == hash_token(token))).scalar_one_or_none()
    if row is None or row.subject_type != subject_type or row.revoked_at is not None:
        return None
    if row.expires_at <= utcnow():
        return None
    return row


def revoke_session(db: Session, session: AuthSession) -> None:
    session.revoked_at = utcnow()


def revoke_all_for_subject(db: Session, subject_type: str, subject_id: uuid.UUID, *, except_id: uuid.UUID | None = None) -> None:
    stmt = (
        update(AuthSession)
        .where(AuthSession.subject_type == subject_type, AuthSession.subject_id == subject_id)
        .where(AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    if except_id is not None:
        stmt = stmt.where(AuthSession.id != except_id)
    db.execute(stmt)
