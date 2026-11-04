"""Admin-editable settings stored in the database, with code defaults."""

from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.misc import SystemSetting

DEFAULT_MATCHING_WEIGHTS: dict[str, float] = {
    "required_skills": 30,
    "preferred_skills": 8,
    "experience": 14,
    "responsibilities": 10,
    "education": 5,
    "certifications": 4,
    "location": 10,
    "salary": 7,
    "seniority": 7,
    "visa": 5,
}

DEFAULT_JOB_CATEGORIES: list[dict] = [
    {"key": "data_engineer", "label": "Data Engineer", "keywords": ["data engineer", "etl", "data pipeline", "big data"]},
    {"key": "azure_data_engineer", "label": "Azure Data Engineer", "keywords": ["azure data", "data factory", "synapse", "adf"]},
    {"key": "databricks_engineer", "label": "Databricks Engineer", "keywords": ["databricks", "delta lake", "pyspark"]},
    {"key": "software_engineer", "label": "Software Engineer", "keywords": ["software engineer", "backend", "full stack", "developer"]},
    {"key": "data_scientist", "label": "Data Scientist", "keywords": ["data scientist", "machine learning", "ml engineer"]},
    {"key": "data_analyst", "label": "Data Analyst", "keywords": ["data analyst", "bi developer", "business intelligence", "power bi"]},
    {"key": "cloud_engineer", "label": "Cloud Engineer", "keywords": ["cloud engineer", "cloud architect", "solutions architect"]},
    {"key": "devops_engineer", "label": "DevOps Engineer", "keywords": ["devops", "sre", "site reliability", "platform engineer"]},
]

DEFAULTS: dict[str, object] = {
    "matching_weights": DEFAULT_MATCHING_WEIGHTS,
    "job_categories": DEFAULT_JOB_CATEGORIES,
}


def get_setting(db: Session, key: str, default=None):
    row = db.get(SystemSetting, key)
    if row is not None:
        return row.value
    return DEFAULTS.get(key, default)


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=value, updated_at=utcnow()))
    else:
        row.value = value
        row.updated_at = utcnow()


def matching_weights(db: Session) -> dict[str, float]:
    stored = get_setting(db, "matching_weights") or {}
    weights = dict(DEFAULT_MATCHING_WEIGHTS)
    weights.update({k: float(v) for k, v in stored.items() if k in weights and float(v) >= 0})
    return weights
