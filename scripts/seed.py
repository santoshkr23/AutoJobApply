"""Seed plans, settings, flags and (disabled) job sources into the configured database:  python scripts/seed.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.db import session_scope  # noqa: E402
from app.services.jobs_service import seed_job_sources  # noqa: E402
from app.services.seed import seed_defaults  # noqa: E402

with session_scope() as db:
    seed_defaults(db)
    seed_job_sources(db)
print("Seeded plans, settings, flags and job sources.")
