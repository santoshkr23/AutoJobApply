"""Verified candidate profile management."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.user import User, UserConsent, UserPreferences, UserProfile
from app.schemas.profile import PreferencesIn
from app.schemas.resume import ParsedResume, ProfileIn, ProfileOut
from app.services.heuristics import total_experience_years


def get_profile(db: Session, user_id: uuid.UUID) -> UserProfile | None:
    return db.execute(select(UserProfile).where(UserProfile.user_id == user_id)).scalar_one_or_none()


def profile_to_dict(p: UserProfile) -> dict:
    """The structure given to AI/matching. Only verified data."""
    return {
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "location": p.location,
        "country": p.country,
        "headline": p.headline,
        "summary": p.summary,
        "skills": list(p.skills or []),
        "experience": list(p.experience or []),
        "education": list(p.education or []),
        "certifications": list(p.certifications or []),
        "projects": list(p.projects or []),
        "links": list(p.links or []),
        "total_experience_years": float(p.total_experience_years) if p.total_experience_years is not None else None,
    }


def profile_out(p: UserProfile | None) -> ProfileOut:
    if p is None:
        return ProfileOut()
    d = profile_to_dict(p)
    return ProfileOut(**d, verified_at=p.verified_at, source_resume_id=p.source_resume_id)


def upsert_profile(db: Session, user: User, data: ProfileIn, *, source_resume_id: uuid.UUID | None = None) -> UserProfile:
    p = get_profile(db, user.id)
    if p is None:
        p = UserProfile(user_id=user.id)
        db.add(p)
    dumped = data.model_dump(exclude={"country", "total_experience_years"})
    p.full_name = dumped["full_name"]
    p.email = dumped["email"]
    p.phone = dumped["phone"]
    p.location = dumped["location"]
    p.headline = dumped["headline"]
    p.summary = dumped["summary"]
    p.skills = dumped["skills"]
    p.experience = dumped["experience"]
    p.education = dumped["education"]
    p.certifications = dumped["certifications"]
    p.projects = dumped["projects"]
    p.links = dumped["links"]
    p.country = data.country.upper() if data.country else p.country
    years = data.total_experience_years
    if years is None:
        years = total_experience_years(dumped["experience"])
    p.total_experience_years = years
    if source_resume_id:
        p.source_resume_id = source_resume_id
    p.verified_at = utcnow()
    if dumped["full_name"] and not user.full_name:
        user.full_name = dumped["full_name"]
    db.flush()
    return p


def get_preferences(db: Session, user_id: uuid.UUID) -> UserPreferences | None:
    return db.execute(select(UserPreferences).where(UserPreferences.user_id == user_id)).scalar_one_or_none()


def upsert_preferences(db: Session, user: User, data: PreferencesIn) -> UserPreferences:
    prefs = get_preferences(db, user.id)
    if prefs is None:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)
    for k, v in data.model_dump().items():
        setattr(prefs, k, v)
    db.flush()
    return prefs


def latest_consents(db: Session, user_id: uuid.UUID) -> dict[str, UserConsent]:
    rows = db.execute(
        select(UserConsent).where(UserConsent.user_id == user_id).order_by(UserConsent.created_at.asc())
    ).scalars()
    latest: dict[str, UserConsent] = {}
    for r in rows:
        latest[r.consent_type] = r  # later rows override earlier ones
    return latest


def has_consent(db: Session, user_id: uuid.UUID, consent_type: str) -> bool:
    c = latest_consents(db, user_id).get(consent_type)
    return bool(c and c.granted)


__all__ = ["ParsedResume"]
