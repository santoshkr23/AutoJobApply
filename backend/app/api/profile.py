"""Profile, job preferences, consents and onboarding progress."""

from fastapi import APIRouter, Request

from app.core.audit import audit
from app.core.deps import DB, VerifiedUser
from app.core.errors import AppError
from app.core.ratelimit import client_ip
from app.models.base import utcnow
from app.models.user import UserConsent
from app.schemas.auth import MessageOut
from app.schemas.profile import ConsentIn, ConsentOut, NotificationPrefsIn, PreferencesIn, PreferencesOut
from app.schemas.resume import ProfileIn, ProfileOut
from app.services import profiles
from app.services.notifications import NOTIFICATION_TYPES, effective_prefs

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileOut)
def get_profile(db: DB, user: VerifiedUser) -> ProfileOut:
    return profiles.profile_out(profiles.get_profile(db, user.id))


@router.put("/profile", response_model=ProfileOut)
def update_profile(body: ProfileIn, request: Request, db: DB, user: VerifiedUser) -> ProfileOut:
    p = profiles.upsert_profile(db, user, body)
    audit(db, action="profile.updated", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return profiles.profile_out(p)


def _prefs_out(db: DB, user) -> PreferencesOut:
    p = profiles.get_preferences(db, user.id)
    if p is None:
        return PreferencesOut()
    base = PreferencesIn.model_validate(
        {
            "target_titles": p.target_titles, "required_skills": p.required_skills, "categories": p.categories,
            "countries": p.countries, "cities": p.cities, "work_modes": p.work_modes,
            "salary_min": p.salary_min, "salary_max": p.salary_max, "salary_currency": p.salary_currency,
            "experience_min": float(p.experience_min) if p.experience_min is not None else None,
            "experience_max": float(p.experience_max) if p.experience_max is not None else None,
            "employment_types": p.employment_types, "needs_visa_sponsorship": p.needs_visa_sponsorship,
            "open_to_relocation": p.open_to_relocation, "min_match_score": p.min_match_score,
            "require_approval": p.require_approval, "auto_prepare_applications": p.auto_prepare_applications,
        }
    )
    return PreferencesOut(**base.model_dump(), notification_prefs=p.notification_prefs or {})


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(db: DB, user: VerifiedUser) -> PreferencesOut:
    return _prefs_out(db, user)


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(body: PreferencesIn, request: Request, db: DB, user: VerifiedUser) -> PreferencesOut:
    profiles.upsert_preferences(db, user, body)
    user.onboarding_step = max(user.onboarding_step, 4)
    audit(db, action="preferences.updated", actor_type="user", actor_id=user.id, request=request)
    db.commit()
    return _prefs_out(db, user)


@router.get("/consents", response_model=list[ConsentOut])
def list_consents(db: DB, user: VerifiedUser) -> list[ConsentOut]:
    return [
        ConsentOut(consent_type=c.consent_type, granted=c.granted, version=c.version, created_at=c.created_at)
        for c in profiles.latest_consents(db, user.id).values()
    ]


@router.post("/consents", response_model=ConsentOut, status_code=201)
def record_consent(body: ConsentIn, request: Request, db: DB, user: VerifiedUser) -> ConsentOut:
    """Append-only: withdrawing consent adds a new row, it never edits history."""
    row = UserConsent(
        user_id=user.id,
        consent_type=body.consent_type,
        version="2026-11",
        granted=body.granted,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:255],
        created_at=utcnow(),
    )
    db.add(row)
    audit(db, action="consent.recorded", actor_type="user", actor_id=user.id, request=request,
          meta={"type": body.consent_type, "granted": body.granted})
    db.commit()
    return ConsentOut(consent_type=row.consent_type, granted=row.granted, version=row.version, created_at=row.created_at)


@router.post("/onboarding/complete", response_model=MessageOut)
def complete_onboarding(db: DB, user: VerifiedUser) -> MessageOut:
    profile = profiles.get_profile(db, user.id)
    if profile is None or profile.verified_at is None:
        raise AppError("Please verify your resume details first.", code="profile_not_verified")
    if profiles.get_preferences(db, user.id) is None:
        raise AppError("Please set your job preferences first.", code="preferences_missing")
    user.onboarding_step = 6
    user.onboarding_completed_at = user.onboarding_completed_at or utcnow()
    db.commit()
    return MessageOut(message="Onboarding complete")


@router.get("/notification-preferences")
def get_notification_prefs(db: DB, user: VerifiedUser) -> dict:
    return {"types": NOTIFICATION_TYPES, "prefs": effective_prefs(db, user.id)}


@router.put("/notification-preferences")
def set_notification_prefs(body: NotificationPrefsIn, db: DB, user: VerifiedUser) -> dict:
    clean = {t: {k: bool(v) for k, v in p.items() if k in ("email", "in_app")} for t, p in body.prefs.items() if t in NOTIFICATION_TYPES}
    prefs = profiles.get_preferences(db, user.id)
    if prefs is None:
        from app.models.user import UserPreferences

        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)
    prefs.notification_prefs = clean
    db.commit()
    return {"types": NOTIFICATION_TYPES, "prefs": effective_prefs(db, user.id)}
