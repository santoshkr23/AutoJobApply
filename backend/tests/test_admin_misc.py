from sqlalchemy import select

from app.core.security import hash_password
from app.models import AdminUser, JobSource, User
from tests.test_applications import job_by_title, prepare_user

ADMIN_PW = "AdminPassw0rd!x"


def admin_headers(client, db, role="superadmin"):
    db.add(AdminUser(email="root@example.com", password_hash=hash_password(ADMIN_PW), role=role, is_active=True))
    db.commit()
    r = client.post("/api/admin/login", json={"email": "root@example.com", "password": ADMIN_PW}, headers={"X-Return-Token": "1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_admin_login_and_isolation_from_user_sessions(client, auth, db):
    assert client.get("/api/admin/stats", headers=auth).status_code == 401  # a user token is not an admin session
    assert client.get("/api/admin/stats").status_code == 401
    bad = client.post("/api/admin/login", json={"email": "root@example.com", "password": "nope"})
    assert bad.status_code == 401
    h = admin_headers(client, db)
    s = client.get("/api/admin/stats", headers=h).json()
    assert s["users"]["total"] >= 1 and "applications" in s
    assert client.get("/api/me", headers=h).status_code == 401  # and an admin token is not a user session


def test_admin_cookie_session_requires_csrf(client, db):
    db.add(AdminUser(email="root@example.com", password_hash=hash_password(ADMIN_PW), role="superadmin", is_active=True))
    db.commit()
    r = client.post("/api/admin/login", json={"email": "root@example.com", "password": ADMIN_PW})
    csrf = r.json()["csrf_token"]
    assert client.get("/api/admin/me").status_code == 200
    assert client.put("/api/admin/feature-flags/anything", json={"enabled": True}).status_code == 403  # no CSRF header
    ok = client.put("/api/admin/feature-flags/anything", json={"enabled": True}, headers={"X-CSRF-Token": csrf})
    assert ok.status_code in (200, 404)  # CSRF passed (flag may not exist)


def test_admin_plan_limits_validation_no_unlimited(client, db):
    h = admin_headers(client, db)
    ok = client.patch("/api/admin/plans/pro", headers=h, json={"limits": {"applications_per_month": 75}})
    assert ok.status_code == 200 and ok.json()["limits"]["applications_per_month"] == 75
    assert client.patch("/api/admin/plans/pro", headers=h, json={"limits": {"applications_per_month": "unlimited"}}).status_code == 422
    assert client.patch("/api/admin/plans/pro", headers=h, json={"limits": {"applications_per_month": -1}}).status_code == 422
    assert client.patch("/api/admin/plans/pro", headers=h, json={"limits": {"bogus": 1}}).status_code == 422


def test_support_role_cannot_change_things(client, db):
    h = admin_headers(client, db, role="support")
    assert client.get("/api/admin/users", headers=h).status_code == 200
    assert client.patch("/api/admin/plans/pro", headers=h, json={"is_active": False}).status_code == 403


def test_disable_user_revokes_access(client, auth, db):
    h = admin_headers(client, db)
    uid = db.execute(select(User)).scalars().first().id
    assert client.patch(f"/api/admin/users/{uid}", headers=h, json={"is_active": False}).status_code == 200
    assert client.get("/api/me", headers=auth).status_code in (401, 403)
    logs = client.get("/api/admin/audit-logs?action=admin.user", headers=h).json()
    assert logs["total"] >= 1


def test_admin_can_run_source_and_see_health(client, db):
    h = admin_headers(client, db)
    src = db.execute(select(JobSource).where(JobSource.key == "mock")).scalar_one()
    r = client.post(f"/api/admin/sources/{src.id}/run", headers=h)
    assert r.json()["status"] == "success" and r.json()["fetched"] == 13
    assert client.get("/api/admin/health", headers=h).json()["ai_provider"] == "mock"


def test_matching_weights_admin_update(client, db):
    h = admin_headers(client, db)
    assert client.put("/api/admin/settings/matching-weights", headers=h, json={"salary": 5}).json()["salary"] == 5
    assert client.put("/api/admin/settings/matching-weights", headers=h, json={"nonsense": 5}).status_code == 422


def test_dashboard_and_notifications(client, auth, db):
    prepare_user(client, auth, db)
    client.post("/api/matches/run", headers=auth)
    aid = client.post("/api/applications", headers=auth, json={"job_id": str(job_by_title(db, "Azure Data Engineer").id)}).json()["id"]
    client.post(f"/api/applications/{aid}/prepare", headers=auth)
    d = client.get("/api/dashboard", headers=auth).json()
    assert d["totals"]["matches"] > 0 and d["applications_by_status"]["PENDING_APPROVAL"] == 1 and d["totals"]["needs_action"] == 1
    assert d["top_matches"] and sum(d["match_score_distribution"].values()) > 0
    n = client.get("/api/notifications", headers=auth).json()
    assert n["unread"] >= 1
    nid = n["items"][0]["id"]
    assert client.post(f"/api/notifications/{nid}/read", headers=auth).status_code == 200
    assert client.post("/api/notifications/read-all", headers=auth).status_code == 200
    assert client.get("/api/notifications?unread_only=true", headers=auth).json()["unread"] == 0


def test_contact_form_validation_and_admin_visibility(client, db):
    assert client.post("/api/contact", json={"email": "bad", "subject": "Hi", "message": "short"}).status_code == 422
    ok = client.post("/api/contact", json={"email": "a@example.com", "subject": "Question", "message": "How do I export my data?"})
    assert ok.status_code == 201
    h = admin_headers(client, db)
    items = client.get("/api/admin/support?status=open", headers=h).json()
    assert len(items) == 1 and items[0]["subject"] == "Question"
    assert client.patch(f"/api/admin/support/{items[0]['id']}", headers=h).json()["status"] == "closed"


def test_maintenance_tasks_run(client, auth, db):
    from app.tasks import maintenance_tasks as m
    assert m.sync_subscriptions() == 0
    assert m.send_interview_reminders() == 0
    assert set(m.retention_cleanup()) == {"email_tokens", "sessions", "audit_logs", "failed_tasks"}
