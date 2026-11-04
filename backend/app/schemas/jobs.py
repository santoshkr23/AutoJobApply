import uuid
from datetime import datetime

from pydantic import BaseModel


class JobOut(BaseModel):
    id: uuid.UUID
    title: str
    company: str
    location_text: str | None
    country: str | None
    city: str | None
    work_mode: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: str | None
    employment_type: str | None
    experience_min: int | None
    experience_max: int | None
    skills: list[str]
    category: str | None
    url: str
    posted_at: datetime | None
    expires_at: datetime | None
    source: str
    attribution: str | None
    is_sample: bool
    match_score: int | None = None


class JobDetailOut(JobOut):
    description: str
    analysis: dict
    visa_sponsorship: bool | None


class JobPage(BaseModel):
    items: list[JobOut]
    total: int
    page: int
    page_size: int
