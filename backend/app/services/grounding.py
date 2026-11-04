"""Grounding validation: AI output may only restate facts that exist in the verified candidate profile.

This is the main defence against fabricated experience, skills, certifications and metrics. It does not
trust the model: every rewritten bullet / summary / cover-letter paragraph is checked in code, and anything
that fails is replaced by the original text and recorded in the change log.
"""

import re
from dataclasses import dataclass, field

from app.schemas.ai import LLMCoverLetter, LLMTailoredResume
from app.services.heuristics import detect_injection
from app.services.taxonomy import canonical_key, extract_skills

DEFAULT_SECTION_ORDER = ["summary", "skills", "experience", "projects", "education", "certifications"]
_NUM_RE = re.compile(r"\d[\d,.]*%?")


def numbers_in(text: str) -> set[str]:
    return {n.strip(".,") for n in _NUM_RE.findall(text or "")}


def _profile_text(profile: dict) -> str:
    chunks = [profile.get("summary") or "", profile.get("headline") or ""]
    for e in profile.get("experience", []):
        chunks += [e.get("title", ""), e.get("company", ""), e.get("start_date") or "", e.get("end_date") or ""] + e.get("bullets", [])
    for p in profile.get("projects", []):
        chunks += [p.get("name", ""), p.get("description") or ""]
    for c in profile.get("certifications", []):
        chunks.append(c.get("name", ""))
    for ed in profile.get("education", []):
        chunks += [ed.get("institution", ""), ed.get("degree") or "", ed.get("start_date") or "", ed.get("end_date") or ""]
    return "\n".join(chunks)


def allowed_numbers(profile: dict) -> set[str]:
    nums = numbers_in(_profile_text(profile))
    years = profile.get("total_experience_years")
    if years is not None:
        nums |= {f"{years:g}", str(int(years))}
    return nums


def profile_skill_keys(profile: dict) -> set[str]:
    keys = {canonical_key(s) for s in profile.get("skills", [])}
    keys |= {canonical_key(s) for s in extract_skills(_profile_text(profile))}
    return keys


@dataclass
class GroundingResult:
    content: dict
    change_log: list[dict] = field(default_factory=list)
    rejected: int = 0

    @property
    def passed(self) -> bool:
        return self.rejected == 0


def text_problems(text: str, *, allowed_nums: set[str], allowed_skills: set[str]) -> list[str]:
    """Return reasons why `text` introduces facts that are not in the allowed sets."""
    problems = []
    new_nums = numbers_in(text) - allowed_nums
    if new_nums:
        problems.append(f"introduces numbers not in the profile: {sorted(new_nums)}")
    new_skills = {canonical_key(s) for s in extract_skills(text)} - allowed_skills
    if new_skills:
        problems.append(f"mentions skills not supported by the profile: {sorted(new_skills)}")
    if detect_injection(text):
        problems.append("contains instruction-like text")
    return problems


def validate_tailored_resume(profile: dict, tailored: LLMTailoredResume) -> GroundingResult:
    log: list[dict] = []
    rejected = 0
    nums = allowed_numbers(profile)
    skill_keys = profile_skill_keys(profile)

    # --- skills: only skills the candidate actually has
    by_key = {canonical_key(s): s for s in profile.get("skills", [])}
    ordered: list[str] = []
    for s in tailored.prioritized_skills:
        k = canonical_key(s)
        if k in by_key and by_key[k] not in ordered:
            ordered.append(by_key[k])
        elif k not in by_key:
            rejected += 1
            log.append({"section": "skills", "kind": "rejected", "after": s, "reason": "skill not in verified profile"})
    ordered += [s for s in profile.get("skills", []) if s not in ordered]
    if ordered != profile.get("skills", []):
        log.append({"section": "skills", "kind": "reordered", "reason": "relevant skills moved first"})

    # --- summary
    summary = (tailored.summary or "").strip()
    probs = text_problems(summary, allowed_nums=nums, allowed_skills=skill_keys) if summary else ["empty"]
    if len(summary) > 700:
        probs.append("too long")
    if probs:
        rejected += 1
        fallback = (profile.get("summary") or profile.get("headline") or "").strip()
        log.append({"section": "summary", "kind": "rejected", "after": summary[:200], "reason": "; ".join(probs)})
        summary = fallback
    elif summary != (profile.get("summary") or "").strip():
        log.append({"section": "summary", "kind": "rewritten", "before": profile.get("summary"), "after": summary})

    # --- experience: identity/dates always come from the profile, never from the model
    tailored_by_id = {e.experience_id: e for e in tailored.experience}
    experience = []
    for exp in profile.get("experience", []):
        originals: list[str] = exp.get("bullets", [])
        role_text = " ".join([exp.get("title", "")] + originals)
        role_skills = {canonical_key(s) for s in extract_skills(role_text)}
        role_nums = numbers_in(role_text) | nums
        out_bullets: list[str] = []
        t = tailored_by_id.get(exp["id"])
        if t is not None:
            for tb in t.bullets:
                idx = tb.source_bullet_index
                if not (0 <= idx < len(originals)):
                    rejected += 1
                    log.append({"section": f"experience:{exp['company']}", "kind": "rejected", "after": tb.text[:200], "reason": "invalid source bullet"})
                    continue
                src = originals[idx]
                text = tb.text.strip()
                if text == src:
                    out_bullets.append(src)
                    continue
                probs = text_problems(text, allowed_nums=numbers_in(src) | (role_nums & numbers_in(src)), allowed_skills=role_skills)
                if len(text) > max(400, int(len(src) * 1.8)):
                    probs.append("rewrite is much longer than the original")
                if probs:
                    rejected += 1
                    out_bullets.append(src)
                    log.append(
                        {"section": f"experience:{exp['company']}", "kind": "rejected", "before": src, "after": text[:300], "reason": "; ".join(probs)}
                    )
                else:
                    out_bullets.append(text)
                    log.append({"section": f"experience:{exp['company']}", "kind": "rewritten", "before": src, "after": text})
        if not out_bullets:
            out_bullets = originals[:6]  # never leave a role empty because of the model
        # de-duplicate while keeping order
        seen: set[str] = set()
        out_bullets = [b for b in out_bullets if not (b in seen or seen.add(b))]
        experience.append(
            {
                "id": exp["id"],
                "company": exp["company"],
                "title": exp["title"],
                "location": exp.get("location"),
                "start_date": exp.get("start_date"),
                "end_date": exp.get("end_date"),
                "is_current": exp.get("is_current", False),
                "bullets": out_bullets,
            }
        )

    order = [s for s in tailored.section_order if s in DEFAULT_SECTION_ORDER]
    order = list(dict.fromkeys(order))
    if set(order) != set(DEFAULT_SECTION_ORDER):
        order = DEFAULT_SECTION_ORDER[:]
    elif order != DEFAULT_SECTION_ORDER:
        log.append({"section": "layout", "kind": "reordered", "after": ", ".join(order), "reason": "sections reordered for relevance"})

    content = {
        "full_name": profile.get("full_name"),
        "email": profile.get("email"),
        "phone": profile.get("phone"),
        "location": profile.get("location"),
        "links": profile.get("links", []),
        "headline": profile.get("headline"),
        "summary": summary,
        "skills": ordered,
        "experience": experience,
        "education": profile.get("education", []),
        "certifications": profile.get("certifications", []),  # copied verbatim, never generated
        "projects": profile.get("projects", []),
        "section_order": order,
    }
    return GroundingResult(content=content, change_log=log, rejected=rejected)


def validate_cover_letter(profile: dict, job_numbers: set[str], letter: LLMCoverLetter) -> tuple[dict, list[dict]]:
    """Drop any paragraph that claims skills or numbers the candidate cannot support."""
    nums = allowed_numbers(profile) | job_numbers
    skill_keys = profile_skill_keys(profile)
    log: list[dict] = []
    kept: list[str] = []
    for p in letter.paragraphs:
        text = p.strip()
        if not text:
            continue
        probs = text_problems(text, allowed_nums=nums, allowed_skills=skill_keys)
        if probs:
            log.append({"section": "cover_letter", "kind": "rejected", "after": text[:200], "reason": "; ".join(probs)})
        else:
            kept.append(text)
    return {"greeting": letter.greeting.strip()[:120], "paragraphs": kept, "closing": letter.closing.strip()[:200]}, log
