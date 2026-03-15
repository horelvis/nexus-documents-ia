"""PDF text extraction using PyMuPDF (fitz).

Handles both regular PDFs and AcroForm PDFs (with editable form fields).
For form PDFs, widget info is appended to the extracted text so the LLM
can detect them as fields and use the widget_name for direct filling.
"""

import logging
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes, max_chars: int = 20000) -> tuple[str, str]:
    """Extract plain text and title from PDF bytes.

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
        for line in full_text.split("\n"):
            line = line.strip()
            if line and len(line) > 3:
                title = line[:100]
                break

    doc.close()
    return full_text[:max_chars], title or "document"


def extract_widgets_from_pdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """Extract AcroForm widget info from PDF.

    Returns list of widget descriptors with name, value, type, and context.
    Empty list if no widgets found.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    widgets = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        for w in page.widgets():
            if w.field_type_string not in ("Text", "ComboBox", "ListBox"):
                continue

            # Get contextual label: text to the left of the widget
            left_rect = fitz.Rect(0, w.rect.y0 - 2, w.rect.x0, w.rect.y1 + 2)
            left_text = page.get_text("text", clip=left_rect).strip().replace("\n", " ")

            widgets.append({
                "widget_name": w.field_name,
                "widget_value": w.field_value or "",
                "widget_type": w.field_type_string,
                "label": left_text[:80] if left_text else w.field_name,
                "page": page_num,
                "rect": [round(w.rect.x0), round(w.rect.y0),
                         round(w.rect.x1), round(w.rect.y1)],
            })

    doc.close()
    return widgets


def has_form_fields(pdf_bytes: bytes) -> bool:
    """Check if PDF has AcroForm fields (editable widgets)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        if list(page.widgets()):
            doc.close()
            return True
    doc.close()
    return False
