"""Normalize raw connector output into the common job schema; fingerprints for duplicate detection."""

import hashlib
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from app.connectors.base import RawJob

COUNTRY_NAMES = {
    "india": "IN", "united states": "US", "usa": "US", "us": "US", "united kingdom": "GB", "uk": "GB",
    "great britain": "GB", "canada": "CA", "germany": "DE", "france": "FR", "netherlands": "NL",
    "ireland": "IE", "spain": "ES", "italy": "IT", "sweden": "SE", "poland": "PL", "portugal": "PT",
    "switzerland": "CH", "australia": "AU", "singapore": "SG", "united arab emirates": "AE", "uae": "AE",
}
EU_CODES = {"DE", "FR", "NL", "IE", "ES", "IT", "SE", "PL", "PT", "BE", "AT", "DK", "FI", "NO", "CH"}
CURRENCY_BY_COUNTRY = {"IN": "INR", "US": "USD", "GB": "GBP", "CA": "CAD", "AU": "AUD", "SG": "SGD", "AE": "AED"} | {c: "EUR" for c in EU_CODES}

EMPLOYMENT_MAP = {
    "full_time": "full_time", "full-time": "full_time", "fulltime": "full_time", "permanent": "full_time",
    "part_time": "part_time", "part-time": "part_time", "contract": "contract", "contractor": "contract",
    "freelance": "contract", "internship": "internship", "intern": "internship", "temporary": "temporary",
}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "h1", "h2", "h3", "h4", "ul", "ol"):
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in ("p", "div", "li", "ul", "ol"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str, limit: int = 20_000) -> str:
    # Some APIs (Greenhouse) return HTML escaped as entities; unescape once so it can be parsed as markup.
    if "&lt;" in raw and "<" not in raw:
        raw = html.unescape(raw)
    if "<" in raw and ">" in raw:
        parser = _Text()
        parser.feed(raw)
        raw = "".join(parser.parts)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)
    return raw.strip()[:limit]


def is_safe_url(url: str | None) -> bool:
    if not url:
        return False
    p = urlparse(url)
    return p.scheme in ("http", "https") and bool(p.netloc)


def guess_country(location_text: str | None, hint: str | None = None) -> str | None:
    if hint and len(hint) == 2:
        return hint.upper()
    if not location_text:
        return None
    low = location_text.lower()
    for name, code in COUNTRY_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", low):
            return code
    return None


def guess_work_mode(job: RawJob) -> str | None:
    if job.work_mode in ("remote", "hybrid", "onsite"):
        return job.work_mode
    text = f"{job.location_text or ''} {job.title}".lower()
    if "hybrid" in text:
        return "hybrid"
    if "remote" in text or "anywhere" in text or "worldwide" in text:
        return "remote"
    return None


def guess_city(location_text: str | None) -> str | None:
    if not location_text:
        return None
    first = re.split(r"[,/|(]", location_text)[0].strip()
    if not first or first.lower() in COUNTRY_NAMES or first.lower() in {"remote", "anywhere", "worldwide", "hybrid"}:
        return None
    return first[:120]


def classify_category(title: str, categories: list[dict]) -> str | None:
    t = title.lower()
    best, best_len = None, 0
    for cat in categories:
        for kw in cat.get("keywords", []):
            if kw in t and len(kw) > best_len:
                best, best_len = cat["key"], len(kw)
    return best


def fingerprint(company: str, title: str, city: str | None, country: str | None, work_mode: str | None) -> str:
    def norm(s: str) -> str:
        s = re.sub(r"\b(sr|sr\.)\b", "senior", s.lower())
        s = re.sub(r"\b(jr|jr\.)\b", "junior", s)
        return re.sub(r"[^a-z0-9]+", " ", s).strip()

    place = norm(city or "") or ("remote" if work_mode == "remote" else (country or ""))
    return hashlib.sha256(f"{norm(company)}|{norm(title)}|{place}".encode()).hexdigest()


def normalize(raw: RawJob, categories: list[dict], default_country: str | None = None) -> dict | None:
    """Return a dict of Job columns, or None if the posting is unusable/unsafe."""
    if not (raw.title and raw.company and raw.external_id and is_safe_url(raw.url)):
        return None
    description = html_to_text(raw.description or "")
    if len(description) < 20:
        return None
    country = guess_country(raw.location_text, raw.country or default_country)
    city = guess_city(raw.location_text)
    mode = guess_work_mode(raw)
    emp = EMPLOYMENT_MAP.get((raw.employment_type or "").strip().lower().replace(" ", "_"))
    smin, smax = raw.salary_min, raw.salary_max
    if smin and smax and smin > smax:
        smin, smax = smax, smin
    currency = raw.salary_currency or (CURRENCY_BY_COUNTRY.get(country or "") if (smin or smax) else None)
    title = re.sub(r"\s+", " ", raw.title).strip()[:300]
    company = re.sub(r"\s+", " ", raw.company).strip()[:255]
    return {
        "external_id": str(raw.external_id)[:255],
        "title": title,
        "company": company,
        "description": description,
        "location_text": (raw.location_text or "")[:255] or None,
        "country": country,
        "city": city,
        "work_mode": mode,
        "salary_min": smin,
        "salary_max": smax,
        "salary_currency": currency,
        "salary_period": raw.salary_period,
        "employment_type": emp,
        "url": raw.url[:2048],
        "apply_url": raw.apply_url[:2048] if is_safe_url(raw.apply_url) else None,
        "attribution": raw.attribution,
        "posted_at": raw.posted_at,
        "expires_at": raw.expires_at,
        "category": classify_category(title, categories),
        "fingerprint": fingerprint(company, title, city, country, mode),
        "is_sample": raw.is_sample,
    }
