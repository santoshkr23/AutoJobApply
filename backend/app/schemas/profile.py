from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

WORK_MODES = {"remote", "hybrid", "onsite"}
EMPLOYMENT_TYPES = {"full_time", "part_time", "contract", "internship", "temporary"}
CONSENT_TYPES = {"auto_apply", "ai_processing", "marketing"}


def _strs(v: list[str], limit: int = 50, max_len: int = 100) -> list[str]:
    out, seen = [], set()
    for s in v:
        s = (s or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s[:max_len])
    return out[:limit]


class PreferencesIn(BaseModel):
    target_titles: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    work_modes: list[str] = Field(default_factory=list)
    salary_min: int | None = Field(default=None, ge=0, le=1_000_000_000)
    salary_max: int | None = Field(default=None, ge=0, le=1_000_000_000)
    salary_currency: str = Field(default="INR", min_length=3, max_length=3)
    experience_min: float | None = Field(default=None, ge=0, le=60)
    experience_max: float | None = Field(default=None, ge=0, le=60)
    employment_types: list[str] = Field(default_factory=list)
    needs_visa_sponsorship: bool = False
    open_to_relocation: bool = False
    min_match_score: int = Field(default=70, ge=0, le=100)
    require_approval: bool = True
    auto_prepare_applications: bool = False

    @field_validator("target_titles", "required_skills", "categories", "cities")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        return _strs(v)

    @field_validator("countries")
    @classmethod
    def countries_iso(cls, v: list[str]) -> list[str]:
        out = []
        for c in v:
            c = c.strip().upper()
            if len(c) != 2 or not c.isalpha():
                raise ValueError("Countries must be 2-letter ISO codes (e.g. IN, US, GB)")
            if c not in out:
                out.append(c)
        return out

    @field_validator("work_modes")
    @classmethod
    def modes(cls, v: list[str]) -> list[str]:
        v = [m.strip().lower() for m in v]
        bad = set(v) - WORK_MODES
        if bad:
            raise ValueError(f"Invalid work mode(s): {sorted(bad)}")
        return list(dict.fromkeys(v))

    @field_validator("employment_types")
    @classmethod
    def types(cls, v: list[str]) -> list[str]:
        v = [m.strip().lower() for m in v]
        bad = set(v) - EMPLOYMENT_TYPES
        if bad:
            raise ValueError(f"Invalid employment type(s): {sorted(bad)}")
        return list(dict.fromkeys(v))

    @field_validator("salary_currency")
    @classmethod
    def currency(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def ranges(self):
        if self.salary_min is not None and self.salary_max is not None and self.salary_min > self.salary_max:
            raise ValueError("Minimum salary cannot exceed maximum salary")
        if self.experience_min is not None and self.experience_max is not None and self.experience_min > self.experience_max:
            raise ValueError("Minimum experience cannot exceed maximum experience")
        return self


class PreferencesOut(PreferencesIn):
    notification_prefs: dict = Field(default_factory=dict)


class ConsentIn(BaseModel):
    consent_type: str
    granted: bool

    @field_validator("consent_type")
    @classmethod
    def valid(cls, v: str) -> str:
        if v not in CONSENT_TYPES:
            raise ValueError(f"consent_type must be one of {sorted(CONSENT_TYPES)}")
        return v


class ConsentOut(BaseModel):
    consent_type: str
    granted: bool
    version: str
    created_at: datetime


class NotificationPrefsIn(BaseModel):
    prefs: dict[str, dict[str, bool]]
