import io
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FIXTURES = Path(__file__).parent / "fixtures"


def sample_text() -> str:
    return (FIXTURES / "sample_resume.txt").read_text()


def make_docx(text: str) -> bytes:
    doc = Document()
    for line in text.split("\n"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.split("\n"):
        c.drawString(40, y, line[:110])
        y -= 14
        if y < 40:
            c.showPage()
            y = 800
    c.save()
    return buf.getvalue()


def upload(client, headers, data: bytes, filename: str, content_type: str = "application/octet-stream"):
    return client.post("/api/resumes", headers=headers, files={"file": (filename, data, content_type)})
