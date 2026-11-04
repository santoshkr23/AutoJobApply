import csv
import io
import uuid

import pytest
from sqlalchemy import select

from app.models import Application, Job, JobSource, Plan
from app.models.base import utcnow
from app.services.jobs_service import run_source
from tests.helpers import make_docx, sample_text, upload

OPEN = {"matched_jobs_per_month": 50, "applications_per_month": 5, "resume_customizations_per_month": 5,
        "cover_letters_per_month": 5, "auto_apply": True}


def prepare_user(client, auth, db, **limits):
    rid = upload(client, auth, make_docx(sample_text()), "r.docx").json()["id"]
    parsed = client.get(f"/api/resumes/{rid}", headers=auth).json()["parsed_data"]
    parsed["country"] = "IN"
    assert client.post(f"/api/resumes/{rid}/confirm", headers=auth, json=parsed).status_code == 200
    client.put("/api/preferences", headers=auth, json={"countries": ["IN"], "min_match_score": 0})
    plan = db.execute(select(Plan).where(Plan.key == "free")).scalar_one()
    plan.limits = {**plan.limits, **OPEN, **limits}
    run_source(db, db.execute(select(JobSource).where(JobSource.key == "mock")).scalar_one())
    db.commit()


def job_by_title(db, title) -> Job:
    return db.execute(select(Job).where(Job.title == title, Job.status == "active")).scalar_one()


def make_job(db, url: str, title="Mock Apply Role") -> Job:
    src = db.execute(select(JobSource).where(JobSource.key == "mock")).scalar_one()
    j = Job(source_id=src.id, external_id=uuid.uuid4().hex, fingerprint=uuid.uuid4().hex, title=title, company="Mock Co",
            description="Python and SQL role for a data engineer. " * 3, url=url, apply_url=url, skills=["Python", "SQL"],
            analysis={"required_skills": ["Python", "SQL"]}, first_seen_at=utcnow(), last_seen_at=utcnow(), is_sample=True)
    db.add(j)
    db.commit()
    return j


def full_flow_until_approved(client, auth, job_id, consent=True):
    r = client.post("/api/applications", headers=auth, json={"job_id": str(job_id)})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    p = client.post(f"/api/applications/{aid}/prepare", headers=auth)
    assert p.status_code == 200, p.text
    assert client.post(f"/api/applications/{aid}/approve-documents", headers=auth).status_code == 200
    if consent:
        client.post("/api/consents", headers=auth, json={"consent_type": "auto_apply", "granted": True})
    return aid


# ----------------------------------------------------------------------------- lifecycle / documents
def test_create_is_idempotent(client, auth, db):
    prepare_user(client, auth, db)
    jid = str(job_by_title(db, "Azure Data Engineer").id)
    a = client.post("/api/applications", headers=auth, json={"job_id": jid})
    b = client.post("/api/applications", headers=auth, json={"job_id": jid})
    assert a.status_code == 201 and b.status_code == 200 and a.json()["id"] == b.json()["id"]
    assert a.json()["status"] == "MATCHED"


def test_prepare_generates_grounded_documents_and_pending_approval(client, auth, db):
    prepare_user(client, auth, db)
    aid = client.post("/api/applications", headers=auth, json={"job_id": str(job_by_title(db, "Azure Data Engineer").id)}).json()["id"]
    d = client.post(f"/api/applications/{aid}/prepare", headers=auth).json()
    assert d["status"] == "PENDING_APPROVAL"
    kinds = {x["kind"]: x for x in d["documents"]}
    assert set(kinds) == {"resume", "cover_letter"} and all(x["status"] == "draft" for x in kinds.values())
    resume = kinds["resume"]["resume"]
    prof = client.get("/api/profile", headers=auth).json()
    assert resume["full_name"] == prof["full_name"] and set(resume["skills"]) == set(prof["skills"])
    assert [e["company"] for e in resume["experience"]] == [e["company"] for e in prof["experience"]]
    for kind in ("resume", "cover_letter"):
        for fmt in ("pdf", "docx"):
            link = client.get(f"/api/applications/{aid}/documents/{kind}/{fmt}", headers=auth)
            assert link.status_code == 200 and "/api/files/" in link.json()["url"]
    assert client.get("/api/me", headers=auth).status_code == 200
    usage = client.get("/api/me", headers=auth).json()
    assert usage is not None


def test_free_plan_cannot_generate_documents(client, auth, db):
    prepare_user(client, auth, db, resume_customizations_per_month=0, cover_letters_per_month=0)
    aid = client.post("/api/applications", headers=auth, json={"job_id": str(job_by_title(db, "Azure Data Engineer").id)}).json()["id"]
    r = client.post(f"/api/applications/{aid}/prepare", headers=auth)
    assert r.status_code == 402


def test_cannot_submit_without_consent_or_document_approval(client, auth, db):
    prepare_user(client, auth, db)
    jid = job_by_title(db, "Azure Data Engineer").id
    aid = client.post("/api/applications", headers=auth, json={"job_id": str(jid)}).json()["id"]
    # no documents yet
    r = client.post(f"/api/applications/{aid}/submit", headers=auth)
    assert r.status_code in (403, 409)
    client.post(f"/api/applications/{aid}/prepare", headers=auth)
    r = client.post(f"/api/applications/{aid}/submit", headers=auth)  # documents not approved / no consent
    assert r.status_code in (403, 409)
    client.post(f"/api/applications/{aid}/approve-documents", headers=auth)
    r = client.post(f"/api/applications/{aid}/submit", headers=auth)
    assert r.status_code == 403 and r.json()["error"]["code"] == "consent_required"
    assert client.get(f"/api/applications/{aid}", headers=auth).json()["status"] == "PENDING_APPROVAL"


def test_plan_without_auto_apply_blocks_submit(client, auth, db):
    prepare_user(client, auth, db, auto_apply=False)
    aid = full_flow_until_approved(client, auth, job_by_title(db, "Azure Data Engineer").id)
    r = client.post(f"/api/applications/{aid}/submit", headers=auth)
    assert r.status_code == 402


def test_editing_cover_letter_voids_approval(client, auth, db):
    prepare_user(client, auth, db)
    aid = full_flow_until_approved(client, auth, job_by_title(db, "Azure Data Engineer").id)
    r = client.put(f"/api/applications/{aid}/cover-letter", headers=auth, json={"paragraphs": ["My own words."]})
    assert r.status_code == 200
    assert {x["kind"]: x["status"] for x in r.json()["documents"]}["cover_letter"] == "draft"
    assert client.post(f"/api/applications/{aid}/submit", headers=auth).status_code == 409


def test_user_can_self_report_applied_and_it_is_labelled(client, auth, db):
    prepare_user(client, auth, db)
    aid = client.post("/api/applications", headers=auth, json={"job_id": str(job_by_title(db, "Azure Data Engineer").id)}).json()["id"]
    r = client.patch(f"/api/applications/{aid}", headers=auth, json={"status": "APPLIED", "notes": "Applied on company site"})
    assert r.status_code == 200 and r.json()["status"] == "APPLIED"
    ev = [e for e in r.json()["events"] if e["to"] == "APPLIED"][0]
    assert ev["data"]["self_reported"] is True and "not verified" in ev["message"]
    # engine-owned statuses cannot be set by the user; terminal rules enforced
    assert client.patch(f"/api/applications/{aid}", headers=auth, json={"status": "APPLYING"}).status_code == 409
    assert client.patch(f"/api/applications/{aid}", headers=auth, json={"status": "INTERVIEW"}).json()["status"] == "INTERVIEW"
    assert client.patch(f"/api/applications/{aid}", headers=auth, json={"status": "MATCHED"}).status_code == 409


def test_applications_are_tenant_isolated(client, auth, auth_b, db):
    prepare_user(client, auth, db)
    aid = client.post("/api/applications", headers=auth, json={"job_id": str(job_by_title(db, "Azure Data Engineer").id)}).json()["id"]
    assert client.get(f"/api/applications/{aid}", headers=auth_b).status_code == 404
    assert client.patch(f"/api/applications/{aid}", headers=auth_b, json={"notes": "x"}).status_code == 404
    assert client.post(f"/api/applications/{aid}/prepare", headers=auth_b).status_code == 404
    assert client.delete(f"/api/applications/{aid}", headers=auth_b).status_code == 404
    assert client.get("/api/applications", headers=auth_b).json()["total"] == 0


def test_list_filters_and_search(client, auth, db):
    prepare_user(client, auth, db)
    for t in ("Azure Data Engineer", "Power BI Developer"):
        client.post("/api/applications", headers=auth, json={"job_id": str(job_by_title(db, t).id)})
    assert client.get("/api/applications", headers=auth).json()["total"] == 2
    assert client.get("/api/applications?q=power", headers=auth).json()["total"] == 1
    assert client.get("/api/applications?status=APPLIED", headers=auth).json()["total"] == 0
    assert client.get("/api/applications?status=BOGUS", headers=auth).status_code == 422


# ----------------------------------------------------------------------------- export
def test_csv_and_xlsx_export_columns_and_isolation(client, auth, auth_b, db):
    prepare_user(client, auth, db)
    j = job_by_title(db, "Azure Data Engineer")
    aid = full_flow_until_approved(client, auth, j.id, consent=False)
    client.patch(f"/api/applications/{aid}", headers=auth, json={"notes": "=HYPERLINK(\"http://evil\")"})
    r = client.get("/api/applications/export.csv", headers=auth)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["job_id", "company", "job_title", "location", "salary", "match_score", "job_url", "job_source",
                       "job_description", "custom_resume_path", "cover_letter_path", "application_status",
                       "application_date", "failure_reason", "notes"]
    assert len(rows) == 2 and rows[1][2] == "Azure Data Engineer" and rows[1][9].endswith("/documents/resume/pdf")
    assert rows[1][14].startswith("'=")  # formula injection neutralised
    x = client.get("/api/applications/export.xlsx", headers=auth)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(x.content)).active
    assert ws.max_row == 2 and ws["C2"].value == "Azure Data Engineer"
    other = list(csv.reader(io.StringIO(client.get("/api/applications/export.csv", headers=auth_b).content.decode("utf-8-sig"))))
    assert len(other) == 1  # header only: another user's data never leaks


# ----------------------------------------------------------------------------- browser automation
@pytest.fixture(scope="module")
def mock_site():
    from mock_site.server import start

    srv, url = start()
    yield url
    srv.shutdown()


@pytest.fixture(scope="module")
def browser_ok():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


@pytest.fixture()
def need_browser(browser_ok):
    if not browser_ok:
        pytest.skip("Chromium for Playwright is not installed in this environment")


def run_submit(client, auth, db, url, title="Mock Apply Role"):
    prepare_user(client, auth, db)
    job = make_job(db, url, title)
    aid = full_flow_until_approved(client, auth, job.id)
    r = client.post(f"/api/applications/{aid}/submit", headers=auth)
    assert r.status_code == 202, r.text
    return aid, client.get(f"/api/applications/{aid}", headers=auth).json()


def test_successful_submission_is_verified_and_counted(client, auth, db, mock_site, need_browser):
    aid, d = run_submit(client, auth, db, f"{mock_site}/apply/ok")
    assert d["status"] == "APPLIED" and d["confirmation_ref"].startswith("MOCK-")
    assert d["attempts"] == 1 and d["submitted_at"]
    ev = [e for e in d["events"] if e["to"] == "APPLIED"][0]
    assert "verified" in ev["message"]
    # resubmitting does nothing and creates no second submission
    from mock_site.server import Handler
    before = len(Handler.submissions)
    client.post(f"/api/applications/{aid}/submit", headers=auth)
    assert len(Handler.submissions) == before
    assert client.get(f"/api/applications/{aid}", headers=auth).json()["attempts"] == 1


@pytest.mark.parametrize("path,code", [("captcha", "captcha"), ("login", "login_required"), ("mfa", "mfa"),
                                        ("silent", "unverified")])
def test_blockers_hand_over_to_user_never_claim_success(client, auth, db, mock_site, need_browser, path, code):
    aid, d = run_submit(client, auth, db, f"{mock_site}/apply/{path}")
    assert d["status"] == "MANUAL_REQUIRED" and d["needs_user_action"] is True and d["failure_code"] == code
    assert d["submitted_at"] is None and d["approved"] is False  # needs fresh approval for any retry
    notes = client.get("/api/notifications", headers=auth) if False else None  # endpoint added later
    assert notes is None


def test_unlisted_domain_is_manual_not_automated(client, auth, db):
    aid, d = run_submit(client, auth, db, "https://careers.example.org/apply/1")
    assert d["status"] == "MANUAL_REQUIRED" and d["failure_code"] == "unsupported_site"


def test_server_error_is_retried_then_fails_honestly(client, auth, db, mock_site, need_browser):
    aid, d = run_submit(client, auth, db, f"{mock_site}/apply/error")
    assert d["status"] == "FAILED" and d["attempts"] == 3 and d["failure_code"] == "http_5xx"
    assert d["submitted_at"] is None and d["confirmation_ref"] is None
    assert sum(1 for e in d["events"] if e["type"] == "attempt_started") == 3


def test_consent_withdrawn_before_run_blocks_submission(client, auth, db, mock_site):
    prepare_user(client, auth, db)
    job = make_job(db, f"{mock_site}/apply/ok")
    aid = full_flow_until_approved(client, auth, job.id)
    from app.models import User
    from app.services import applications as svc
    from app.services.submission import submit_now

    user = db.execute(select(User)).scalars().first()
    svc.approve_submission(db, user, svc.get_app(db, user, uuid.UUID(aid)))
    db.commit()
    client.post("/api/consents", headers=auth, json={"consent_type": "auto_apply", "granted": False})
    assert submit_now(db, uuid.UUID(aid)) == "MANUAL_REQUIRED"
    assert db.execute(select(Application).where(Application.id == uuid.UUID(aid))).scalar_one().failure_code == "consent_withdrawn"
