"""Validation and text extraction for uploaded resumes. Uploaded files are untrusted input."""

import hashlib
import io
import zipfile

from docx import Document
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.errors import AppError

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_PDF_PAGES = 30
MAX_TEXT_CHARS = 60_000
MAX_DOCX_UNCOMPRESSED = 30 * 1024 * 1024


def detect_kind(filename: str, data: bytes) -> tuple[str, str]:
    """Return (extension, mime) based on content, not on the client-supplied type."""
    name = (filename or "").lower()
    if data[:5] == b"%PDF-" and name.endswith(".pdf"):
        return "pdf", PDF_MIME
    if data[:4] == b"PK\x03\x04" and name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "word/document.xml" not in names:
                    raise AppError("This does not look like a valid DOCX file.", code="invalid_file")
                if sum(i.file_size for i in z.infolist()) > MAX_DOCX_UNCOMPRESSED:
                    raise AppError("The DOCX file is too large when decompressed.", code="invalid_file")
        except zipfile.BadZipFile as exc:
            raise AppError("This does not look like a valid DOCX file.", code="invalid_file") from exc
        return "docx", DOCX_MIME
    raise AppError("Only PDF and DOCX resumes are supported.", code="unsupported_file_type")


def validate_upload(filename: str, data: bytes) -> tuple[str, str, str]:
    s = get_settings()
    if not data:
        raise AppError("The uploaded file is empty.", code="invalid_file")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise AppError(f"File is larger than {s.max_upload_mb} MB.", code="file_too_large", status_code=413)
    ext, mime = detect_kind(filename, data)
    return ext, mime, hashlib.sha256(data).hexdigest()


def extract_text(data: bytes, ext: str) -> str:
    try:
        if ext == "pdf":
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise AppError("Password-protected PDFs are not supported.", code="invalid_file")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise AppError(f"Resume has more than {MAX_PDF_PAGES} pages.", code="invalid_file")
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            text = "\n".join(parts)
    except AppError:
        raise
    except Exception as exc:  # corrupt/odd files
        raise AppError("We could not read this file. Try exporting it again as PDF or DOCX.", code="unreadable_file") from exc
    text = text.replace("\x00", "").strip()
    if len(text) < 50:
        raise AppError(
            "No readable text was found. Scanned/image-only resumes are not supported; upload a text PDF or DOCX.",
            code="no_text",
        )
    return text[:MAX_TEXT_CHARS]
