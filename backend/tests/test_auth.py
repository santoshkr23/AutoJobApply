from app.core import ratelimit
from app.services import email as email_service
from tests.conftest import PASSWORD, latest_link_token, login_headers, register_user


def test_register_sends_verification_and_is_generic(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "New@Example.com", "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert r.status_code == 202
    assert len(email_service.OUTBOX) == 1
    assert email_service.OUTBOX[0]["to"] == "new@example.com"
    # Registering the same address again must look identical (no account enumeration) and send nothing.
    r2 = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": PASSWORD, "accept_terms": True, "accept_privacy": True},
    )
    assert r2.status_code == 202 and r2.json() == r.json()
    assert len(email_service.OUTBOX) == 1


def test_register_validation(client):
    base = {"email": "a@example.com", "accept_terms": True, "accept_privacy": True}
    assert client.post("/api/auth/register", json={**base, "password": "short1"}).status_code == 400
    assert client.post("/api/auth/register", json={**base, "password": "onlylettersnodigits"}).status_code == 400
    assert client.post("/api/auth/register", json={**base, "password": PASSWORD, "accept_terms": False}).status_code == 400
    assert client.post("/api/auth/register", json={**base, "email": "not-an-email", "password": PASSWORD}).status_code == 422


def test_passwords_are_hashed_not_stored_plaintext(client, db):
    from sqlalchemy import select

    from app.models import User

    register_user(client)
    user = db.execute(select(User)).scalar_one()
    assert user.password_hash and PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")


def test_login_flow_and_me(client):
    register_user(client)
    bad = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-password1"})
    assert bad.status_code == 401
    ok = client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert ok.status_code == 200
    assert ok.json()["token"] is None  # session token never in the body unless explicitly requested
    assert "session" in client.cookies and "csrf" in client.cookies
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
    assert me.json()["email_verified"] is True
    assert me.json()["plan"] == "free"


def test_unauthenticated_access_denied(client):
    assert client.get("/api/me").status_code == 401


def test_unknown_email_and_wrong_password_look_identical(client):
    register_user(client)
    a = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-password1"})
    b = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "wrong-password1"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_csrf_required_for_cookie_sessions(client):
    register_user(client)
    client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    # State-changing request with cookies but without the CSRF header is rejected.
    r = client.post("/api/auth/logout")
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = client.post("/api/auth/logout", headers={"X-CSRF-Token": client.cookies.get("csrf")})
    assert r.status_code == 200
    assert client.get("/api/me").status_code == 401  # session revoked server-side


def test_bearer_token_works_without_csrf(client):
    register_user(client)
    headers = login_headers(client)
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401


def test_password_reset_flow_revokes_sessions(client):
    register_user(client)
    headers = login_headers(client)
    assert client.post("/api/auth/forgot-password", json={"email": "alice@example.com"}).status_code == 202
    token = latest_link_token("reset-password")
    new_pw = "An0therStrongPass!"
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 200
    # Old session is dead, old password no longer works, token cannot be reused.
    assert client.get("/api/me", headers=headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": new_pw}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": new_pw}).status_code == 400


def test_forgot_password_does_not_leak_account_existence(client):
    a = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert a.status_code == 202
    assert email_service.OUTBOX == []


def test_verification_token_single_use_and_invalid(client):
    register_user(client, verify=False)
    token = latest_link_token("verify-email")
    assert client.post("/api/auth/verify-email", json={"token": "x" * 20}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400


def test_login_rate_limited(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    ratelimit.reset_rate_limits()
    try:
        codes = [
            client.post("/api/auth/login", json={"email": "x@example.com", "password": "wrong-password1"}).status_code
            for _ in range(14)
        ]
        assert 429 in codes
    finally:
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
        get_settings.cache_clear()
        ratelimit.reset_rate_limits()


def test_disabled_account_cannot_login(client, db):
    from sqlalchemy import select

    from app.models import User

    register_user(client)
    user = db.execute(select(User)).scalar_one()
    user.is_active = False
    db.commit()
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_disabled"


def test_google_login_reports_not_configured(client):
    r = client.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_not_configured"


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
