"""Idempotent seed data: plans, settings, feature flags. Safe to run on every deploy."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing import Plan
from app.models.misc import FeatureFlag, SystemSetting
from app.services.quotas import DEFAULT_PLANS
from app.services.settings_store import DEFAULTS, set_setting

FEATURE_FLAGS = {
    "auto_apply": "Enable the application automation engine",
    "new_user_signups": "Allow new registrations",
    "ai_resume_customization": "Enable AI resume customization",
    "google_login": "Show Google sign-in",
}


def seed_defaults(db: Session) -> None:
    # Existing rows are never overwritten: admins own plan limits, prices and settings.
    for spec in DEFAULT_PLANS:
        if db.execute(select(Plan).where(Plan.key == spec["key"])).scalar_one_or_none() is None:
            db.add(Plan(**spec))

    for key, value in DEFAULTS.items():
        if db.get(SystemSetting, key) is None:
            set_setting(db, key, value)

    for key, desc in FEATURE_FLAGS.items():
        if db.execute(select(FeatureFlag).where(FeatureFlag.key == key)).scalar_one_or_none() is None:
            db.add(FeatureFlag(key=key, description=desc, enabled=True))
    db.flush()

    from app.services.jobs_service import seed_job_sources

    seed_job_sources(db)
