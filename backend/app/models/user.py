import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.models.base import Base, JSONType, SoftDelete, Timestamps, UUIDPk


class User(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)  # stored lower-cased
    password_hash: Mapped[str | None] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disabled_reason: Mapped[str | None] = mapped_column(String(255))
    onboarding_step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))
    razorpay_customer_id: Mapped[str | None] = mapped_column(String(64))

    profile: Mapped["UserProfile | None"] = relationship(back_populates="user", uselist=False)
    preferences: Mapped["UserPreferences | None"] = relationship(back_populates="user", uselist=False)


class UserProfile(UUIDPk, Timestamps, Base):
    """Verified candidate profile: the single source of truth for AI generation."""

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(EncryptedText())
    location: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(2))
    headline: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    experience: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    education: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    certifications: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    projects: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    links: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    total_experience_years: Mapped[float | None] = mapped_column(Numeric(4, 1))
    source_resume_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("resumes.id", ondelete="SET NULL"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="profile")


class UserPreferences(UUIDPk, Timestamps, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    target_titles: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    required_skills: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    categories: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    countries: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    cities: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    work_modes: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)  # remote/hybrid/onsite
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    experience_min: Mapped[float | None] = mapped_column(Numeric(4, 1))
    experience_max: Mapped[float | None] = mapped_column(Numeric(4, 1))
    employment_types: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    needs_visa_sponsorship: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    open_to_relocation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_match_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_prepare_applications: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_prefs: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    last_match_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="preferences")


class UserConsent(UUIDPk, Base):
    """Append-only consent ledger. The latest row per (user, type) decides."""

    __tablename__ = "user_consents"
    __table_args__ = (Index("ix_user_consents_user_type", "user_id", "consent_type", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1", nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthSession(UUIDPk, Base):
    """Server-side sessions. Only a SHA-256 of the token is stored."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_subject", "subject_type", "subject_id"),)

    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)  # user | admin
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailToken(UUIDPk, Base):
    __tablename__ = "email_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)  # verify_email | reset_password
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminUser(UUIDPk, Timestamps, Base):
    """Admins are a separate identity from end users (own credentials and sessions)."""

    __tablename__ = "admin_users"
    __table_args__ = (UniqueConstraint("email", name="uq_admin_users_email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin", nullable=False)  # superadmin | admin | support
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
