"""PDF text replacement using PyMuPDF redact & insert strategy.

Three-phase algorithm per page:
  Phase 1 — Collect: search all fields, validate matches, capture font styles
  Phase 2 — Redact: batch all redactions, apply once per page
  Phase 3 — Insert: write new text at original positions
"""

import logging
from dataclasses import dataclass

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# --- Font mapping: embedded PDF font names → Base14 identifiers ---

_FONT_MAP = {
    "arial": "helv",
    "arialmt": "helv",
    "arial,bold": "hebo",
    "arial-bold": "hebo",
    "arial-boldmt": "hebo",
    "arial,italic": "heit",
    "arial-italic": "heit",
    "helvetica": "helv",
    "helvetica-bold": "hebo",
    "helvetica-oblique": "heit",
    "helvetica-boldoblique": "hebi",
    "timesnewroman": "tiro",
    "timesnewromanpsmt": "tiro",
    "timesnewroman,bold": "tibo",
    "timesnewroman-bold": "tibo",
    "timesnewroman,italic": "tiit",
    "times-roman": "tiro",
    "times-bold": "tibo",
    "times-italic": "tiit",
    "courier": "cour",
    "couriernew": "cour",
    "courier-bold": "cobo",
    "calibri": "helv",
    "calibri-bold": "hebo",
    "calibri-italic": "heit",
    "cambria": "tiro",
    "cambria-bold": "tibo",
    "verdana": "helv",
    "tahoma": "helv",
    "garamond": "tiro",
}

# Base14 font names recognized by PyMuPDF
_BASE14_NAMES = {
    "helv", "hebo", "heit", "hebi",  # Helvetica family
    "tiro", "tibo", "tiit", "tibi",  # Times family
    "cour", "cobo", "coit", "cobi",  # Courier family
    "symb", "zadb",                   # Symbol, ZapfDingbats
}


def _normalize_font_name(font_name: str) -> str:
    """Normalize a PDF font name to a Base14 identifier.

    Strips subset prefix (e.g., 'ABCDEF+ArialMT' → 'arialmt'),
    lowercases, removes spaces. Falls back to 'helv' (Helvetica).
    """
    if not font_name:
        return "helv"

    # Strip subset prefix (6 uppercase letters + '+')
    if "+" in font_name:
        font_name = font_name.split("+", 1)[1]

    normalized = font_name.lower().replace(" ", "")

    # Already a Base14 name?
    if normalized in _BASE14_NAMES:
        return normalized

    # Try exact match in font map
    if normalized in _FONT_MAP:
        return _FONT_MAP[normalized]

    # Try prefix match (e.g., "arialmt-regular" → "arialmt")
    for key, value in _FONT_MAP.items():
        if normalized.startswith(key):
            return value

    return "helv"


@dataclass
class PendingReplacement:
    """A text replacement waiting to be applied."""

    rect: fitz.Rect
    new_value: str
    font_size: float
    font_name: str  # Base14 identifier
    color: tuple  # RGB floats (0-1 range)
    field_name: str  # for logging


class PdfReplacer:
    """Performs text replacement in PDF files via redact & insert."""

    def replace(
        self,
        pdf_bytes: bytes,
        fields: list[dict],
        field_values: dict[str, str],
    ) -> tuple[bytes, int, list[str]]:
        """Replace field values in a PDF document.

        Args:
            pdf_bytes: Original PDF file bytes.
            fields: Detected fields from analyzer (with current_value).
            field_values: Map of field_name → new_value from user.

        Returns:
            Tuple of (modified_pdf_bytes, fields_replaced, failed_fields).
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Build replacement list: (current_value, new_value, field_name)
        replacements: list[tuple[str, str, str]] = []
        for f in fields:
            name = f.get("field_name", "")
            current = f.get("current_value", "")
            if name in field_values and current:
                replacements.append((current, field_values[name], name))

        # Sort by current_value length descending (avoid partial matches)
        replacements.sort(key=lambda x: len(x[0]), reverse=True)

        # Collect pending replacements per page
        pending: dict[int, list[PendingReplacement]] = {}
        replaced_fields: set[str] = set()
        failed_fields: list[str] = []

        # Phase 1: Collect matches across all pages
        for current_value, new_value, field_name in replacements:
            found = False
            for page_num in range(len(doc)):
                page = doc[page_num]
                rects = page.search_for(current_value)
                for rect in rects:
                    # Validate: confirm the rect actually contains our text
                    clip_text = page.get_text("text", clip=rect).strip()
                    if not clip_text or current_value not in clip_text:
                        logger.debug(
                            "Skipping false match for '%s' on page %d: clip='%s'",
                            field_name, page_num, clip_text[:50],
                        )
                        continue

                    # Capture font properties
                    font_size, font_name, color = self._extract_style(page, rect)

                    if page_num not in pending:
                        pending[page_num] = []
                    pending[page_num].append(
                        PendingReplacement(
                            rect=rect,
                            new_value=new_value,
                            font_size=font_size,
                            font_name=font_name,
                            color=color,
                            field_name=field_name,
                        )
                    )
                    found = True

            if found:
                replaced_fields.add(field_name)
            else:
                failed_fields.append(field_name)
                logger.warning(
                    "Could not find text for field '%s': '%s'",
                    field_name, current_value[:50],
                )

        # Phase 2 & 3: Redact and insert per page
        for page_num, page_replacements in pending.items():
            page = doc[page_num]

            # Phase 2: Batch redactions
            for repl in page_replacements:
                page.add_redact_annot(repl.rect, text="", fill=(1, 1, 1))
            page.apply_redactions()

            # Phase 3: Insert new text
            for repl in page_replacements:
                # Baseline positioning: rect bottom minus descent estimate (~20%)
                baseline_y = repl.rect.y1 - (repl.font_size * 0.2)
                try:
                    page.insert_text(
                        point=(repl.rect.x0, baseline_y),
                        text=repl.new_value,
                        fontsize=repl.font_size,
                        fontname=repl.font_name,
                        color=repl.color,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to insert text for '%s': %s", repl.field_name, e,
                    )
                    # Try with fallback font
                    try:
                        page.insert_text(
                            point=(repl.rect.x0, baseline_y),
                            text=repl.new_value,
                            fontsize=repl.font_size,
                            fontname="helv",
                            color=repl.color,
                        )
                    except Exception as e2:
                        logger.error("Fallback insert also failed: %s", e2)

        # Save modified PDF
        result_bytes = doc.tobytes()
        doc.close()

        return result_bytes, len(replaced_fields), failed_fields

    def _extract_style(
        self, page: fitz.Page, rect: fitz.Rect
    ) -> tuple[float, str, tuple]:
        """Extract font size, name, and color from text in a rect.

        Returns:
            (font_size, base14_font_name, rgb_color_tuple)
        """
        font_size = 12.0
        font_name = "helv"
        color = (0, 0, 0)  # black

        try:
            text_dict = page.get_text("dict", clip=rect)
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_size = span.get("size", 12.0)
                        raw_font = span.get("font", "")
                        font_name = _normalize_font_name(raw_font)
                        # Color is an int in PyMuPDF — convert to RGB tuple
                        color_int = span.get("color", 0)
                        color = (
                            ((color_int >> 16) & 0xFF) / 255.0,
                            ((color_int >> 8) & 0xFF) / 255.0,
                            (color_int & 0xFF) / 255.0,
                        )
                        return font_size, font_name, color
        except Exception as e:
            logger.warning("Could not extract style from rect: %s", e)

        return font_size, font_name, color


_replacer = None


def get_pdf_replacer() -> PdfReplacer:
    global _replacer
    if _replacer is None:
        _replacer = PdfReplacer()
    return _replacer
