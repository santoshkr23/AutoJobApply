"""Shared FastAPI dependencies: authentication, CSRF, tenant-scoped lookups."""

import uuid
from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import Forbidden, NotFound, Unauthorized
from app.core.security import constant_time_equals
from app.models.user import AdminUser, AuthSession, User
from app.services.sessions import lookup_session

USER_COOKIE = "session"
ADMIN_COOKIE = "admin_session"
CSRF_COOKIE = "csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

DB = Annotated[Session, Depends(get_db)]


@dataclass
class Principal:
    session: AuthSession
    via_cookie: bool


def _extract_token(request: Request, cookie_name: str) -> tuple[str | None, bool]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip(), False
    token = request.cookies.get(cookie_name)
    return token, True


def _enforce_csrf(request: Request, session: AuthSession, via_cookie: bool) -> None:
    """Cookie-authenticated unsafe requests must echo the CSRF token (double submit)."""
    if not via_cookie or request.method in SAFE_METHODS:
        return
    header = request.headers.get(CSRF_HEADER, "")
    if not header or not constant_time_equals(header, session.csrf_token):
        raise Forbidden("CSRF validation failed", code="csrf_failed")


def get_current_user(request: Request, db: DB) -> User:
    token, via_cookie = _extract_token(request, USER_COOKIE)
    if not token:
        raise Unauthorized()
    session = lookup_session(db, token, "user")
    if session is None:
        raise Unauthorized("Session expired or invalid")
    _enforce_csrf(request, session, via_cookie)
    user = db.get(User, session.subject_id)
    if user is None or user.deleted_at is not None:
        raise Unauthorized("Account not found")
    if not user.is_active:
        raise Forbidden("This account has been disabled", code="account_disabled")
    request.state.session = session
    return user


def get_verified_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.email_verified_at is None:
        raise Forbidden("Please verify your email address first", code="email_not_verified")
    return user


def get_current_admin(request: Request, db: DB) -> AdminUser:
    token, via_cookie = _extract_token(request, ADMIN_COOKIE)
    if not token:
        raise Unauthorized()
    session = lookup_session(db, token, "admin")
    if session is None:
        raise Unauthorized("Admin session expired or invalid")
    _enforce_csrf(request, session, via_cookie)
    admin = db.get(AdminUser, session.subject_id)
    if admin is None or not admin.is_active:
        raise Forbidden("Admin account disabled")
    request.state.session = session
    return admin


CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUser = Annotated[User, Depends(get_verified_user)]
CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]

T = TypeVar("T")


def get_owned(db: Session, model: type[T], object_id: uuid.UUID, user: User) -> T:
    """Tenant isolation: fetch a row only if it belongs to `user`. Other users' rows look like 404."""
    obj = db.execute(
        select(model).where(model.id == object_id, model.user_id == user.id)  # type: ignore[attr-defined]
    ).scalar_one_or_none()
    if obj is None or getattr(obj, "deleted_at", None) is not None:
        raise NotFound()
    return obj
