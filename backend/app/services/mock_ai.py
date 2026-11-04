"""Offline implementations of the AI tasks. Used by the labelled `mock` provider (development/tests).

They only reuse facts present in their inputs: they reorder, select and recombine the candidate's own
wording and never fabricate employers, skills, numbers or achievements.
"""

import json
import re

from app.services.taxonomy import canonical_key, extract_skills


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def mock_tailor(profile: dict, analysis: dict, job: dict) -> dict:
    job_skills = {canonical_key(s) for s in analysis.get("required_skills", []) + analysis.get("preferred_skills", [])}
    required = {canonical_key(s) for s in analysis.get("required_skills", [])}
    skills = profile.get("skills", [])
    ranked = sorted(
        skills,
        key=lambda s: (0 if canonical_key(s) in required else 1 if canonical_key(s) in job_skills else 2, skills.index(s)),
    )
    matched = [s for s in ranked if canonical_key(s) in job_skills][:6]

    years = profile.get("total_experience_years")
    headline = profile.get("headline") or job.get("title") or "Professional"
    parts = []
    if years:
        parts.append(f"{headline} with {years:g} years of professional experience.")
    else:
        parts.append(f"{headline}.")
    if matched:
        parts.append("Hands-on experience with " + ", ".join(matched) + ".")
    base_summary = _sentences(profile.get("summary") or "")
    if base_summary:
        parts.append(base_summary[0])
    summary = " ".join(parts)

    experience = []
    for exp in profile.get("experience", []):
        bullets = exp.get("bullets", [])
        scored = []
        for i, b in enumerate(bullets):
            hit = len({canonical_key(s) for s in extract_skills(b)} & job_skills)
            scored.append((-hit, i, b))
        scored.sort()
        experience.append(
            {
                "experience_id": exp["id"],
                "bullets": [{"text": b, "source_bullet_index": i} for _h, i, b in scored[:8]],
            }
        )
    top_has_skills = bool(matched)
    order = ["summary", "skills", "experience", "projects", "education", "certifications"] if top_has_skills else [
        "summary", "experience", "skills", "projects", "education", "certifications"
    ]
    return {"summary": summary, "prioritized_skills": ranked, "experience": experience, "section_order": order}


def mock_cover_letter(profile: dict, job: dict, analysis: dict) -> dict:
    required = {canonical_key(s) for s in analysis.get("required_skills", [])}
    have = [s for s in profile.get("skills", []) if canonical_key(s) in required][:5]
    name = profile.get("full_name") or "the candidate"
    company = job.get("company") or "your company"
    title = job.get("title") or "this role"
    years = profile.get("total_experience_years")

    p1 = f"I am writing to apply for the {title} position at {company}."
    if years:
        p1 += f" I bring {years:g} years of professional experience"
        p1 += f" and hands-on work with {', '.join(have)}." if have else "."

    best_bullet = None
    best_company = None
    for exp in profile.get("experience", []):
        for b in exp.get("bullets", []):
            if {canonical_key(s) for s in extract_skills(b)} & required:
                best_bullet, best_company = b, exp.get("company")
                break
        if best_bullet:
            break
    paragraphs = [p1]
    if best_bullet:
        paragraphs.append(f"In my work at {best_company}, {best_bullet[0].lower() + best_bullet[1:]}".rstrip(".") + ".")
    paragraphs.append(
        f"I would welcome the opportunity to discuss how my background can support {company}'s goals for the {title} role."
    )
    return {"greeting": "Dear Hiring Manager,", "paragraphs": paragraphs, "closing": f"Sincerely,\n{name}"}


def mock_explain(match: dict) -> dict:
    matched = match.get("skills_matched", [])
    missing = match.get("missing_skills", [])
    score = match.get("score", 0)
    text = f"Overall match {score}%. "
    text += f"Matches {len(matched)} of the job's key skills" + (f" ({', '.join(matched[:5])})." if matched else ".")
    if missing:
        text += f" Missing: {', '.join(missing[:5])}."
    return {"explanation": text, "recommendation_reason": match.get("recommendation", "consider")}


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
