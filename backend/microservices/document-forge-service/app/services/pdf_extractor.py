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

    Returns list of widget descriptors with name, value, type, context,
    and metadata (max_len for text, on_state for checkboxes).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    widgets = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        for w in page.widgets():
            wtype = w.field_type_string
            if wtype not in ("Text", "CheckBox", "ComboBox", "ListBox"):
                continue

            # Get contextual label: text to the left of the widget
            left_rect = fitz.Rect(0, w.rect.y0 - 2, w.rect.x0, w.rect.y1 + 2)
            left_text = page.get_text("text", clip=left_rect).strip().replace("\n", " ")

            # Sanitize widget_value — PyMuPDF may return surrogates for encoded PDF names
            raw_value = w.field_value or ""
            try:
                raw_value.encode("utf-8")
            except UnicodeEncodeError:
                raw_value = raw_value.encode("utf-8", errors="replace").decode("utf-8")

            widget_info: dict[str, Any] = {
                "widget_name": w.field_name,
                "widget_value": raw_value,
                "widget_type": wtype,
                "label": left_text[:80] if left_text else w.field_name,
                "page": page_num,
                "rect": [round(w.rect.x0), round(w.rect.y0),
                         round(w.rect.x1), round(w.rect.y1)],
            }

            if wtype == "Text":
                widget_info["max_len"] = getattr(w, "text_maxlen", 0) or 0
            elif wtype == "CheckBox":
                try:
                    on = w.on_state()
                    # on_state may contain surrogates (e.g. S#ED → \udced)
                    # Store ONLY the JSON-safe version in widget info
                    # The replacer will call w.on_state() directly at render time
                    widget_info["on_state"] = on.encode("utf-8", errors="replace").decode("utf-8")
                except Exception:
                    widget_info["on_state"] = "Yes"

            widgets.append(widget_info)

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


def widgets_to_fields(widgets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw widget list into forge-compatible fields.

    Each widget becomes a field with field_name = widget_name.
    Single-digit Cifra fields (max_len=1) on the same line are grouped
    into a composite field.

    Returns list of field dicts ready for session.fields.
    """
    fields = []
    used_widgets: set[str] = set()

    # Group single-digit fields by Y position (same line = same composite)
    digit_groups: dict[tuple[int, int], list[dict]] = {}  # (page, y) → widgets
    for w in widgets:
        if w["widget_type"] == "Text" and w.get("max_len") == 1:
            key = (w["page"], w["rect"][1])  # group by page + y position
            digit_groups.setdefault(key, []).append(w)

    # Create composite fields from digit groups (≥2 digits)
    for (page, y), group in digit_groups.items():
        if len(group) < 2:
            continue
        # Sort by x position (left to right)
        group.sort(key=lambda w: w["rect"][0])
        # Use first widget's label, composite name
        first = group[0]
        # Unique composite name using first widget name
        composite_name = first["widget_name"] + "_to_" + group[-1]["widget_name"]
        # Combine current values
        current = "".join((w["widget_value"] or " ").strip() or " " for w in group).strip()
        # Get label from the leftmost widget
        label = first.get("label", "") or composite_name

        fields.append({
            "field_name": composite_name,
            "label": label,
            "current_value": current,
            "field_type": "text",
            "required": False,
            "context_hint": f"Composite of {len(group)} digit fields: {', '.join(w['widget_name'] for w in group)}",
            "suggested_value": None,
            "widget_name": composite_name,
            "widget_names": [w["widget_name"] for w in group],  # all widget names in order
        })
        for w in group:
            used_widgets.add(w["widget_name"])

    # Add remaining widgets as individual fields
    for w in widgets:
        if w["widget_name"] in used_widgets:
            continue

        field_type = "text"
        if w["widget_type"] == "CheckBox":
            field_type = "checkbox"
        elif w.get("max_len") == 1:
            field_type = "number"

        current_value = (w["widget_value"] or "").strip()

        fields.append({
            "field_name": w["widget_name"],
            "label": w.get("label", "") or w["widget_name"],
            "current_value": current_value,
            "field_type": field_type,
            "required": False,
            "context_hint": "",
            "suggested_value": None,
            "widget_name": w["widget_name"],
        })

    return fields
