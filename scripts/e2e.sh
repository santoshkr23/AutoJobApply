#!/usr/bin/env bash
# Runs the browser end-to-end journey against a locally started stack.
# Needs: PostgreSQL + Redis running, backend venv installed, frontend built (npm run build).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}"
LOG=/tmp/e2e-backend.log
cd "$ROOT/backend"
[ -f .venv/bin/activate ] && source .venv/bin/activate
alembic upgrade head
python "$ROOT/scripts/seed.py"
ENVIRONMENT=development CELERY_TASK_ALWAYS_EAGER=true RATE_LIMIT_ENABLED=false BILLING_SANDBOX_ENABLED=true \
  uvicorn app.main:app --port 8000 > "$LOG" 2>&1 &
BACK=$!
cd "$ROOT/frontend"
BACKEND_URL=http://localhost:8000 npx next start -p 3000 > /tmp/e2e-frontend.log 2>&1 &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null || true' EXIT
for i in $(seq 1 60); do curl -fs localhost:8000/api/health >/dev/null && curl -fs localhost:3000 >/dev/null && break; sleep 1; done
# Sample jobs: an admin would normally enable and run the sample source from the admin panel.
cd "$ROOT/backend" && python - <<'PY'
from sqlalchemy import select
from app.core.db import session_scope
from app.models import JobSource
from app.services.jobs_service import run_source
with session_scope() as db:
    s = db.execute(select(JobSource).where(JobSource.key == "mock")).scalar_one()
    s.enabled = True
    run_source(db, s)
PY
cd "$ROOT/frontend" && E2E_BACKEND_LOG=$LOG npx playwright test "$@"
