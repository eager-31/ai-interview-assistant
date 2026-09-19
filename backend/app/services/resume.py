from io import BytesIO

from pypdf import PdfReader

MAX_RESUME_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
MAX_CHARS = 15_000


class ResumeError(Exception):
    """The uploaded file can't be used as a resume. The message is safe to show the user."""


def extract_resume_text(pdf_bytes: bytes) -> str:
    # Checking the file header rather than trusting the filename or content-type.
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ResumeError("The resume must be a PDF file.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ResumeError("The PDF is password-protected.")
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_PAGES]]
    except ResumeError:
        raise
    except Exception as exc:
        # pypdf raises many different types on malformed files; they all mean the same to the user.
        raise ResumeError("The PDF could not be read. It may be damaged.") from exc

    text = "\n".join(pages).strip()
    if not text:
        raise ResumeError("The PDF has no selectable text. Scanned image-only PDFs are not supported.")
    return text[:MAX_CHARS]
