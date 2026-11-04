import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, SoftDelete, Timestamps, UUIDPk


class ApplicationStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    MATCHED = "MATCHED"
    RESUME_GENERATED = "RESUME_GENERATED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    WITHDRAWN = "WITHDRAWN"


class Application(UUIDPk, Timestamps, SoftDelete, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
        Index("ix_applications_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    match_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("job_matches.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default=ApplicationStatus.MATCHED.value, nullable=False)
    # Deterministic key (user + job) so repeated submissions can never create duplicates.
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    adapter: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_ref: Mapped[str | None] = mapped_column(String(255))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    needs_user_action: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ApplicationEvent(UUIDPk, Base):
    __tablename__ = "application_events"
    __table_args__ = (Index("ix_application_events_app", "application_id", "created_at"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str | None] = mapped_column(String(24))
    message: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationDocument(UUIDPk, Timestamps, SoftDelete, Base):
    """Documents attached to an application: tailored resume and cover letter."""

    __tablename__ = "application_documents"
    __table_args__ = (Index("ix_application_documents_app", "application_id", "kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # resume | cover_letter
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("resume_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)  # draft | approved
    content: Mapped[dict | None] = mapped_column(JSONType)  # cover letter text lives here
    pdf_key: Mapped[str | None] = mapped_column(String(512))
    docx_key: Mapped[str | None] = mapped_column(String(512))
    ai_provider: Mapped[str | None] = mapped_column(String(32))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
