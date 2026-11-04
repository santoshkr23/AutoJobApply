from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    SUBMITTED = "submitted"            # submission verified by a confirmation signal on the page
    MANUAL_REQUIRED = "manual_required"  # a human must act (CAPTCHA, login, MFA, unsupported form, ...)
    RETRYABLE = "retryable"            # transient problem (timeout, network): safe to try again
    FAILED = "failed"                  # permanent problem


@dataclass
class Applicant:
    full_name: str
    email: str
    phone: str | None = None
    location: str | None = None


@dataclass
class SubmissionContext:
    application_id: str
    job_title: str
    company: str
    apply_url: str
    applicant: Applicant
    resume_bytes: bytes
    resume_filename: str
    cover_letter_text: str
    allowed_domains: list[str] = field(default_factory=list)
    headless: bool = True
    timeout_ms: int = 20_000


@dataclass
class SubmissionResult:
    outcome: Outcome
    code: str
    message: str
    confirmation_ref: str | None = None
    evidence: dict = field(default_factory=dict)


class Adapter:
    name = "base"

    def can_handle(self, url: str, allowed_domains: list[str]) -> bool:
        raise NotImplementedError

    def submit(self, ctx: SubmissionContext) -> SubmissionResult:
        raise NotImplementedError
