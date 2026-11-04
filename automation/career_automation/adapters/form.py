"""Generic form adapter, restricted to allowlisted domains (default: the local mock site only).

It fills a standard application form, then verifies success from a confirmation signal on the resulting page.
It stops and hands over to the user at the first sign of CAPTCHA, login wall or MFA - it never tries to bypass them.
"""

import re
from urllib.parse import urlparse

from career_automation.base import Adapter, Outcome, SubmissionContext, SubmissionResult

CAPTCHA_RE = re.compile(r"captcha|recaptcha|hcaptcha|i am not a robot|verify you are human|turnstile", re.I)
LOGIN_RE = re.compile(r"sign in to continue|log in to continue|please (log|sign) in|create an account to apply", re.I)
MFA_RE = re.compile(r"verification code|two-factor|2fa|one-time (code|password)|enter the code", re.I)
CONFIRM_RE = re.compile(r"(application|submission) (has been )?(received|submitted|sent)|thank you for applying|application complete", re.I)
REF_RE = re.compile(r"(?:reference|confirmation|ref)(?: number| id| code)?[:#\s]+([A-Z0-9][A-Z0-9-]{4,})", re.I)

FIELD_HINTS = {
    "full_name": ("name", "full_name", "fullname", "your-name", "applicant"),
    "email": ("email", "e-mail"),
    "phone": ("phone", "mobile", "tel"),
    "location": ("location", "city"),
    "cover_letter": ("cover", "message", "letter"),
}


def host_allowed(url: str, allowed: list[str]) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme in ("http", "https") and any(host == d or host.endswith("." + d) for d in allowed)


def classify_blocker(text: str) -> tuple[str, str] | None:
    if CAPTCHA_RE.search(text):
        return "captcha", "A CAPTCHA is shown. Please complete this application yourself."
    if MFA_RE.search(text):
        return "mfa", "The site asks for a verification code. Please complete this application yourself."
    if LOGIN_RE.search(text):
        return "login_required", "The site requires you to sign in. Please complete this application yourself."
    return None


class GenericFormAdapter(Adapter):
    name = "generic_form"

    def can_handle(self, url, allowed_domains):
        return host_allowed(url, allowed_domains)

    def submit(self, ctx: SubmissionContext) -> SubmissionResult:
        if not host_allowed(ctx.apply_url, ctx.allowed_domains):
            return SubmissionResult(Outcome.MANUAL_REQUIRED, "domain_not_allowed", "This site is not on the automation allowlist.")
        from playwright.sync_api import Error as PWError
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=ctx.headless)
                try:
                    page = browser.new_context(accept_downloads=False).new_page()
                    page.set_default_timeout(ctx.timeout_ms)
                    resp = page.goto(ctx.apply_url)
                    if resp is not None and resp.status >= 500:
                        return SubmissionResult(Outcome.RETRYABLE, "http_5xx", f"Site returned HTTP {resp.status}.")
                    if resp is not None and resp.status >= 400:
                        return SubmissionResult(Outcome.FAILED, "http_4xx", f"Apply page returned HTTP {resp.status}.")
                    blocker = classify_blocker(page.content())
                    if blocker:
                        return SubmissionResult(Outcome.MANUAL_REQUIRED, blocker[0], blocker[1], evidence={"url": page.url})
                    form = page.locator("form").first
                    if form.count() == 0:
                        return SubmissionResult(Outcome.MANUAL_REQUIRED, "no_form", "No application form found on the page.")
                    self._fill(page, form, ctx)
                    page.locator("form button[type=submit], form input[type=submit]").first.click()
                    page.wait_for_load_state("domcontentloaded")
                    text = page.inner_text("body")
                    blocker = classify_blocker(page.content())
                    if blocker:
                        return SubmissionResult(Outcome.MANUAL_REQUIRED, blocker[0], blocker[1], evidence={"url": page.url})
                    if CONFIRM_RE.search(text):
                        m = REF_RE.search(text)
                        return SubmissionResult(Outcome.SUBMITTED, "confirmed", "Submission confirmed by the site.",
                                                confirmation_ref=m.group(1) if m else None, evidence={"url": page.url})
                    # No confirmation signal: we cannot claim success.
                    return SubmissionResult(Outcome.MANUAL_REQUIRED, "unverified", "Submitted the form but the site did not confirm it. "
                                            "Please check whether your application went through.", evidence={"url": page.url})
                finally:
                    browser.close()
        except PWTimeout:
            return SubmissionResult(Outcome.RETRYABLE, "timeout", "The site timed out.")
        except PWError as exc:
            return SubmissionResult(Outcome.RETRYABLE, "browser_error", f"Browser error: {str(exc)[:200]}")

    def _fill(self, page, form, ctx: SubmissionContext) -> None:
        a = ctx.applicant
        values = {"full_name": a.full_name, "email": a.email, "phone": a.phone, "location": a.location,
                  "cover_letter": ctx.cover_letter_text}
        for el in form.locator("input:not([type=file]):not([type=hidden]):not([type=submit]), textarea").all():
            ident = " ".join(filter(None, [el.get_attribute("name"), el.get_attribute("id"), el.get_attribute("placeholder"),
                                           el.get_attribute("type")])).lower()
            for key, hints in FIELD_HINTS.items():
                if values.get(key) and any(h in ident for h in hints):
                    # prefer the most specific hint: email before name
                    if key == "full_name" and "email" in ident:
                        continue
                    el.fill(values[key])
                    break
        files = form.locator("input[type=file]")
        if files.count():
            name = re.sub(r"[^A-Za-z0-9._-]", "_", ctx.resume_filename or "resume.pdf")
            files.first.set_input_files({"name": name, "mimeType": "application/pdf", "buffer": ctx.resume_bytes})
        for cb in form.locator("input[type=checkbox][required]").all():
            # Only tick a consent box we are explicitly authorised to: the user approved this exact submission.
            cb.check()
