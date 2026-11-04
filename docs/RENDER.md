# Deploy on Render

> Written without a Render account to test against: the blueprint is validated as YAML only. Expect to fix small things on the first deploy and report them.

## 1. Push and create
1. Push this repo to GitHub (already at `santoshkr23/AutoJobApply`).
2. In Render: **New > Blueprint**, pick the repo. It creates: Postgres, Key Value (Redis), `autojobapply-api` (FastAPI) and `autojobapply-web` (Next.js).
3. When asked for values marked "sync: false", leave them empty for now except `ENCRYPTION_KEY` (below). Click **Apply**.

## 2. Fill the variables (API service > Environment), then redeploy it
| Variable | Value |
|---|---|
| `ENCRYPTION_KEY` | a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `FRONTEND_URL`, `API_URL`, `CORS_ORIGINS` | the public URL of the **web** service, e.g. `https://autojobapply-web.onrender.com` (all three the same) |

`SECRET_KEY` is generated for you. Database and Redis URLs are wired automatically.

## 3. Use it
- Open the web URL (first load after idle takes ~1 minute on the free plan).
- Verification emails: the starter setup uses `EMAIL_PROVIDER=console`, so the link is printed in the **API service logs** (search for `[email:console]`). To send real email set `EMAIL_PROVIDER=smtp` and `SMTP_HOST/PORT/USER/PASSWORD/STARTTLS` (e.g. Brevo, Resend, SES) and `EMAIL_FROM`.
- Admin account: API service > **Shell** (paid plans) or run locally against the same DB: `python scripts/create_admin.py you@example.com`.
- Sample jobs: Admin > Sources > enable "mock" > Run.

## Limits of the free starter setup
- **Files are not durable**: `STORAGE_BACKEND=local` writes to temporary disk, so uploaded resumes and generated documents disappear on restart/redeploy (parsed profile data stays in the database). For durable files create a Cloudflare R2 or AWS S3 bucket and set `STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`.
- **Free Postgres expires** after about 30 days; free web services sleep when idle.
- **No background worker**: `CELERY_TASK_ALWAYS_EAGER=true` runs jobs inside the API request, so scheduled job discovery does not run. Enable the commented `worker` block in `render.yaml` (paid) and set eager to `false` for scheduling.
- **Browser auto-apply is not available on Render** in this setup (no Chromium worker). Applications stay in manual mode.
- `ENVIRONMENT=development` is used only because production mode refuses console email and sandbox payments. Before real users: real SMTP, real payment keys + webhooks, `ENVIRONMENT=production`, `BILLING_SANDBOX_ENABLED=false`.
