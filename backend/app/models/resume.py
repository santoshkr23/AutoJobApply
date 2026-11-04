import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, SoftDelete, Timestamps, UUIDPk


class Resume(UUIDPk, Timestamps, SoftDelete, Base):
    """Uploaded master resumes. Never modified after upload; only parsed data may be corrected."""

    __tablename__ = "resumes"
    __table_args__ = (Index("ix_resumes_user", "user_id", "deleted_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(120), default="Master resume", nullable=False)
    is_master: Mapped[bool] = mapped_column(default=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    parse_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[dict | None] = mapped_column(JSONType)
    ai_provider: Mapped[str | None] = mapped_column(String(32))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResumeVersion(UUIDPk, Timestamps, SoftDelete, Base):
    """A tailored resume generated for one job. Always derived from the verified profile."""

    __tablename__ = "resume_versions"
    __table_args__ = (Index("ix_resume_versions_user_job", "user_id", "job_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("resumes.id", ondelete="SET NULL"))
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    match_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("job_matches.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)  # draft|approved|rejected
    content: Mapped[dict] = mapped_column(JSONType, nullable=False)
    change_log: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    validation: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    pdf_key: Mapped[str | None] = mapped_column(String(512))
    docx_key: Mapped[str | None] = mapped_column(String(512))
    ai_provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
