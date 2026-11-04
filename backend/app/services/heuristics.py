"""Deterministic, offline text analysis.

Powers the labelled `mock` AI provider (development/tests) and is the fallback for job analysis when the
LLM is unavailable. It extracts facts that are literally present in the text and never invents any.
"""

import re
from datetime import UTC, datetime

from app.services.taxonomy import canonical, extract_certifications, extract_skills

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MONTH_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_TOKEN = rf"(?:{_MONTH_RE}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:-|–|—|to)\s*(?P<end>{_DATE_TOKEN}|present|current|now|till date|ongoing)", re.IGNORECASE
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{8,16}\d)(?!\d)")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s,;|]+|(?:linkedin\.com|github\.com)/[^\s,;|]+", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*(?:[•●▪■◦\-\*–·]|\d+[.)])\s+")

SECTION_SYNONYMS = {
    "summary": ["summary", "professional summary", "profile", "objective", "career objective", "about me", "about"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "technologies", "tech stack", "skills & tools"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "work history", "employment"],
    "education": ["education", "academic background", "academics", "education & training", "qualifications"],
    "certifications": ["certifications", "certificates", "licenses", "certifications & licenses", "courses"],
    "projects": ["projects", "personal projects", "key projects", "academic projects"],
}
_HEADER_LOOKUP = {s: sec for sec, syns in SECTION_SYNONYMS.items() for s in syns}


def _is_header(line: str) -> str | None:
    s = re.sub(r"[:\-–_=*#]+$", "", line.strip()).strip().lower()
    s = re.sub(r"^[#*\-_= ]+", "", s)
    if 0 < len(s) <= 40:
        return _HEADER_LOOKUP.get(s)
    return None


def parse_date(token: str | None) -> tuple[int, int] | None:
    """Return (year, month) or None. 'Present' maps to today."""
    if not token:
        return None
    t = token.strip().lower()
    if t in {"present", "current", "now", "till date", "ongoing"}:
        now = datetime.now(UTC)
        return now.year, now.month
    m = re.match(rf"({_MONTH_RE})\s+(\d{{4}})", t)
    if m:
        return int(m.group(2)), MONTHS.get(m.group(1)[:3], 1)
    m = re.match(r"(\d{1,2})/(\d{4})", t)
    if m:
        return int(m.group(2)), min(max(int(m.group(1)), 1), 12)
    m = re.match(r"(\d{4})", t)
    if m:
        return int(m.group(1)), 1
    return None


def total_experience_years(experience: list[dict]) -> float | None:
    """Total years across roles, merging overlaps so concurrent jobs are not double counted."""
    spans: list[tuple[int, int]] = []
    for e in experience:
        s = parse_date(e.get("start_date"))
        end = parse_date("present") if e.get("is_current") else parse_date(e.get("end_date"))
        if s and end:
            a, b = s[0] * 12 + s[1], end[0] * 12 + end[1]
            if b >= a:
                spans.append((a, b))
    if not spans:
        return None
    spans.sort()
    merged = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= merged[-1][1] + 1:  # overlapping or directly adjacent months
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    months = sum(b - a + 1 for a, b in merged)  # both the start and end month are worked months
    return round(months / 12, 1)


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in lines:
        sec = _is_header(line)
        if sec:
            current = sec
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _guess_name(header_lines: list[str]) -> str | None:
    for line in header_lines[:6]:
        s = line.strip()
        if not s or EMAIL_RE.search(s) or re.search(r"\d", s) or len(s) > 60:
            continue
        words = s.split()
        if 2 <= len(words) <= 4 and all(re.match(r"^[A-Za-z.'\-]+$", w) for w in words):
            return " ".join(w if w.isupper() is False else w.title() for w in words)
    return None


def _split_role_line(line: str) -> tuple[str | None, str | None, str | None]:
    """Parse '<Title> | <Company> | <Location> | dates' variants into (title, company, location)."""
    cleaned = DATE_RANGE_RE.sub("", line)
    cleaned = re.sub(r"\s*[()]\s*$", "", cleaned).strip(" |-–—,")
    parts = [p.strip() for p in re.split(r"\s*[|•]\s*|\s+[–—-]\s+|\s+at\s+|,\s{2,}", cleaned) if p.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 1:
        return parts[0], None, None
    return None, None, None


def _parse_experience(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    prev_text = ""
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        m = DATE_RANGE_RE.search(line)
        if m and not BULLET_RE.match(line):
            title, company, loc = _split_role_line(line)
            if (not title or not company) and prev_text:
                p_title, p_company, p_loc = _split_role_line(prev_text)
                title = title or p_title
                company = company or p_company or (p_title if title and p_title != title else None)
                loc = loc or p_loc
            if current:
                entries.append(current)
            end = m.group("end")
            current = {
                "company": company or "Unknown company",
                "title": title or "Unknown title",
                "location": loc,
                "start_date": m.group("start"),
                "end_date": None if end.lower() in {"present", "current", "now", "till date", "ongoing"} else end,
                "is_current": end.lower() in {"present", "current", "now", "till date", "ongoing"},
                "bullets": [],
            }
        elif current is not None:
            if BULLET_RE.match(line):
                current["bullets"].append(BULLET_RE.sub("", line).strip())
            elif current["bullets"] and not DATE_RANGE_RE.search(line) and len(line) > 40:
                current["bullets"][-1] += " " + line.strip()  # wrapped bullet text
            elif len(line) > 40 and not current["bullets"]:
                current["bullets"].append(line.strip())
        prev_text = line
    if current:
        entries.append(current)
    return entries


def _parse_education(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    degree_re = re.compile(
        r"(b\.?\s?tech|m\.?\s?tech|b\.?\s?e\b|m\.?\s?e\b|b\.?\s?sc|m\.?\s?sc|bca|mca|mba|ph\.?d|bachelor[^,|\n]*|master[^,|\n]*|diploma[^,|\n]*)",
        re.IGNORECASE,
    )
    inst_re = re.compile(r"[^,|\n]*(?:university|college|institute|school|iit|nit)[^,|\n]*", re.IGNORECASE)
    for line in lines:
        s = line.strip()
        if not s:
            continue
        inst = inst_re.search(s)
        deg = degree_re.search(s)
        dates = re.findall(r"\d{4}", s)
        if inst or deg:
            out.append(
                {
                    "institution": (inst.group(0).strip(" -–—|,") if inst else "Not specified"),
                    "degree": deg.group(0).strip() if deg else None,
                    "field": None,
                    "start_date": dates[0] if len(dates) > 1 else None,
                    "end_date": dates[-1] if dates else None,
                }
            )
    # Merge consecutive lines describing the same entry (degree line followed by institution line).
    merged: list[dict] = []
    for e in out:
        if merged and e["institution"] == "Not specified" and merged[-1]["degree"] is None:
            merged[-1]["degree"] = e["degree"]
        elif merged and e["degree"] is None and merged[-1]["institution"] == "Not specified":
            merged[-1]["institution"] = e["institution"]
        else:
            merged.append(e)
    return merged[:10]


def _parse_skill_tokens(lines: list[str]) -> list[str]:
    tokens: list[str] = []
    for line in lines:
        line = re.sub(r"^[A-Za-z /&]{2,30}:\s*", "", BULLET_RE.sub("", line))  # drop "Languages:" style labels
        for t in re.split(r"[,;|•·/]\s*|\s{2,}", line):
            t = t.strip(" .-–")
            if 1 < len(t) <= 40 and not t.endswith(":"):
                tokens.append(canonical(t))
    return tokens


def parse_resume_text(text: str) -> dict:
    lines = [ln for ln in text.replace("\r", "").split("\n")]
    sections = _split_sections(lines)
    header = sections.get("header", [])
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search("\n".join(header[:10]) or text)
    links = []
    for m in URL_RE.finditer(text):
        u = m.group(0).rstrip(".,)")
        if u not in links:
            links.append(u)
    experience = _parse_experience(sections.get("experience", []))
    skills = _parse_skill_tokens(sections.get("skills", []))
    for s in extract_skills(text):
        if s not in skills:
            skills.append(s)
    certs = [{"name": c, "issuer": None, "date": None} for c in extract_certifications(text)]
    for line in sections.get("certifications", []):
        name = BULLET_RE.sub("", line).strip()
        if len(name) > 3 and not any(name.lower() in c["name"].lower() or c["name"].lower() in name.lower() for c in certs):
            certs.append({"name": name[:200], "issuer": None, "date": None})
    projects = []
    for line in sections.get("projects", []):
        s = BULLET_RE.sub("", line).strip()
        if len(s) > 3:
            projects.append({"name": s.split(":")[0][:100], "description": s[:600], "technologies": extract_skills(s)})
    summary = " ".join(x.strip() for x in sections.get("summary", []) if x.strip()) or None
    location = None
    for line in header[:8]:
        for part in re.split(r"\s*[|•·]\s*", line):
            part = part.strip()
            if "@" in part or re.search(r"\d", part) or "/" in part or "." in part.replace(". ", " "):
                continue
            m = re.fullmatch(r"([A-Z][A-Za-z ]+,\s*[A-Z][A-Za-z ]+(?:,\s*[A-Z][A-Za-z ]+)?)", part)
            if m:
                location = m.group(1).strip()
                break
        if location:
            break
    headline = None
    if len(header) > 1:
        for line in header[1:5]:
            s = line.strip()
            if s and not EMAIL_RE.search(s) and not re.search(r"\d{5,}", s) and 3 < len(s) < 90 and s != location:
                headline = s
                break
    return {
        "full_name": _guess_name(header),
        "email": email.group(0) if email else None,
        "phone": phone.group(1).strip() if phone else None,
        "location": location,
        "headline": headline,
        "summary": summary[:3000] if summary else None,
        "skills": skills[:120],
        "experience": experience[:20],
        "education": _parse_education(sections.get("education", [])),
        "certifications": certs[:30],
        "projects": projects[:20],
        "links": links[:10],
    }


# --------------------------------------------------------------------------- job analysis
_PREFERRED_MARKERS = re.compile(r"(nice to have|preferred|bonus|good to have|a plus|desirable|optional)", re.IGNORECASE)
_RESP_MARKERS = re.compile(r"(responsibilities|what you.?ll do|duties|your role|day[- ]to[- ]day|you will)", re.IGNORECASE)


def _years(text: str) -> tuple[int | None, int | None]:
    best: tuple[int | None, int | None] = (None, None)
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*\+?\s*)?(?:years|yrs)", text, re.IGNORECASE):
        window = text[max(0, m.start() - 80): m.end() + 60].lower()
        if "experience" in window or "exp" in window:
            lo, hi = int(m.group(1)), int(m.group(2)) if m.group(2) else None
            if best[0] is None or lo < best[0]:
                best = (lo, hi)
    return best


def analyze_job_text(title: str, description: str) -> dict:
    text = f"{title}\n{description}"
    lines = description.split("\n")
    pref_idx = next((i for i, ln in enumerate(lines) if _PREFERRED_MARKERS.search(ln) and len(ln) < 80), None)
    if pref_idx is not None:
        required_text = f"{title}\n" + "\n".join(lines[:pref_idx])
        preferred_text = "\n".join(lines[pref_idx:])
    else:
        required_text, preferred_text = text, ""
    required = extract_skills(required_text)
    preferred = [s for s in extract_skills(preferred_text) if s not in required]

    resp: list[str] = []
    in_resp = False
    for ln in lines:
        if _RESP_MARKERS.search(ln) and len(ln) < 60:
            in_resp = True
            continue
        if in_resp:
            if BULLET_RE.match(ln):
                resp.append(BULLET_RE.sub("", ln).strip()[:300])
            elif ln.strip() == "" and resp:
                continue
            elif _is_header(ln) or (resp and len(ln) < 60 and ln.strip().endswith(":")):
                in_resp = False
    low = text.lower()
    tl = title.lower()
    seniority = None
    for key, pat in [
        ("intern", r"\bintern(ship)?\b"), ("junior", r"\b(junior|jr\.?|entry[- ]level|graduate)\b"),
        ("principal", r"\b(principal|staff|architect)\b"), ("lead", r"\b(lead|head)\b"),
        ("manager", r"\bmanager\b"), ("senior", r"\b(senior|sr\.?)\b"),
    ]:
        if re.search(pat, tl):
            seniority = key
            break
    lo, hi = _years(text)
    if seniority is None and lo is not None:
        seniority = "junior" if lo <= 1 else "mid" if lo <= 4 else "senior"
    education = None
    if re.search(r"\b(ph\.?d|doctorate)\b", low):
        education = "phd"
    elif re.search(r"\b(master'?s|m\.?tech|m\.?sc|mba)\b", low):
        education = "master"
    elif re.search(r"\b(bachelor'?s?|b\.?tech|b\.?e\b|b\.?sc|undergraduate degree|degree in)\b", low):
        education = "bachelor"
    visa = None
    if re.search(r"(no visa sponsorship|(?:visa )?sponsorship (?:is |are )?(?:not|n't) (?:available|provided|offered|possible)|"
                 r"not (?:able|eligible) to sponsor|unable to sponsor|cannot sponsor|can'?t sponsor|"
                 r"without (?:visa )?sponsorship|will not sponsor|does not (?:offer|provide) (?:visa )?sponsorship|"
                 r"must (?:be|already be) (?:legally )?authori[sz]ed to work|no sponsorship)", low):
        visa = False
    elif re.search(r"(visa sponsorship (?:is )?(?:available|provided|offered)|we (?:can |will )?sponsor|sponsorship (?:is )?available|relocation and visa|offer(?:s)? visa)", low):
        visa = True
    mode = None
    if re.search(r"\b(fully remote|remote[- ]first|100% remote|work from home|remote)\b", low):
        mode = "remote"
    if re.search(r"\bhybrid\b", low):
        mode = "hybrid"
    elif mode is None and re.search(r"\b(on[- ]?site|in[- ]office|in office)\b", low):
        mode = "onsite"
    return {
        "required_skills": required,
        "preferred_skills": preferred,
        "responsibilities": resp[:15],
        "min_years_experience": lo,
        "max_years_experience": hi,
        "seniority": seniority,
        "education_required": education,
        "certifications_mentioned": extract_certifications(text),
        "visa_sponsorship": visa,
        "work_mode": mode,
        "suspicious_instructions_detected": bool(detect_injection(text)),
    }


# --------------------------------------------------------------------------- prompt injection heuristics
_INJECTION_PATTERNS = [
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts?)",
    r"disregard (?:all |any )?(?:previous|prior|above)",
    r"you are now (?:a|an|in)\b",
    r"system prompt",
    r"reveal (?:your|the) (?:instructions|prompt)",
    r"(?:rate|score|rank) (?:this )?(?:candidate|resume|applicant) (?:as )?(?:10|100|highest|perfect)",
    r"(?:hire|select|recommend) this candidate",
    r"<\s*/?\s*(?:system|assistant|instructions?)\s*>",
    r"\bdo anything now\b",
]


def detect_injection(text: str) -> list[str]:
    hits = []
    low = text.lower()
    for p in _INJECTION_PATTERNS:
        if re.search(p, low):
            hits.append(p)
    return hits
