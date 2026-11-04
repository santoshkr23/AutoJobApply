"""Render tailored resumes and cover letters to ATS-friendly DOCX and PDF."""

import io
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

SECTION_TITLES = {
    "summary": "Professional Summary",
    "skills": "Technical Skills",
    "experience": "Professional Experience",
    "projects": "Projects",
    "education": "Education",
    "certifications": "Certifications",
}


def _contact_line(c: dict) -> str:
    parts = [c.get("email"), c.get("phone"), c.get("location")] + list(c.get("links") or [])[:3]
    return "  |  ".join(p for p in parts if p)


def _dates(e: dict) -> str:
    start, end = e.get("start_date"), ("Present" if e.get("is_current") else e.get("end_date"))
    return " - ".join(x for x in (start, end) if x)


def _edu_line(ed: dict) -> str:
    left = ", ".join(x for x in (ed.get("degree"), ed.get("field")) if x)
    right = " - ".join(x for x in (ed.get("start_date"), ed.get("end_date")) if x)
    return " | ".join(x for x in (left, ed.get("institution"), right) if x)


# --------------------------------------------------------------------------- resume
def render_resume_docx(c: dict) -> bytes:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    head = doc.add_paragraph()
    run = head.add_run(c.get("full_name") or "")
    run.bold = True
    run.font.size = Pt(20)
    doc.add_paragraph(_contact_line(c))
    if c.get("headline"):
        doc.add_paragraph(c["headline"]).runs[0].italic = True

    for section in c.get("section_order", []):
        if section == "summary" and c.get("summary"):
            doc.add_heading(SECTION_TITLES[section], level=2)
            doc.add_paragraph(c["summary"])
        elif section == "skills" and c.get("skills"):
            doc.add_heading(SECTION_TITLES[section], level=2)
            doc.add_paragraph(", ".join(c["skills"]))
        elif section == "experience" and c.get("experience"):
            doc.add_heading(SECTION_TITLES[section], level=2)
            for e in c["experience"]:
                p = doc.add_paragraph()
                r = p.add_run(f"{e['title']} - {e['company']}")
                r.bold = True
                meta = " | ".join(x for x in (e.get("location"), _dates(e)) if x)
                if meta:
                    p.add_run(f"\n{meta}").italic = True
                for b in e.get("bullets", []):
                    doc.add_paragraph(b, style="List Bullet")
        elif section == "projects" and c.get("projects"):
            doc.add_heading(SECTION_TITLES[section], level=2)
            for pr in c["projects"]:
                p = doc.add_paragraph()
                p.add_run(pr["name"]).bold = True
                if pr.get("description"):
                    p.add_run(f" - {pr['description']}")
        elif section == "education" and c.get("education"):
            doc.add_heading(SECTION_TITLES[section], level=2)
            for ed in c["education"]:
                doc.add_paragraph(_edu_line(ed))
        elif section == "certifications" and c.get("certifications"):
            doc.add_heading(SECTION_TITLES[section], level=2)
            for cert in c["certifications"]:
                doc.add_paragraph(" - ".join(x for x in (cert["name"], cert.get("issuer"), cert.get("date")) if x), style="List Bullet")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle("name", parent=base["Title"], fontSize=20, leading=24, alignment=0, spaceAfter=2),
        "contact": ParagraphStyle("contact", parent=base["Normal"], fontSize=9, textColor="#444444", spaceAfter=6),
        "h": ParagraphStyle("h", parent=base["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=3, textColor="#1f2937"),
        "body": ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=13.5),
        "role": ParagraphStyle("role", parent=base["Normal"], fontSize=10.5, leading=14, spaceBefore=4, fontName="Helvetica-Bold"),
        "meta": ParagraphStyle("meta", parent=base["Normal"], fontSize=9, textColor="#555555", fontName="Helvetica-Oblique"),
        "bullet": ParagraphStyle("bullet", parent=base["Normal"], fontSize=10, leading=13.5, leftIndent=12, bulletIndent=2),
    }


def render_resume_pdf(c: dict) -> bytes:
    s = _styles()
    story = [Paragraph(escape(c.get("full_name") or ""), s["name"]), Paragraph(escape(_contact_line(c)), s["contact"])]
    if c.get("headline"):
        story.append(Paragraph(f"<i>{escape(c['headline'])}</i>", s["body"]))
    for section in c.get("section_order", []):
        def heading(sec=section):
            story.extend([Paragraph(SECTION_TITLES[sec], s["h"]), HRFlowable(width="100%", thickness=0.5, color="#cccccc")])

        if section == "summary" and c.get("summary"):
            heading()
            story.append(Paragraph(escape(c["summary"]), s["body"]))
        elif section == "skills" and c.get("skills"):
            heading()
            story.append(Paragraph(escape(", ".join(c["skills"])), s["body"]))
        elif section == "experience" and c.get("experience"):
            heading()
            for e in c["experience"]:
                story.append(Paragraph(escape(f"{e['title']} - {e['company']}"), s["role"]))
                meta = " | ".join(x for x in (e.get("location"), _dates(e)) if x)
                if meta:
                    story.append(Paragraph(escape(meta), s["meta"]))
                for b in e.get("bullets", []):
                    story.append(Paragraph(escape(b), s["bullet"], bulletText="•"))
        elif section == "projects" and c.get("projects"):
            heading()
            for pr in c["projects"]:
                text = f"<b>{escape(pr['name'])}</b>" + (f" - {escape(pr['description'])}" if pr.get("description") else "")
                story.append(Paragraph(text, s["body"]))
        elif section == "education" and c.get("education"):
            heading()
            for ed in c["education"]:
                story.append(Paragraph(escape(_edu_line(ed)), s["body"]))
        elif section == "certifications" and c.get("certifications"):
            heading()
            for cert in c["certifications"]:
                line = " - ".join(x for x in (cert["name"], cert.get("issuer"), cert.get("date")) if x)
                story.append(Paragraph(escape(line), s["bullet"], bulletText="•"))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                      title=f"{c.get('full_name') or 'Resume'} - Resume", author=c.get("full_name") or "").build(story)
    return buf.getvalue()


# --------------------------------------------------------------------------- cover letter
def render_cover_letter_docx(letter: dict, sender: dict, job: dict) -> bytes:
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    p = doc.add_paragraph()
    p.add_run(sender.get("full_name") or "").bold = True
    doc.add_paragraph(_contact_line(sender))
    doc.add_paragraph(f"Re: {job.get('title', '')} - {job.get('company', '')}")
    doc.add_paragraph(letter["greeting"])
    for para in letter["paragraphs"]:
        doc.add_paragraph(para)
    doc.add_paragraph(letter["closing"])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_cover_letter_pdf(letter: dict, sender: dict, job: dict) -> bytes:
    s = _styles()
    story = [
        Paragraph(escape(sender.get("full_name") or ""), s["role"]),
        Paragraph(escape(_contact_line(sender)), s["contact"]),
        Spacer(1, 6),
        Paragraph(escape(f"Re: {job.get('title', '')} - {job.get('company', '')}"), s["body"]),
        Spacer(1, 10),
        Paragraph(escape(letter["greeting"]), s["body"]),
        Spacer(1, 6),
    ]
    for para in letter["paragraphs"]:
        story += [Paragraph(escape(para), s["body"]), Spacer(1, 8)]
    story.append(Paragraph(escape(letter["closing"]).replace("\n", "<br/>"), s["body"]))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
                      title="Cover letter", author=sender.get("full_name") or "").build(story)
    return buf.getvalue()
