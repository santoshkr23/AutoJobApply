# Honest status

## Implemented and covered by automated tests
Auth/verification/reset, profile + resume parsing, preferences, job ingestion (mock + Adzuna-style connector interface), deterministic matching, AI tailoring with grounding checks, application state machine, consent-gated submission engine (Playwright against a local mock site only), CSV/XLSX export, billing with signed webhooks (sandbox provider exercised end-to-end), admin API, notifications, dashboard.
Frontend: public site, auth, onboarding, dashboard pages, admin panel; unit tests + a Playwright browser journey.

## Interface exists, NOT verified against the real service
- OpenAI provider (`AI_PROVIDER=openai`) - only the labelled mock provider is tested.
- Razorpay and Stripe live APIs - signature logic is unit-tested with fixtures; no real account was used.
- Google OAuth sign-in - needs client credentials.
- Real job boards / employer sites - automation only tested on the local mock site; adapters for specific boards are not provided.
- Docker images and GitHub Actions workflows - written but not executed in the authoring environment.
- Windows `.exe` - see desktop/README.md.

## Known gaps
Legal pages are templates; no user 2FA; no email deliverability setup; `workers/`, `shared/` are reserved (workers run from the backend image); no load testing.
