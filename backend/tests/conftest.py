"""Test harness.

Runs against PostgreSQL (TEST_DATABASE_URL, default: local `career_test`) and falls back to SQLite
if PostgreSQL is unreachable. Every test runs inside an outer transaction that is rolled back,
and the API plus background tasks share that single transaction.
"""

import os
import re
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="career-tests-")
_PG_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://career:career@localhost:5432/career_test")


def _pg_available(url: str) -> bool:
    try:
        from sqlalchemy import create_engine, text

        eng = create_engine(url, connect_args={"connect_timeout": 2})
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


_DB_URL = _PG_URL if _pg_available(_PG_URL) else f"sqlite:///{_TMP}/test.sqlite"

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "SECRET_KEY": "test-secret-key-test-secret-key-test-secret-key",
        "DATABASE_URL": _DB_URL,
        "RATE_LIMIT_ENABLED": "false",
        "EMAIL_PROVIDER": "console",
        "AI_PROVIDER": "mock",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_PATH": f"{_TMP}/storage",
        "AUTOMATION_SCREENSHOT_DIR": f"{_TMP}/screenshots",
        "CELERY_TASK_ALWAYS_EAGER": "true",
        "BILLING_SANDBOX_ENABLED": "true",
        "RAZORPAY_WEBHOOK_SECRET": "rzp-test-webhook-secret",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_secret",
        "FRONTEND_URL": "http://localhost:3000",
        "REDIS_URL": "redis://localhost:6379/15",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core import db as db_module  # noqa: E402
from app.core.ratelimit import reset_rate_limits  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import email as email_service  # noqa: E402

DB_IS_POSTGRES = _DB_URL.startswith("postgresql")


@pytest.fixture(scope="session")
def engine():
    kwargs = {"connect_args": {"check_same_thread": False}} if not DB_IS_POSTGRES else {}
    eng = create_engine(_DB_URL, **kwargs)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    outer = connection.begin()
    factory = sessionmaker(
        bind=connection, autoflush=False, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    # Route all app/worker code paths through this transaction.
    db_module._engine = engine
    db_module._SessionLocal = factory
    session = factory()
    from app.services.seed import seed_defaults

    seed_defaults(session)
    session.commit()
    reset_rate_limits()
    email_service.OUTBOX.clear()
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
        db_module._SessionLocal = None
        db_module._engine = None


@pytest.fixture()
def client(db):
    from app.main import create_app

    with TestClient(create_app(), base_url="http://testserver") as c:
        yield c


def latest_link_token(kind: str) -> str:
    """Extract the token from the most recent email containing `/<kind>?token=`."""
    for msg in reversed(email_service.OUTBOX):
        m = re.search(rf"/{kind}\?token=([A-Za-z0-9_\-]+)", msg["text"])
        if m:
            return m.group(1)
    raise AssertionError(f"No {kind} email found in outbox")


PASSWORD = "Str0ngPassw0rd!"


def register_user(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD, verify: bool = True):
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "Alice Test", "accept_terms": True, "accept_privacy": True},
    )
    assert r.status_code == 202, r.text
    if verify:
        token = latest_link_token("verify-email")
        assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200


def login_headers(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD) -> dict:
    """Log in as an API client and return Bearer headers (bypasses cookie/CSRF)."""
    r = client.post("/api/auth/login", json={"email": email, "password": password}, headers={"X-Return-Token": "1"})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def auth(client):
    register_user(client)
    return login_headers(client)


@pytest.fixture()
def auth_b(client):
    """A second, unrelated user for tenant-isolation tests."""
    register_user(client, "bob@example.com")
    return login_headers(client, "bob@example.com")


FIXTURES = Path(__file__).parent / "fixtures"
