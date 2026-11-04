# Architecture

AI Career Agent is a multi-tenant SaaS: job seekers upload a resume, get matched to jobs from authorized
sources, receive tailored resumes and cover letters, and (where a site allows it and the user consents)
have applications submitted for them.

```
 Browser ─► Next.js (frontend) ──► FastAPI (backend/app)  ──► PostgreSQL
                                        │   │                   ▲
                                        │   └─► Redis ──► Celery workers (queues: default, ai,
                                        │                  discovery, automation) ──► Playwright
                                        └─► S3-compatible storage (private, signed URLs)
 Razorpay / Stripe ──signed webhooks──► FastAPI        OpenAI API ◄── backend AI service
```

## Repository layout

| Path | Purpose |
|---|---|
| `backend/app` | FastAPI app: `api/` routers, `models/` SQLAlchemy, `services/` business logic, `connectors/` job sources, `tasks/` Celery tasks |
| `backend/alembic` | Database migrations |
| `automation/` | Playwright application adapters, CAPTCHA detection, mock job site used by tests |
| `workers/` | Worker/beat entrypoints and container definition |
| `frontend/` | Next.js (TypeScript, Tailwind, shadcn-style components) |
| `infrastructure/` | Docker, nginx, deployment manifests |
| `scripts/` | Seed/admin/backup helpers |
| `docs/` | This documentation |

## Key design decisions

* **Synchronous SQLAlchemy 2.0 + FastAPI threadpool.** Simple, and identical code runs in API and Celery workers.
* **Tenant isolation at the application layer.** Every user-owned table has `user_id`; all reads go through
  `get_owned()` or an explicit `user_id` filter; other users' rows return 404. Covered by tests.
* **Sessions are server-side.** Opaque random tokens, only SHA-256 stored, revocable. Browser clients use
  HttpOnly cookies + double-submit CSRF; API clients may use a Bearer token. Admins are a separate identity
  (`admin_users`) with their own sessions and cookie.
* **AI never invents facts.** The verified profile is the only source of truth. LLM output is schema
  validated, then checked by `grounding.py` (no new employers, dates, certifications, skills or numbers).
  Anything failing validation is replaced by the original text and recorded in the change log.
* **Prompt-injection defence.** Resumes and job descriptions are wrapped as untrusted data, the model has no
  tools, output must match a strict JSON schema, and grounding validation runs on the result.
* **Deterministic matching.** Scores come from a transparent, weighted algorithm (weights editable by admins),
  so results are explainable and testable. The LLM only helps analyze job text and write explanations.
* **Applications are consent-gated and verified.** Statuses follow an explicit state machine; `APPLIED` is
  only set after the adapter verifies a confirmation. CAPTCHA/MFA/login walls always hand control back to the
  user (`MANUAL_REQUIRED`). Idempotency keys and an atomic claim prevent duplicate submissions.
* **Payments are webhook-driven.** Frontend success pages never grant access. Webhooks are signature
  verified, deduplicated (`webhook_events`), and processed idempotently.
* **Sandbox implementations are explicit.** Without credentials the real integration interface exists and a
  clearly labelled sandbox (mock AI, console email, local storage, sandbox billing, mock job source) is used
  in development only. Production configuration validation refuses sandbox settings.

## Data model

27 tables (see `backend/app/models`): the 19 requested tables plus `sessions`, `email_tokens`,
`webhook_events`, `discovery_runs`, `feature_flags`, `system_settings`, `support_requests`,
`failed_tasks`, and `application_documents`.

## Application state machine

```
DISCOVERED → MATCHED → RESUME_GENERATED → PENDING_APPROVAL → APPLYING → APPLIED → INTERVIEW → OFFER
                                                          ↘ MANUAL_REQUIRED   ↘ REJECTED / WITHDRAWN
                                                          ↘ FAILED (retryable → PENDING_APPROVAL)
```
