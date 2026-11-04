import hashlib
import hmac
import json
import time

import httpx
import respx
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Payment, Plan, Subscription, User
from app.services.billing import sandbox
from app.services.billing import service as billing


def plan_key(client, auth):
    return client.get("/api/billing/subscription", headers=auth).json()["plan"]["key"]


def sandbox_checkout(client, auth, plan="pro"):
    r = client.post("/api/billing/checkout", headers=auth, json={"plan_key": plan, "provider": "sandbox"})
    assert r.status_code == 200, r.text
    return r.json()["checkout_url"].split("sandbox_sub=")[1].split("&")[0]


def test_public_plans_list_matches_spec(client):
    d = client.get("/api/billing/plans").json()
    prices = {p["key"]: p["price_inr"] for p in d["plans"]}
    assert prices == {"free": 0, "pro": 49900, "premium": 99900}
    assert "sandbox" in d["providers"] and "razorpay" not in d["providers"]  # unconfigured providers are not advertised
    assert all(v != "unlimited" for p in d["plans"] for v in p["limits"].values())


def test_checkout_alone_never_activates_a_plan(client, auth):
    sandbox_checkout(client, auth)
    assert plan_key(client, auth) == "free"  # a frontend redirect/claim proves nothing


def test_sandbox_payment_via_signed_webhook_activates_plan_and_invoice(client, auth, db):
    sub = sandbox_checkout(client, auth)
    r = client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": sub})
    assert r.status_code == 200 and r.json()["results"] == ["processed", "processed"]
    d = client.get("/api/billing/subscription", headers=auth).json()
    assert d["plan"]["key"] == "pro" and d["subscription"]["status"] == "active"
    pays = client.get("/api/billing/payments", headers=auth).json()
    assert len(pays) == 1 and pays[0]["status"] == "succeeded" and pays[0]["invoice_number"].startswith("INV-")
    inv = client.get(f"/api/billing/payments/{pays[0]['id']}/invoice", headers=auth).json()
    assert inv["plan"] == "Pro" and inv["amount"] == 49900


def test_webhook_rejects_bad_signature_and_dedupes(client, auth, db):
    sub_id = sandbox_checkout(client, auth)
    uid = db.execute(select(User)).scalars().first().id
    raw = sandbox.build_event(kind="subscription_activated", user_id=uid, plan_key="pro", amount=49900, currency="INR", sub_id=sub_id)
    assert client.post("/api/webhooks/sandbox", content=raw, headers={"x-sandbox-signature": "bad"}).status_code == 400
    assert plan_key(client, auth) == "free"
    ok = {"x-sandbox-signature": sandbox.sign(raw)}
    assert client.post("/api/webhooks/sandbox", content=raw, headers=ok).json() == {"status": "processed"}
    assert client.post("/api/webhooks/sandbox", content=raw, headers=ok).json() == {"status": "duplicate"}
    tampered = raw.replace(b'"pro"', b'"premium"')
    assert client.post("/api/webhooks/sandbox", content=tampered, headers=ok).status_code == 400


def test_failed_payment_gives_grace_period(client, auth, db):
    sub = sandbox_checkout(client, auth)
    client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": sub})
    uid = db.execute(select(User)).scalars().first().id
    raw = sandbox.build_event(kind="payment_failed", user_id=uid, plan_key="pro", amount=49900, currency="INR", sub_id=sub)
    client.post("/api/webhooks/sandbox", content=raw, headers={"x-sandbox-signature": sandbox.sign(raw)})
    d = client.get("/api/billing/subscription", headers=auth).json()
    assert d["subscription"]["status"] == "past_due" and d["subscription"]["failed_payment_count"] == 1
    assert d["plan"]["key"] == "pro"  # still entitled inside the grace window


def test_cancel_keeps_access_until_period_end(client, auth, db):
    sub = sandbox_checkout(client, auth, "premium")
    client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": sub})
    r = client.post("/api/billing/cancel", headers=auth)
    assert r.status_code == 200 and r.json()["cancel_at_period_end"] is True
    uid = db.execute(select(User)).scalars().first().id
    raw = sandbox.build_event(kind="subscription_canceled", user_id=uid, plan_key="premium", amount=0, currency="INR", sub_id=sub)
    client.post("/api/webhooks/sandbox", content=raw, headers={"x-sandbox-signature": sandbox.sign(raw)})
    assert plan_key(client, auth) == "premium"  # paid through the end of the period


def test_upgrade_replaces_previous_subscription(client, auth, db):
    s1 = sandbox_checkout(client, auth, "pro")
    client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": s1})
    s2 = sandbox_checkout(client, auth, "premium")
    client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": s2})
    assert plan_key(client, auth) == "premium"
    statuses = sorted(s.status for s in db.execute(select(Subscription)).scalars())
    assert statuses == ["active", "canceled"]


def test_refund_updates_payment(client, auth, db):
    sub = sandbox_checkout(client, auth)
    client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": sub})
    pay = db.execute(select(Payment)).scalar_one()
    billing.refund_payment(db, pay, 10000, None)
    assert pay.status == "partially_refunded" and pay.refunded_amount == 10000
    billing.refund_payment(db, pay, None, None)
    assert pay.status == "refunded"


def test_invoices_are_private(client, auth, auth_b, db):
    sub = sandbox_checkout(client, auth)
    client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": sub})
    pid = client.get("/api/billing/payments", headers=auth).json()[0]["id"]
    assert client.get(f"/api/billing/payments/{pid}/invoice", headers=auth_b).status_code == 404
    assert client.get("/api/billing/payments", headers=auth_b).json() == []


def test_unknown_plan_and_unconfigured_provider(client, auth):
    assert client.post("/api/billing/checkout", headers=auth, json={"plan_key": "free", "provider": "sandbox"}).status_code == 422
    r = client.post("/api/billing/checkout", headers=auth, json={"plan_key": "pro", "provider": "razorpay"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_not_configured"
    assert client.post("/api/billing/checkout", headers=auth, json={"plan_key": "pro", "provider": "paypal"}).status_code == 404


# ----------------------------------------------------------------------------- real providers (HTTP + signatures)
def _set_env(monkeypatch, **kv):
    for k, v in kv.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def test_razorpay_webhook_signature_and_activation(client, auth, db, monkeypatch):
    _set_env(monkeypatch, RAZORPAY_KEY_ID="k", RAZORPAY_KEY_SECRET="s", RAZORPAY_WEBHOOK_SECRET="whsec")
    try:
        uid = db.execute(select(User)).scalars().first().id
        body = json.dumps({"id": "evt1", "event": "subscription.activated", "payload": {"subscription": {"entity": {
            "id": "sub_rzp1", "notes": {"user_id": str(uid), "plan_key": "pro"}, "current_start": 1760000000, "current_end": 4070000000}}}}).encode()
        good = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
        assert client.post("/api/webhooks/razorpay", content=body, headers={"x-razorpay-signature": "0" * 64}).status_code == 400
        assert plan_key(client, auth) == "free"
        r = client.post("/api/webhooks/razorpay", content=body, headers={"x-razorpay-signature": good, "x-razorpay-event-id": "evt1"})
        assert r.json() == {"status": "processed"} and plan_key(client, auth) == "pro"
        charged = json.dumps({"id": "evt2", "event": "subscription.charged", "payload": {
            "subscription": {"entity": {"id": "sub_rzp1", "notes": {"user_id": str(uid), "plan_key": "pro"}}},
            "payment": {"entity": {"id": "pay_1", "amount": 49900, "currency": "INR"}}}}).encode()
        client.post("/api/webhooks/razorpay", content=charged, headers={"x-razorpay-signature": hmac.new(b"whsec", charged, hashlib.sha256).hexdigest()})
        assert client.get("/api/billing/payments", headers=auth).json()[0]["amount"] == 49900
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


@respx.mock
def test_razorpay_checkout_creates_remote_subscription(client, auth, db, monkeypatch):
    _set_env(monkeypatch, RAZORPAY_KEY_ID="k", RAZORPAY_KEY_SECRET="s", RAZORPAY_WEBHOOK_SECRET="whsec")
    try:
        db.execute(select(Plan).where(Plan.key == "pro")).scalar_one().razorpay_plan_id = "plan_X"
        db.commit()
        route = respx.post("https://api.razorpay.com/v1/subscriptions").mock(
            return_value=httpx.Response(200, json={"id": "sub_new", "short_url": "https://rzp.io/i/abc"}))
        r = client.post("/api/billing/checkout", headers=auth, json={"plan_key": "pro", "provider": "razorpay"})
        assert r.status_code == 200 and r.json()["checkout_url"] == "https://rzp.io/i/abc"
        sent = json.loads(route.calls[0].request.content)
        assert sent["plan_id"] == "plan_X" and sent["notes"]["plan_key"] == "pro"
        assert plan_key(client, auth) == "free"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_stripe_signature_tolerance_and_events(client, auth, db, monkeypatch):
    _set_env(monkeypatch, STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET="whsec_x")
    try:
        uid = str(db.execute(select(User)).scalars().first().id)
        body = json.dumps({"id": "evt_s1", "type": "checkout.session.completed", "data": {"object": {
            "mode": "subscription", "payment_status": "paid", "subscription": "sub_st1",
            "metadata": {"user_id": uid, "plan_key": "premium"}}}}).encode()

        def header(ts, secret="whsec_x"):
            return f"t={ts},v1=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()

        now = int(time.time())
        assert client.post("/api/webhooks/stripe", content=body, headers={"stripe-signature": header(now, "wrong")}).status_code == 400
        assert client.post("/api/webhooks/stripe", content=body, headers={"stripe-signature": header(now - 3600)}).status_code == 400  # replay
        r = client.post("/api/webhooks/stripe", content=body, headers={"stripe-signature": header(now)})
        assert r.json() == {"status": "processed"} and plan_key(client, auth) == "premium"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_sandbox_endpoints_hidden_in_production(client, auth, monkeypatch):
    _set_env(monkeypatch, ENVIRONMENT="production", SECRET_KEY="x" * 40, ENCRYPTION_KEY="kJ0vSx3Z0V0Zr0m7mS2m3nq2o0o8O3m7l1c3m2n4b5k=",
             COOKIE_SECURE="true", AI_PROVIDER="openai", BILLING_SANDBOX_ENABLED="false")
    try:
        assert client.post("/api/billing/sandbox/complete", headers=auth, json={"subscription_id": "x"}).status_code in (404, 401, 403)
        assert "sandbox" not in billing.available_providers()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
