import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.jobs import JobOut


class MatchOut(BaseModel):
    id: uuid.UUID
    score: int
    status: str
    recommendation: str
    skills_matched: list[str]
    missing_skills: list[str]
    experience_match: dict
    location_match: dict
    salary_match: dict
    explanation: str
    details: dict
    created_at: datetime
    job: JobOut


class MatchPage(BaseModel):
    items: list[MatchOut]
    total: int
    page: int
    page_size: int


class MatchRunOut(BaseModel):
    evaluated: int
    saved: int
    below_threshold: int
    quota_blocked: int
    already_matched: int
    queued: bool = False


class MatchStatusIn(BaseModel):
    status: str
