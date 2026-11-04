"""Registration, verification, login/logout, password reset, Google OAuth, password change."""

import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update

from app.core.audit import audit
from app.core.config import get_settings
from app.core.deps import CSRF_COOKIE, DB, USER_COOKIE, CurrentUser
from app.core.errors import AppError, Forbidden, ServiceNotConfigured, Unauthorized
from app.core.ratelimit import client_ip, hit, rate_limit
from app.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    validate_password_strength,
    verify_password,
)
from app.models.base import utcnow
from app.models.user import EmailToken, User, UserConsent
from app.schemas.auth import (
    ChangePasswordIn,
    EmailIn,
    LoginIn,
    MessageOut,
    RegisterIn,
    ResetPasswordIn,
    SessionOut,
    TokenIn,
    UserOut,
)
from app.services import email as email_service
from app.services.sessions import create_session, revoke_all_for_subject, revoke_session
from app.tasks.celery_app import enqueue
from app.tasks.email_tasks import send_email_task

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_REGISTER_MSG = "If this email can be registered, a verification link has been sent."
GENERIC_RESET_MSG = "If an account exists for this email, a reset link has been sent."
CURRENT_TERMS_VERSION = "2026-11"


def user_out(db: DB, user: User) -> UserOut:
    from app.services.quotas import get_plan_for_user

    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        email_verified=user.email_verified_at is not None,
        onboarding_step=user.onboarding_step,
        onboarding_completed=user.onboarding_completed_at is not None,
        has_password=bool(user.password_hash),
        created_at=user.created_at,
        plan=get_plan_for_user(db, user).key,
    )


def set_session_cookies(response: Response, token: str, csrf: str, max_age: int, *, cookie_name: str = USER_COOKIE) -> None:
    s = get_settings()
    common = dict(max_age=max_age, secure=s.cookie_secure, samesite="lax", domain=s.cookie_domain, path="/")
    response.set_cookie(cookie_name, token, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **common)  # readable by the SPA for double-submit


def clear_session_cookies(response: Response, *, cookie_name: str = USER_COOKIE) -> None:
    response.delete_cookie(cookie_name, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _issue_email_token(db: DB, user: User, purpose: str) -> str:
    # Invalidate previous unused tokens of the same purpose.
    db.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    token = new_token(32)
    ttl = get_settings().email_token_ttl_minutes
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(minutes=ttl),
            created_at=utcnow(),
        )
    )
    return token


def _consume_email_token(db: DB, token: str, purpose: str) -> User:
    row = db.execute(
        select(EmailToken).where(EmailToken.token_hash == hash_token(token), EmailToken.purpose == purpose)
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise AppError("This link is invalid or has expired.", code="invalid_token")
    user = db.get(User, row.user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("This link is invalid or has expired.", code="invalid_token")
    row.used_at = utcnow()
    return user


def _send_verification(db: DB, user: User) -> None:
    s = get_settings()
    token = _issue_email_token(db, user, "verify_email")
    url = f"{s.frontend_url}/verify-email?token={token}"
    text, html = email_service.render(
        f"Verify your email for {s.brand_name}",
        ["Welcome! Please confirm your email address to activate your account. This link expires in "
         f"{s.email_token_ttl_minutes} minutes."],
        ("Verify email", url),
    )
    _queue_after_commit(db, user.email, f"Verify your email - {s.brand_name}", text, html)


def _queue_after_commit(db: DB, to: str, subject: str, text: str, html: str) -> None:
    from sqlalchemy import event

    @event.listens_for(db, "after_commit", once=True)
    def _go(_session):  # noqa: ANN001
        enqueue(send_email_task, to, subject, text, html)


def _record_consent(db: DB, user: User, request: Request, consent_type: str, granted: bool) -> None:
    db.add(
        UserConsent(
            user_id=user.id,
            consent_type=consent_type,
            version=CURRENT_TERMS_VERSION,
            granted=granted,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:255],
            created_at=utcnow(),
        )
    )


def _start_session(db: DB, request: Request, response: Response, user: User) -> SessionOut:
    s = get_settings()
    token, row = create_session(
        db, subject_type="user", subject_id=user.id, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    user.last_login_at = utcnow()
    set_session_cookies(response, token, row.csrf_token, s.session_ttl_hours * 3600)
    wants_token = request.headers.get("x-return-token") == "1"
    return SessionOut(user=user_out(db, user), csrf_token=row.csrf_token, token=token if wants_token else None)


@router.post("/register", status_code=202, response_model=MessageOut, dependencies=[Depends(rate_limit("register", 5))])
def register(body: RegisterIn, request: Request, db: DB) -> MessageOut:
    if not (body.accept_terms and body.accept_privacy):
        raise AppError("You must accept the Terms and the Privacy Policy.", code="consent_required")
    problems = validate_password_strength(body.password)
    if problems:
        raise AppError(problems[0], code="weak_password", details=problems)

    existing = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if existing is not None:
        # Do not reveal whether the email is registered (account enumeration).
        audit(db, action="auth.register_duplicate", request=request, meta={"email_hash": hash_token(body.email)[:12]})
        db.commit()
        return MessageOut(message=GENERIC_REGISTER_MSG)

    user = User(email=body.email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(user)
    db.flush()
    _record_consent(db, user, request, "terms", True)
    _record_consent(db, user, request, "privacy", True)
    _send_verification(db, user)
    audit(db, action="auth.register", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return MessageOut(message=GENERIC_REGISTER_MSG)


@router.post("/verify-email", response_model=MessageOut, dependencies=[Depends(rate_limit("verify", 20))])
def verify_email(body: TokenIn, request: Request, db: DB) -> MessageOut:
    user = _consume_email_token(db, body.token, "verify_email")
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    audit(db, action="auth.email_verified", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return MessageOut(message="Email verified. You can now sign in.")


@router.post("/resend-verification", status_code=202, response_model=MessageOut, dependencies=[Depends(rate_limit("resend", 3))])
def resend_verification(body: EmailIn, db: DB) -> MessageOut:
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if user and user.email_verified_at is None and user.deleted_at is None and user.is_active:
        _send_verification(db, user)
        db.commit()
    return MessageOut(message="If the account exists and is unverified, a new link has been sent.")


@router.post("/login", response_model=SessionOut, dependencies=[Depends(rate_limit("login", 20))])
def login(body: LoginIn, request: Request, response: Response, db: DB) -> SessionOut:
    # Per-account throttle against credential stuffing (15 minute window).
    if get_settings().rate_limit_enabled and not hit(f"login_email:{body.email}", 10, 900):
        raise AppError("Too many failed attempts. Try again in a few minutes.", code="rate_limited", status_code=429)
    user = db.execute(select(User).where(User.email == body.email, User.deleted_at.is_(None))).scalar_one_or_none()
    ok = verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None:
        audit(db, action="auth.login_failed", request=request, meta={"email_hash": hash_token(body.email)[:12]})
        db.commit()
        raise Unauthorized("Invalid email or password")
    if not user.is_active:
        raise Forbidden("This account has been disabled", code="account_disabled")
    if needs_rehash(user.password_hash or ""):
        user.password_hash = hash_password(body.password)
    out = _start_session(db, request, response, user)
    audit(db, action="auth.login", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return out


@router.post("/logout", response_model=MessageOut)
def logout(request: Request, response: Response, db: DB, user: CurrentUser) -> MessageOut:
    revoke_session(db, request.state.session)
    audit(db, action="auth.logout", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    clear_session_cookies(response)
    return MessageOut(message="Signed out")


@router.post("/forgot-password", status_code=202, response_model=MessageOut, dependencies=[Depends(rate_limit("forgot", 5))])
def forgot_password(body: EmailIn, request: Request, db: DB) -> MessageOut:
    s = get_settings()
    user = db.execute(select(User).where(User.email == body.email, User.deleted_at.is_(None))).scalar_one_or_none()
    if user and user.is_active:
        token = _issue_email_token(db, user, "reset_password")
        url = f"{s.frontend_url}/reset-password?token={token}"
        text, html = email_service.render(
            f"Reset your {s.brand_name} password",
            [f"We received a request to reset your password. The link expires in {s.email_token_ttl_minutes} minutes. "
             "If you did not request this, you can ignore this email."],
            ("Reset password", url),
        )
        _queue_after_commit(db, user.email, f"Reset your password - {s.brand_name}", text, html)
        audit(db, action="auth.password_reset_requested", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return MessageOut(message=GENERIC_RESET_MSG)


@router.post("/reset-password", response_model=MessageOut, dependencies=[Depends(rate_limit("reset", 10))])
def reset_password(body: ResetPasswordIn, request: Request, db: DB) -> MessageOut:
    problems = validate_password_strength(body.new_password)
    if problems:
        raise AppError(problems[0], code="weak_password", details=problems)
    user = _consume_email_token(db, body.token, "reset_password")
    user.password_hash = hash_password(body.new_password)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()  # they proved control of the mailbox
    revoke_all_for_subject(db, "user", user.id)  # sign out everywhere
    audit(db, action="auth.password_reset", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return MessageOut(message="Password updated. Please sign in.")


@router.post("/change-password", response_model=MessageOut, dependencies=[Depends(rate_limit("chpw", 10))])
def change_password(body: ChangePasswordIn, request: Request, db: DB, user: CurrentUser) -> MessageOut:
    if not verify_password(body.current_password, user.password_hash):
        raise Unauthorized("Current password is incorrect")
    problems = validate_password_strength(body.new_password)
    if problems:
        raise AppError(problems[0], code="weak_password", details=problems)
    user.password_hash = hash_password(body.new_password)
    revoke_all_for_subject(db, "user", user.id, except_id=request.state.session.id)
    audit(db, action="auth.password_changed", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return MessageOut(message="Password changed")


# --------------------------------------------------------------------------- Google OAuth
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
OAUTH_STATE_COOKIE = "oauth_state"


def _google_redirect_uri() -> str:
    return f"{get_settings().api_url}/api/auth/google/callback"


@router.get("/google/login", dependencies=[Depends(rate_limit("google", 20))])
def google_login() -> RedirectResponse:
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret):
        raise ServiceNotConfigured("Google sign-in is not configured on this server")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    resp.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, secure=s.cookie_secure, samesite="lax")
    return resp


@router.get("/google/callback", dependencies=[Depends(rate_limit("google", 20))])
def google_callback(request: Request, db: DB, code: str = "", state: str = "") -> RedirectResponse:
    s = get_settings()
    if not (s.google_client_id and s.google_client_secret):
        raise ServiceNotConfigured("Google sign-in is not configured on this server")
    expected = request.cookies.get(OAUTH_STATE_COOKIE, "")
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        raise AppError("Invalid OAuth state", code="oauth_state_invalid")
    try:
        with httpx.Client(timeout=10) as client:
            tok = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": s.google_client_id,
                    "client_secret": s.google_client_secret,
                    "redirect_uri": _google_redirect_uri(),
                    "grant_type": "authorization_code",
                },
            )
            tok.raise_for_status()
            info = client.get(
                GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tok.json()['access_token']}"}
            )
            info.raise_for_status()
            profile = info.json()
    except (httpx.HTTPError, KeyError) as exc:
        log.warning("Google OAuth exchange failed: %s", exc)
        raise AppError("Google sign-in failed. Please try again.", code="oauth_failed") from exc

    if not profile.get("email_verified") or not profile.get("email") or not profile.get("sub"):
        raise AppError("Your Google email address is not verified.", code="oauth_email_unverified")
    email = str(profile["email"]).lower()
    sub = str(profile["sub"])

    user = db.execute(select(User).where(User.google_sub == sub)).scalar_one_or_none()
    if user is None:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is not None and user.deleted_at is None:
            if user.email_verified_at is None:
                # Pre-hijack protection: an unverified local account may have been created by someone else.
                user.password_hash = None
            user.google_sub = sub
            user.email_verified_at = user.email_verified_at or utcnow()
        else:
            user = User(
                email=email, google_sub=sub, full_name=profile.get("name"), email_verified_at=utcnow()
            )
            db.add(user)
            db.flush()
            _record_consent(db, user, request, "terms", True)
            _record_consent(db, user, request, "privacy", True)
    if user.deleted_at is not None or not user.is_active:
        raise Forbidden("This account is not available", code="account_disabled")

    response = RedirectResponse(f"{s.frontend_url}/dashboard")
    token, row = create_session(
        db, subject_type="user", subject_id=user.id, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    user.last_login_at = utcnow()
    set_session_cookies(response, token, row.csrf_token, s.session_ttl_hours * 3600)
    response.delete_cookie(OAUTH_STATE_COOKIE)
    audit(db, action="auth.google_login", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return response
