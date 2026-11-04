# Deployment

## Local (Docker Compose)
```bash
cp .env.example .env
# set SECRET_KEY:      python -c "import secrets; print(secrets.token_urlsafe(48))"
# set ENCRYPTION_KEY:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up --build
python scripts/create_admin.py   # (inside the backend container: docker compose exec backend python /app/scripts/create_admin.py)
```
Web: http://localhost:3000 - API docs: http://localhost:8000/api/docs - dev mailbox: http://localhost:8025 - 

> Status: `docker compose config` validates; the images were **not built or run in the authoring sandbox** (no Docker daemon). Run it once and report problems. The same code path was tested without Docker (see README).

## Production checklist
- `ENVIRONMENT=production`, `COOKIE_SECURE=true`, HTTPS in front (nginx/Caddy/cloud LB); production refuses weak secrets and the billing sandbox.
- Strong unique `SECRET_KEY`, `ENCRYPTION_KEY`, DB password; keep them in a secrets manager, never in git.
- Use managed PostgreSQL and Redis or add volumes + backups (below). For production switch to S3 (`STORAGE_BACKEND=s3`, `S3_*` vars) or keep the `appdata` volume and back it up.
- Replace Mailpit with real SMTP. Set `AI_PROVIDER=openai` + key only after testing it (it is not tested live).
- Payments: set provider keys and register webhooks `POST /api/webhooks/razorpay` and `/api/webhooks/stripe`. Plans activate only from verified webhooks. Test in each provider's test mode first.
- `AUTOMATION_ALLOWED_DOMAINS`: only add domains you are permitted to automate. CAPTCHA/login/MFA pages always fall back to manual.
- Review and replace the template Privacy Policy / Terms with lawyer-approved text.
- Scale: run more `worker` replicas; keep one `beat`.

## Backup and restore
```bash
# backup
docker compose exec -T postgres pg_dump -U career -Fc career > backup-$(date +%F).dump
docker run --rm -v autojobapply_appdata:/data -v "$PWD":/out alpine tar czf /out/files-$(date +%F).tgz -C /data .
# restore (stop app services first)
docker compose exec -T postgres pg_restore -U career -d career --clean --if-exists < backup.dump
docker run --rm -v autojobapply_appdata:/data -v "$PWD":/in alpine tar xzf /in/files.tgz -C /data
```
Schedule the dump (cron/CI) and copy it off-host. Test a restore periodically - an untested backup is not a backup.

## Migrations
`alembic upgrade head` runs on API start. Roll back with `alembic downgrade -1` after restoring a backup if needed.
