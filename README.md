# AutoJobApply - AI Career Agent

A SaaS platform that finds jobs matching your profile, scores them transparently, tailors a resume and cover letter **without inventing facts**, and - only with your explicit consent and per-application approval - helps submit applications. Every application is tracked honestly; the platform never fabricates a success.

**Stack:** Next.js 14 (TypeScript, Tailwind) - FastAPI - SQLAlchemy/Alembic - PostgreSQL - Celery/Redis - Playwright - S3-compatible storage - Razorpay/Stripe - Docker.

Read [docs/STATUS.md](docs/STATUS.md) first: it lists what is tested and what is only an interface.

## Quick start (Docker)
```bash
cp .env.example .env     # set SECRET_KEY and ENCRYPTION_KEY (commands inside the file)
docker compose up --build
```
Open http://localhost:3000. Dev emails appear at http://localhost:8025. More: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Quick start (without Docker)
```bash
# PostgreSQL + Redis running locally
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt && python -m playwright install chromium
cp ../.env.example .env && alembic upgrade head && python ../scripts/seed.py
uvicorn app.main:app --reload                 # API :8000
celery -A app.tasks.celery_app:celery_app worker -B -l info   # optional; CELERY_TASK_ALWAYS_EAGER=true runs tasks inline
cd ../frontend && npm ci && BACKEND_URL=http://localhost:8000 npm run dev   # web :3000
python scripts/create_admin.py                # admin panel at /admin/login
```

## Plans
FREE: 10 matched jobs/month, no auto-apply. PRO ₹499, PREMIUM ₹999. All limits are admin-editable (Admin > Plans); none are unlimited. Plans activate only after a verified payment webhook. In development a clearly labelled **sandbox** payment provider is used when no real keys are set (refused in production).

## Testing - actual results (last run in the authoring sandbox)
| Suite | Result |
|---|---|
| Backend `pytest` | 99 passed |
| Backend `ruff check` | clean |
| Frontend `vitest` | 15 passed |
| Frontend `tsc --noEmit` / `next build` | clean / 34 routes |
| Browser e2e (`scripts/e2e.sh`) | 3 passed (register, verify, onboard, subscribe via sandbox, match, tailor, approve, export) |
| Docker build / compose up | **not run** (no Docker daemon available); `compose config` validates |
| GitHub Actions | written, not yet observed running |

Run them: `cd backend && pytest`, `cd frontend && npm test`, `./scripts/e2e.sh`.

## Safety principles (enforced in code and tests)
No CAPTCHA/MFA/login bypass - those pages become "manual required". Submission requires consent + approved documents + per-application approval, re-checked at run time. APPLIED only from a verified confirmation or a labelled user self-report. AI output is validated against your profile. No secrets in git.

## Layout
`frontend/` web app - `backend/` API, models, services, Celery tasks - `automation/` Playwright adapters + local mock careers site - `scripts/` seed, admin, e2e - `docs/` deployment, security, status - `desktop/` Windows wrapper - `infrastructure/`, `workers/`, `shared/`, `database/`: reserved/placeholders (see docs/STATUS.md).

## License / legal
Privacy Policy and Terms pages are templates and must be reviewed by a lawyer before launch.
