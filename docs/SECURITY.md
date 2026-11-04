# Security notes
- Passwords hashed (Argon2); opaque server-side sessions in HttpOnly cookies; CSRF double-submit header; rate limiting; admin identity and cookies separate from users.
- Tenant isolation: every owned object is fetched through an ownership check and returns 404 otherwise (tested).
- Sensitive fields (e.g. portal credentials) are Fernet-encrypted; signed, expiring download links; private object storage.
- Payments: frontend success is never trusted. Webhook signatures verified (Razorpay HMAC, Stripe HMAC + timestamp tolerance), events deduplicated.
- Automation: needs explicit consent + per-application approval, re-checked at execution; never bypasses CAPTCHA/MFA/login; allowlisted domains only; no fabricated success - APPLIED requires a verified confirmation or a clearly labelled user self-report.
- AI: output is validated against the profile (no invented numbers/skills); job text is treated as untrusted (prompt-injection tests).
- Not done: external penetration test, dependency audit automation, WAF, 2FA for users/admins, GDPR export tooling beyond what is in the API.
