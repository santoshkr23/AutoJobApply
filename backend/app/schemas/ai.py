"""Strict (no defaults) models used as structured-output schemas for the LLM.

OpenAI strict structured outputs require every field to be present, so optional values are `X | None`
and lists are always required. Outputs are re-validated and grounded before anything is stored.
"""

from pydantic import BaseModel


class LLMExperience(BaseModel):
    company: str
    title: str
    location: str | None
    start_date: str | None
    end_date: str | None
    is_current: bool
    bullets: list[str]


class LLMEducation(BaseModel):
    institution: str
    degree: str | None
    field: str | None
    start_date: str | None
    end_date: str | None


class LLMCertification(BaseModel):
    name: str
    issuer: str | None
    date: str | None


class LLMProject(BaseModel):
    name: str
    description: str | None
    technologies: list[str]


class LLMParsedResume(BaseModel):
    full_name: str | None
    email: str | None
    phone: str | None
    location: str | None
    headline: str | None
    summary: str | None
    skills: list[str]
    experience: list[LLMExperience]
    education: list[LLMEducation]
    certifications: list[LLMCertification]
    projects: list[LLMProject]
    links: list[str]


class LLMJobAnalysis(BaseModel):
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    min_years_experience: int | None
    max_years_experience: int | None
    seniority: str | None  # intern|junior|mid|senior|lead|principal|manager
    education_required: str | None  # none|bachelor|master|phd
    certifications_mentioned: list[str]
    visa_sponsorship: bool | None  # true=offered, false=explicitly not offered, null=unknown
    work_mode: str | None  # remote|hybrid|onsite
    suspicious_instructions_detected: bool


class LLMTailoredBullet(BaseModel):
    text: str
    source_bullet_index: int  # index into the original bullets of that experience


class LLMTailoredExperience(BaseModel):
    experience_id: str
    bullets: list[LLMTailoredBullet]


class LLMTailoredResume(BaseModel):
    summary: str
    prioritized_skills: list[str]  # must be a subset of the candidate's verified skills
    experience: list[LLMTailoredExperience]
    section_order: list[str]  # e.g. ["summary","skills","experience","projects","education","certifications"]


class LLMCoverLetter(BaseModel):
    greeting: str
    paragraphs: list[str]
    closing: str


class LLMMatchExplanation(BaseModel):
    explanation: str
    recommendation_reason: str
