"""Explainable job matching.

Scores are computed by a transparent weighted algorithm (weights are admin-configurable), not by asking an
LLM for a number. This keeps results reproducible, testable and resistant to prompt injection in job text.
Related (but different) skills earn partial credit yet are still reported as MISSING, so the candidate is
never credited with skills they do not have.
"""

import re
from dataclasses import dataclass, field

from app.services.taxonomy import canonical, canonical_key

SCORING_VERSION = "v1"

# Families of broadly interchangeable technologies: partial credit only.
RELATED_FAMILIES = [
    {"snowflake", "bigquery", "amazon redshift", "azure synapse", "databricks"},
    {"aws", "azure", "gcp"},
    {"tableau", "power bi", "looker"},
    {"apache airflow", "azure data factory", "aws glue", "dbt"},
    {"jenkins", "github actions", "gitlab ci", "azure devops"},
    {"postgresql", "mysql", "sql server", "oracle"},
    {"apache spark", "pyspark", "databricks"},
    {"pytorch", "tensorflow"},
    {"react", "angular", "vue.js", "next.js"},
    {"terraform", "ansible", "infrastructure as code"},
]
RELATED_CREDIT = 0.4

STOPWORDS = set(
    "the and for with that this will have from your you our are was were their they them into over about using "
    "work working team teams role roles strong good great ability able including such other more most also across "
    "years year experience required requirements preferred responsibilities skills knowledge candidate company".split()
)

LEVELS = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4, "principal": 5, "manager": 4}
EDU_LEVELS = {"none": 0, "bachelor": 1, "master": 2, "phd": 3}


@dataclass
class CandidateView:
    skills: list[str]
    years: float | None
    country: str | None
    city: str | None
    degrees: list[str]
    certifications: list[str]
    text: str  # summary + headline + bullets, used for responsibility overlap
    latest_title: str | None


@dataclass
class PrefsView:
    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    work_modes: list[str] = field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "INR"
    needs_visa: bool = False
    open_to_relocation: bool = False
    min_match_score: int = 70


@dataclass
class JobView:
    title: str
    description: str
    required_skills: list[str]
    preferred_skills: list[str]
    responsibilities: list[str]
    min_years: int | None
    max_years: int | None
    seniority: str | None
    education_required: str | None
    certifications: list[str]
    visa_sponsorship: bool | None
    work_mode: str | None
    country: str | None
    city: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: str | None


def candidate_view(profile: dict) -> CandidateView:
    exp = profile.get("experience", [])
    bullets = [b for e in exp for b in e.get("bullets", [])]
    latest = exp[0]["title"] if exp else None
    return CandidateView(
        skills=profile.get("skills", []),
        years=profile.get("total_experience_years"),
        country=profile.get("country"),
        city=(profile.get("location") or "").split(",")[0].strip() or None,
        degrees=[" ".join(x for x in (e.get("degree"), e.get("field")) if x) for e in profile.get("education", [])],
        certifications=[c.get("name", "") for c in profile.get("certifications", [])],
        text=" ".join([profile.get("summary") or "", profile.get("headline") or ""] + bullets),
        latest_title=latest,
    )


def job_view(job) -> JobView:
    a = job.analysis or {}
    return JobView(
        title=job.title,
        description=job.description,
        required_skills=a.get("required_skills") or list(job.skills or []),
        preferred_skills=a.get("preferred_skills") or [],
        responsibilities=a.get("responsibilities") or [],
        min_years=job.experience_min if job.experience_min is not None else a.get("min_years_experience"),
        max_years=job.experience_max if job.experience_max is not None else a.get("max_years_experience"),
        seniority=a.get("seniority"),
        education_required=a.get("education_required"),
        certifications=a.get("certifications_mentioned") or [],
        visa_sponsorship=job.visa_sponsorship if job.visa_sponsorship is not None else a.get("visa_sponsorship"),
        work_mode=job.work_mode,
        country=job.country,
        city=job.city,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
    )


def prefs_view(prefs) -> PrefsView:
    if prefs is None:
        return PrefsView()
    return PrefsView(
        countries=list(prefs.countries or []), cities=list(prefs.cities or []), work_modes=list(prefs.work_modes or []),
        salary_min=prefs.salary_min, salary_max=prefs.salary_max, salary_currency=prefs.salary_currency or "INR",
        needs_visa=bool(prefs.needs_visa_sponsorship), open_to_relocation=bool(prefs.open_to_relocation),
        min_match_score=prefs.min_match_score,
    )


# --------------------------------------------------------------------------- components
def _skill_coverage(cand_skills: list[str], wanted: list[str]) -> tuple[float, list[str], list[str], list[str]]:
    have = {canonical_key(s) for s in cand_skills}
    matched, missing, related = [], [], []
    credit = 0.0
    for s in wanted:
        k = canonical_key(s)
        if k in have:
            matched.append(canonical(s))
            credit += 1.0
            continue
        fam = next((f for f in RELATED_FAMILIES if k in f and (f & have)), None)
        missing.append(canonical(s))
        if fam:
            credit += RELATED_CREDIT
            related.append(f"{canonical(s)} (related: {', '.join(sorted(canonical(x) for x in fam & have))})")
    return (credit / len(wanted) if wanted else 0.0), matched, missing, related


def _experience(cand_years: float | None, job: JobView) -> tuple[float, dict]:
    info = {"candidate_years": cand_years, "required_min": job.min_years, "required_max": job.max_years}
    if cand_years is None:
        return 0.5, {**info, "status": "unknown_candidate_experience"}
    if job.min_years is None:
        return 0.7, {**info, "status": "not_specified"}
    if cand_years >= job.min_years:
        if job.max_years is not None and cand_years > job.max_years + 3:
            return 0.8, {**info, "status": "overqualified"}
        return 1.0, {**info, "status": "meets"}
    ratio = max(cand_years, 0) / job.min_years
    return round(ratio**2, 3), {**info, "status": "below_minimum", "gap_years": round(job.min_years - cand_years, 1)}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z][a-z+#.]{3,}", text.lower()) if t not in STOPWORDS}


def _responsibilities(cand_text: str, job: JobView) -> float:
    basis = " ".join(job.responsibilities) if job.responsibilities else job.description[:1500]
    j = _tokens(basis)
    if not j:
        return 0.5
    coverage = len(j & _tokens(cand_text)) / len(j)
    return min(1.0, coverage / 0.45)


def _edu_level(degrees: list[str]) -> int | None:
    best = None
    for d in degrees:
        low = d.lower()
        if re.search(r"ph\.?d|doctor", low):
            lvl = 3
        elif re.search(r"master|m\.?\s?tech|m\.?\s?sc|mba|mca|\bm\.?e\b", low):
            lvl = 2
        elif re.search(r"bachelor|b\.?\s?tech|b\.?\s?sc|bca|\bb\.?e\b|b\.?\s?com|\bba\b", low):
            lvl = 1
        else:
            continue
        best = lvl if best is None else max(best, lvl)
    return best


def _education(degrees: list[str], req: str | None) -> tuple[float, dict]:
    cand = _edu_level(degrees)
    need = EDU_LEVELS.get(req or "none", 0)
    info = {"required": req, "candidate_level": cand}
    if need == 0:
        return 0.9, {**info, "status": "not_required"}
    if cand is None:
        return 0.5, {**info, "status": "unknown_candidate_education"}
    if cand >= need:
        return 1.0, {**info, "status": "meets"}
    return (0.5 if cand == need - 1 else 0.2), {**info, "status": "below"}


def _certs(cand_certs: list[str], wanted: list[str]) -> tuple[float, dict]:
    if not wanted:
        return 0.6, {"mentioned": [], "matched": [], "status": "none_mentioned"}
    blob = " ".join(cand_certs).lower()
    matched = [c for c in wanted if c.lower() in blob]
    return len(matched) / len(wanted), {"mentioned": wanted, "matched": matched, "status": "matched" if matched else "missing"}


def _location(cand: CandidateView, prefs: PrefsView, job: JobView) -> tuple[float, dict, bool]:
    remote = job.work_mode == "remote"
    mode_ok = not prefs.work_modes or job.work_mode is None or job.work_mode in prefs.work_modes
    country_ok = not prefs.countries or job.country in prefs.countries or (remote and job.country is None)
    cities = {c.lower() for c in prefs.cities}
    city_ok = not cities or remote or (job.city or "").lower() in cities
    score = 1.0
    hard = False
    if not country_ok:
        score = 0.7 if prefs.open_to_relocation else 0.15
        hard = not prefs.open_to_relocation
    elif not city_ok:
        score *= 0.85 if prefs.open_to_relocation else 0.7
    if not mode_ok:
        score *= 0.5
    status = "match" if score >= 0.95 else "partial" if score >= 0.5 else "mismatch"
    return score, {"job_location": job.city or job.country, "work_mode": job.work_mode, "country_ok": country_ok,
                   "mode_ok": mode_ok, "city_ok": city_ok, "status": status}, hard


_PERIOD = {"year": 1, "month": 12, "hour": 2080, None: 1}


def _salary(prefs: PrefsView, job: JobView) -> tuple[float, dict]:
    jmin, jmax = job.salary_min, job.salary_max
    info = {"job_min": jmin, "job_max": jmax, "currency": job.salary_currency, "preferred_min": prefs.salary_min}
    if (jmin is None and jmax is None) or prefs.salary_min is None:
        return 0.6, {**info, "status": "unknown"}
    if job.salary_currency and job.salary_currency != prefs.salary_currency:
        return 0.6, {**info, "status": "currency_differs"}
    mult = _PERIOD.get(job.salary_period, 1)
    top = (jmax if jmax is not None else jmin) * mult
    if top >= prefs.salary_min:
        return 1.0, {**info, "status": "meets"}
    ratio = top / prefs.salary_min
    return (0.7 if ratio >= 0.9 else round(ratio * 0.7, 3)), {**info, "status": "below_expectation"}


def _candidate_level(cand: CandidateView) -> int:
    y = cand.years or 0
    lvl = 1 if y < 2 else 2 if y < 5 else 3 if y < 9 else 4
    t = (cand.latest_title or "").lower()
    if re.search(r"principal|architect|head of|director", t):
        lvl = max(lvl, 4)
    elif re.search(r"lead|manager", t):
        lvl = max(lvl, 4)
    elif re.search(r"senior|sr\.?", t):
        lvl = max(lvl, 3)
    return lvl


def _seniority(cand: CandidateView, job: JobView) -> tuple[float, dict]:
    if not job.seniority or job.seniority not in LEVELS:
        return 0.7, {"job_level": job.seniority, "status": "unknown"}
    cl, jl = _candidate_level(cand), LEVELS[job.seniority]
    diff = cl - jl
    score = {0: 1.0, 1: 0.85, -1: 0.55}.get(diff, 0.5 if diff >= 2 else 0.2)
    return score, {"job_level": job.seniority, "candidate_level": cl, "status": "aligned" if diff == 0 else "stretch" if diff < 0 else "over"}


def _visa(prefs: PrefsView, job: JobView) -> tuple[float, dict, bool]:
    if not prefs.needs_visa:
        return 1.0, {"needed": False, "status": "not_needed"}, False
    if job.visa_sponsorship is True:
        return 1.0, {"needed": True, "status": "sponsorship_offered"}, False
    if job.visa_sponsorship is False:
        return 0.0, {"needed": True, "status": "sponsorship_refused"}, True
    return 0.5, {"needed": True, "status": "unknown"}, False


# --------------------------------------------------------------------------- orchestration
def recommendation_for(score: int) -> str:
    return "strong_apply" if score >= 85 else "apply" if score >= 70 else "consider" if score >= 55 else "skip"


def score_job(cand: CandidateView, prefs: PrefsView, job: JobView, weights: dict[str, float]) -> dict:
    req_cov, req_matched, req_missing, req_related = _skill_coverage(cand.skills, job.required_skills)
    pref_cov, pref_matched, pref_missing, pref_related = _skill_coverage(cand.skills, job.preferred_skills)
    if not job.required_skills:
        req_cov = 0.5  # nothing extractable: neutral rather than rewarding or punishing
    if not job.preferred_skills:
        pref_cov = 0.5
    exp_score, exp_info = _experience(cand.years, job)
    resp = _responsibilities(cand.text, job)
    edu_score, edu_info = _education(cand.degrees, job.education_required)
    cert_score, cert_info = _certs(cand.certifications, job.certifications)
    loc_score, loc_info, loc_hard = _location(cand, prefs, job)
    sal_score, sal_info = _salary(prefs, job)
    sen_score, sen_info = _seniority(cand, job)
    visa_score, visa_info, visa_hard = _visa(prefs, job)

    components = {
        "required_skills": req_cov, "preferred_skills": pref_cov, "experience": exp_score, "responsibilities": resp,
        "education": edu_score, "certifications": cert_score, "location": loc_score, "salary": sal_score,
        "seniority": sen_score, "visa": visa_score,
    }
    total_w = sum(weights.get(k, 0) for k in components) or 1.0
    raw = sum(weights.get(k, 0) * v for k, v in components.items()) / total_w
    score = round(raw * 100)

    caps = []
    if visa_hard:
        score, caps = min(score, 25), caps + ["Employer does not offer visa sponsorship"]
    if loc_hard:
        score, caps = min(score, 40), caps + ["Job is outside your preferred countries"]
    if job.required_skills and req_cov < 0.34:
        score, caps = min(score, 55), caps + ["Most required skills are missing"]
    score = max(0, min(100, score))

    matched_all = req_matched + [s for s in pref_matched if s not in req_matched]
    explanation = _template_explanation(score, req_matched, req_missing, req_related, exp_info, loc_info, caps)
    return {
        "score": score,
        "scoring_version": SCORING_VERSION,
        "skills_matched": matched_all,
        "required_skills_matched": req_matched,
        "missing_skills": req_missing,
        "missing_preferred_skills": pref_missing,
        "related_skills": req_related + pref_related,
        "experience_match": exp_info,
        "education_match": edu_info,
        "certification_match": cert_info,
        "location_match": loc_info,
        "salary_match": sal_info,
        "seniority_match": sen_info,
        "visa_match": visa_info,
        "components": {k: round(v, 3) for k, v in components.items()},
        "weights": weights,
        "caps_applied": caps,
        "explanation": explanation,
        "recommendation": recommendation_for(score),
    }


def _template_explanation(score, matched, missing, related, exp, loc, caps) -> str:
    parts = [f"Overall match {score}%."]
    if matched:
        parts.append(f"Matches {len(matched)} required skill(s): {', '.join(matched[:6])}.")
    if missing:
        parts.append(f"Missing required skill(s): {', '.join(missing[:6])}.")
    if related:
        parts.append(f"Related experience only (not counted as a match): {'; '.join(related[:3])}.")
    status = exp.get("status")
    if status == "below_minimum":
        parts.append(f"About {exp.get('gap_years')} year(s) less experience than the stated minimum.")
    elif status == "meets":
        parts.append("Experience meets the stated requirement.")
    if loc.get("status") == "mismatch":
        parts.append("Location or work mode does not fit your preferences.")
    parts += [c + "." for c in caps]
    return " ".join(parts)


# --------------------------------------------------------------------------- persistence / orchestration
from dataclasses import dataclass as _dc  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.models import Job, JobMatch, User  # noqa: E402
from app.models.base import utcnow  # noqa: E402
from app.services import profiles, quotas  # noqa: E402
from app.services.settings_store import matching_weights  # noqa: E402


@_dc
class MatchRunStats:
    evaluated: int = 0
    saved: int = 0
    below_threshold: int = 0
    quota_blocked: int = 0
    already_matched: int = 0


class ProfileMissing(AppError):
    status_code = 409
    code = "profile_not_ready"


def match_user_now(db: Session, user: User) -> MatchRunStats:
    """Score all active jobs not yet matched for this user; persist those at/above their threshold,
    best first, until the monthly matched-jobs quota is used up. Never invents profile data."""
    stats = MatchRunStats()
    profile = profiles.get_profile(db, user.id)
    if profile is None or profile.verified_at is None:
        raise ProfileMissing("Confirm your resume/profile before running job matching.")
    prefs_row = profiles.get_preferences(db, user.id)
    cand, prefs = candidate_view(profiles.profile_to_dict(profile)), prefs_view(prefs_row)
    weights = matching_weights(db)

    existing = set(db.execute(select(JobMatch.job_id).where(JobMatch.user_id == user.id)).scalars())
    jobs = db.execute(select(Job).where(Job.status == "active")).scalars().all()
    scored: list[tuple[int, Job, dict]] = []
    for job in jobs:
        if job.id in existing:
            stats.already_matched += 1
            continue
        res = score_job(cand, prefs, job_view(job), weights)
        stats.evaluated += 1
        if res["score"] < prefs.min_match_score:
            stats.below_threshold += 1
            continue
        scored.append((res["score"], job, res))
    scored.sort(key=lambda t: -t[0])
    room = quotas.remaining(db, user, "matched_jobs_per_month")
    for score, job, res in scored:
        if stats.saved >= room:
            stats.quota_blocked += 1
            continue
        db.add(JobMatch(user_id=user.id, job_id=job.id, score=score, details=res, scoring_version=SCORING_VERSION))
        stats.saved += 1
    if stats.saved:
        quotas.increment_usage(db, user.id, "matched_jobs", stats.saved)
    if prefs_row is not None:
        prefs_row.last_match_run_at = utcnow()
    db.flush()
    return stats
