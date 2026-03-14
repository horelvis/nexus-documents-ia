"""PDF text extraction using PyMuPDF (fitz)."""

import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes, max_chars: int = 20000) -> tuple[str, str]:
    """Extract plain text and title from PDF bytes.

    Args:
        pdf_bytes: Raw PDF file content.
        max_chars: Maximum characters to extract (LLM context budget).

    Returns:
        Tuple of (text, title).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Title: PDF metadata > first line of text
    title = ""
    try:
        title = doc.metadata.get("title", "") or ""
    except Exception:
        pass

    text_parts = []
    for page in doc:
        page_text = page.get_text("text")
        if page_text:
            text_parts.append(page_text)

    full_text = "\n".join(text_parts)

    if not title:
        # Use first non-empty line as title fallback
        for line in full_text.split("\n"):
            line = line.strip()
            if line and len(line) > 3:
                title = line[:100]
                break

    doc.close()
    return full_text[:max_chars], title or "document"
