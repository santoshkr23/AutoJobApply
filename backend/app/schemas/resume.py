"""Domain schemas for candidate data (used by the API and stored as JSON)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _clean_list(values: list[str], limit: int = 200) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = (v or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s[:120])
    return out[:limit]


class ExperienceItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    company: str = Field(max_length=200)
    title: str = Field(max_length=200)
    location: str | None = Field(default=None, max_length=200)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("bullets")
    @classmethod
    def clean_bullets(cls, v: list[str]) -> list[str]:
        return [b.strip()[:600] for b in v if b and b.strip()]


class EducationItem(BaseModel):
    institution: str = Field(max_length=200)
    degree: str | None = Field(default=None, max_length=200)
    field: str | None = Field(default=None, max_length=200)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)


class CertificationItem(BaseModel):
    name: str = Field(max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    date: str | None = Field(default=None, max_length=40)


class ProjectItem(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=1500)
    technologies: list[str] = Field(default_factory=list)


class ParsedResume(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=255)
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=3000)
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=30)
    education: list[EducationItem] = Field(default_factory=list, max_length=15)
    certifications: list[CertificationItem] = Field(default_factory=list, max_length=40)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=30)
    links: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, v: list[str]) -> list[str]:
        return _clean_list(v)

    @field_validator("links")
    @classmethod
    def clean_links(cls, v: list[str]) -> list[str]:
        return _clean_list(v, 15)


class ResumeOut(BaseModel):
    id: uuid.UUID
    label: str
    original_filename: str
    content_type: str
    size_bytes: int
    parse_status: str
    parse_error: str | None
    parsed_data: ParsedResume | None
    ai_provider: str | None
    confirmed_at: datetime | None
    created_at: datetime


class ProfileOut(ParsedResume):
    total_experience_years: float | None = None
    country: str | None = None
    verified_at: datetime | None = None
    source_resume_id: uuid.UUID | None = None


class ProfileIn(ParsedResume):
    country: str | None = Field(default=None, min_length=2, max_length=2)
    total_experience_years: float | None = Field(default=None, ge=0, le=60)
