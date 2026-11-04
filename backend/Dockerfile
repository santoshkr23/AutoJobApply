# Build context is the repository root:  docker build -f backend/Dockerfile --target api .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ /app/backend/
COPY automation/ /app/automation/
COPY scripts/ /app/scripts/
ENV PYTHONPATH=/app/backend:/app/automation
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown -R app /data /app
USER app

# --- Background workers (AI, discovery, email, maintenance)
FROM base AS worker
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-Q", "default,ai,discovery", "-l", "info", "--concurrency", "4"]

# --- Scheduler
FROM base AS beat
CMD ["celery", "-A", "app.tasks.celery_app", "beat", "-l", "info", "-s", "/tmp/celerybeat-schedule"]

# --- Browser automation worker (needs Chromium)
FROM base AS automation
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium && chmod -R a+rX /ms-playwright
USER app
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-Q", "automation", "-l", "info", "--concurrency", "2"]
# --- API server
FROM base AS api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=5 CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["sh", "-c", "alembic upgrade head && python /app/scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
