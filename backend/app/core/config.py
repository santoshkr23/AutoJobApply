"""Application configuration. All secrets come from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Branding (configurable so the product can be renamed)
    brand_name: str = "AI Career Agent"
    brand_support_email: str = "support@example.com"
    frontend_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"

    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False

    # Security
    secret_key: str = INSECURE_DEFAULT_SECRET
    # Fernet key for field-level encryption (base64 urlsafe 32 bytes).
    encryption_key: str = ""
    session_ttl_hours: int = 24 * 7
    admin_session_ttl_hours: int = 8
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cors_origins: str = "http://localhost:3000"
    email_token_ttl_minutes: int = 60

    # Database / queue
    database_url: str = "postgresql+psycopg://career:career@localhost:5432/career"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    # Object storage (S3 compatible). If s3_endpoint_url/bucket empty -> local dev storage.
    storage_backend: Literal["s3", "local"] = "local"
    s3_endpoint_url: str = ""
    s3_bucket: str = "career-agent"
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    local_storage_path: str = ".local-storage"
    signed_url_ttl_seconds: int = 300
    max_upload_mb: int = 8

    # AI
    ai_provider: Literal["openai", "mock"] = "mock"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model_default: str = "gpt-4o-mini"
    openai_model_advanced: str = "gpt-4o"

    # Email
    email_provider: Literal["console", "smtp"] = "console"
    email_from: str = "AI Career Agent <no-reply@example.com>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Billing
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Sandbox billing simulates a provider locally. Never allowed in staging/production.
    billing_sandbox_enabled: bool = False
    billing_sandbox_secret: str = "sandbox-webhook-secret"

    # Job discovery
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    enable_mock_connector: bool = True
    job_max_age_days: int = 45
    job_missing_runs_before_expiry: int = 3

    # Automation
    # Domains where the generic form adapter is allowed to run. Only add domains whose
    # terms permit automated applications or that you operate yourself.
    automation_allowed_domains: str = "localhost,127.0.0.1"
    automation_headless: bool = True
    automation_screenshot_dir: str = ".local-storage/screenshots"
    automation_max_attempts: int = 3

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 10
    rate_limit_default_per_minute: int = 240

    # Data retention
    retention_audit_log_days: int = 365
    retention_deleted_account_days: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def automation_domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.automation_allowed_domains.split(",") if d.strip()]

    @property
    def is_production_like(self) -> bool:
        return self.environment in ("staging", "production")

    @model_validator(mode="after")
    def _validate_production_safety(self) -> "Settings":
        if self.is_production_like:
            problems = []
            if self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32:
                problems.append("SECRET_KEY must be a random value of at least 32 characters")
            if not self.encryption_key:
                problems.append("ENCRYPTION_KEY must be set")
            if self.billing_sandbox_enabled:
                problems.append("BILLING_SANDBOX_ENABLED must be false")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true")
            if self.ai_provider == "mock":
                problems.append("AI_PROVIDER=mock is not allowed")
            if problems:
                raise ValueError("Unsafe configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
