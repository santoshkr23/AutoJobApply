"""Email sending with a configurable provider.

console: logs the message (development only; nothing is delivered).
smtp:    delivers through any SMTP server (SES, Sendgrid, Postmark, Mailgun, Gmail relay...).
"""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import parseaddr

from app.core.config import get_settings
from app.core.errors import ServiceNotConfigured

log = logging.getLogger(__name__)

# Messages captured by the console provider; tests read this to find verification links.
OUTBOX: list[dict] = []


def _layout(title: str, body_html: str) -> str:
    brand = get_settings().brand_name
    return (
        '<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:auto;padding:24px;color:#111">'
        f'<h2 style="margin:0 0 16px">{title}</h2>{body_html}'
        f'<hr style="border:none;border-top:1px solid #eee;margin:24px 0"/>'
        f'<p style="color:#888;font-size:12px">Sent by {brand}. If you did not expect this email you can ignore it.</p></div>'
    )


def render(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> tuple[str, str]:
    text = title + "\n\n" + "\n\n".join(paragraphs)
    html_body = "".join(f"<p>{p}</p>" for p in paragraphs)
    if button:
        label, url = button
        text += f"\n\n{label}: {url}"
        html_body += (
            f'<p><a href="{url}" style="background:#4f46e5;color:#fff;padding:10px 18px;'
            f'border-radius:8px;text-decoration:none;display:inline-block">{label}</a></p>'
            f'<p style="color:#666;font-size:13px">Or copy this link: {url}</p>'
        )
    return text, _layout(title, html_body)


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    s = get_settings()
    if s.email_provider == "console":
        if s.is_production_like:
            raise ServiceNotConfigured("EMAIL_PROVIDER=console cannot be used in staging/production")
        log.info("[email:console] to=%s subject=%s\n%s", to, subject, text)
        OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html})
        return
    if not s.smtp_host:
        raise ServiceNotConfigured("SMTP_HOST is not configured")
    msg = EmailMessage()
    msg["From"] = s.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg, from_addr=parseaddr(s.email_from)[1], to_addrs=[to])
