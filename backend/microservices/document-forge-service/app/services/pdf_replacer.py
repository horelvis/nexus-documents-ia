"""PDF text replacement using PyMuPDF redact & insert strategy.

Two search strategies:
  1. Direct match: search_for(current_value) — for unique text values
  2. Context-anchor: search_for(context_hint) to find the line, then locate
     the dots/placeholder on that line — for form PDFs where all fields are "..."

Three-phase algorithm per page:
  Phase 1 — Collect: search all fields, validate matches, capture font styles
  Phase 2 — Redact: batch all redactions, apply once per page
  Phase 3 — Insert: write new text at original positions
"""

import logging
import re
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

_BASE14_NAMES = {
    "helv", "hebo", "heit", "hebi",
    "tiro", "tibo", "tiit", "tibi",
    "cour", "cobo", "coit", "cobi",
    "symb", "zadb",
}

# Pattern to detect "dots-only" current_value (form placeholders)
_DOTS_PATTERN = re.compile(r"^[.\s]+$")
# Minimum dots sequence to search for in PDF
_MIN_DOTS = "...."


def _normalize_font_name(font_name: str) -> str:
    """Normalize a PDF font name to a Base14 identifier."""
    if not font_name:
        return "helv"
    if "+" in font_name:
        font_name = font_name.split("+", 1)[1]
    normalized = font_name.lower().replace(" ", "")
    if normalized in _BASE14_NAMES:
        return normalized
    if normalized in _FONT_MAP:
        return _FONT_MAP[normalized]
    for key, value in _FONT_MAP.items():
        if normalized.startswith(key):
            return value
    return "helv"


def _extract_context_anchor(context_hint: str) -> str:
    """Extract a searchable text anchor from the context_hint.

    Strips dots and takes the longest non-dots fragment (>5 chars).
    """
    if not context_hint:
        return ""
    # Split on runs of dots and take fragments
    parts = re.split(r"\.{3,}", context_hint)
    # Find longest non-trivial fragment
    best = ""
    for part in parts:
        cleaned = part.strip()
        if len(cleaned) > len(best) and len(cleaned) >= 5:
            best = cleaned
    return best


@dataclass
class PendingReplacement:
    """A text replacement waiting to be applied."""
    rect: fitz.Rect
    new_value: str
    font_size: float
    font_name: str
    color: tuple
    field_name: str


class PdfReplacer:
    """Performs text replacement in PDF files.

    Three strategies (tried in order per field):
    1. Widget fill: if field has widget_name, fill the AcroForm widget directly
    2. Direct search: search_for(current_value) for unique text values
    3. Context-anchor: use context_hint to locate dots/placeholder fields
    """

    def replace(
        self,
        pdf_bytes: bytes,
        fields: list[dict],
        field_values: dict[str, str],
    ) -> tuple[bytes, int, list[str]]:
        """Replace field values in a PDF document.

        Returns:
            Tuple of (modified_pdf_bytes, fields_replaced, failed_fields).
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Phase 0: Widget fill — direct AcroForm field filling
        widget_filled: set[str] = set()
        self._fill_widgets(doc, fields, field_values, widget_filled)

        # Build replacement list for remaining fields (non-widget)
        replacements = []
        for f in fields:
            name = f.get("field_name", "")
            current = f.get("current_value", "")
            hint = f.get("context_hint", "")
            if name in field_values and name not in widget_filled and current:
                replacements.append({
                    "field_name": name,
                    "current_value": current,
                    "new_value": field_values[name],
                    "context_hint": hint,
                    "is_dots": bool(_DOTS_PATTERN.match(current.strip())),
                })

        # Sort: non-dots first (direct match), then dots (context-anchor)
        # Within each group, sort by current_value length descending
        replacements.sort(key=lambda x: (x["is_dots"], -len(x["current_value"])))

        pending: dict[int, list[PendingReplacement]] = {}
        replaced_fields: set[str] = set()
        failed_fields: list[str] = []
        # Track which rects have been claimed to avoid double-replacement
        claimed_rects: set[tuple[int, float, float, float, float]] = set()

        for repl in replacements:
            found = False
            if repl["is_dots"]:
                found = self._find_by_context(
                    doc, repl, pending, claimed_rects,
                )
            else:
                found = self._find_by_direct_search(
                    doc, repl, pending, claimed_rects,
                )

            if found:
                replaced_fields.add(repl["field_name"])
            else:
                failed_fields.append(repl["field_name"])
                logger.warning(
                    "Could not locate field '%s' in PDF", repl["field_name"],
                )

        # Phase 2 & 3: Cover and insert per page
        # Strategy: white rectangle overlay + text insertion.
        # This is more reliable than apply_redactions() which may not
        # remove text from all PDF content stream formats.
        for page_num in sorted(pending.keys()):
            page_repls = pending[page_num]
            page = doc[page_num]

            # Phase 2: Draw white rectangles over old text
            shape = page.new_shape()
            for pr in page_repls:
                # Expand rect slightly for clean coverage
                cover = pr.rect + (-1, -1, 1, 1)
                shape.draw_rect(cover)
                shape.finish(fill=(1, 1, 1), color=(1, 1, 1), width=0)
            shape.commit()

            # Phase 3: Insert new text
            for pr in page_repls:
                baseline_y = pr.rect.y1 - (pr.font_size * 0.15)
                try:
                    page.insert_text(
                        point=(pr.rect.x0 + 1, baseline_y),
                        text=pr.new_value,
                        fontsize=pr.font_size,
                        fontname=pr.font_name,
                        color=pr.color,
                    )
                except Exception as e:
                    logger.error("Insert failed for '%s': %s", pr.field_name, e)
                    try:
                        page.insert_text(
                            point=(pr.rect.x0 + 1, baseline_y),
                            text=pr.new_value,
                            fontsize=pr.font_size,
                            fontname="helv",
                            color=pr.color,
                        )
                    except Exception as e2:
                        logger.error("Fallback insert failed: %s", e2)

        result_bytes = doc.tobytes()
        doc.close()

        all_replaced = replaced_fields | widget_filled
        return result_bytes, len(all_replaced), failed_fields

    def _fill_widgets(
        self,
        doc: fitz.Document,
        fields: list[dict],
        field_values: dict[str, str],
        filled: set[str],
    ) -> None:
        """Fill AcroForm widgets directly by widget_name mapping.

        Handles:
        - Text widgets: direct field_value assignment
        - CheckBox widgets: set to on_state() for truthy values, clear for falsy
        - Cifra widgets (max_len=1): single-digit fields, no special handling
        """
        # Build widget_name → (new_value, field_name) mapping
        widget_targets: dict[str, tuple[str, str]] = {}
        for f in fields:
            name = f.get("field_name", "")
            wn = f.get("widget_name", "")
            if name in field_values and wn:
                widget_targets[wn] = (field_values[name], name)
                filled.add(name)

        if not widget_targets:
            return

        for page_num in range(len(doc)):
            page = doc[page_num]
            for w in page.widgets():
                if w.field_name not in widget_targets:
                    continue

                new_val, field_name = widget_targets[w.field_name]
                old_val = w.field_value or ""

                if w.field_type_string == "CheckBox":
                    # Truthy values: "true", "1", "yes", "sí", "si", "x", on_state
                    truthy = new_val.strip().lower() in (
                        "true", "1", "yes", "sí", "si", "x", "on", "checked",
                    )
                    if truthy:
                        try:
                            w.field_value = w.on_state()
                        except Exception:
                            w.field_value = "Yes"
                    else:
                        w.field_value = ""  # unchecked
                    w.update()
                    logger.info(
                        "CheckBox %s: %s (was '%s')",
                        w.field_name,
                        "checked" if truthy else "unchecked",
                        old_val[:10],
                    )
                else:
                    # Text, ComboBox, ListBox
                    w.field_value = new_val
                    w.update()
                    logger.info(
                        "Widget filled: %s = '%s' (was '%s')",
                        w.field_name, new_val[:30], old_val[:30],
                    )

    def _find_by_direct_search(
        self,
        doc: fitz.Document,
        repl: dict,
        pending: dict[int, list[PendingReplacement]],
        claimed: set,
    ) -> bool:
        """Strategy 1: Direct text search for unique values."""
        found = False
        current_value = repl["current_value"]
        for page_num in range(len(doc)):
            page = doc[page_num]
            rects = page.search_for(current_value)
            for rect in rects:
                key = (page_num, round(rect.x0, 1), round(rect.y0, 1),
                       round(rect.x1, 1), round(rect.y1, 1))
                if key in claimed:
                    continue
                # Validate
                clip = page.get_text("text", clip=rect).strip()
                if not clip or current_value not in clip:
                    continue
                fs, fn, color = self._extract_style(page, rect)
                pending.setdefault(page_num, []).append(
                    PendingReplacement(
                        rect=rect, new_value=repl["new_value"],
                        font_size=fs, font_name=fn, color=color,
                        field_name=repl["field_name"],
                    )
                )
                claimed.add(key)
                found = True
        return found

    def _find_by_context(
        self,
        doc: fitz.Document,
        repl: dict,
        pending: dict[int, list[PendingReplacement]],
        claimed: set,
    ) -> bool:
        """Strategy 2: Context-anchor search for dots/placeholder fields.

        1. Extract anchor text from context_hint (non-dots part)
        2. Search for anchor to find the line (Y coordinate)
        3. Find dots rects on that same line, to the right of the anchor
        4. Claim the first unclaimed dots rect
        """
        anchor = _extract_context_anchor(repl["context_hint"])
        if not anchor:
            # Fallback: try direct search
            return self._find_by_direct_search(doc, repl, pending, claimed)

        for page_num in range(len(doc)):
            page = doc[page_num]
            anchor_rects = page.search_for(anchor)
            if not anchor_rects:
                continue

            for ar in anchor_rects:
                # Search for dots on the same line (similar Y)
                dots_rects = page.search_for(_MIN_DOTS)
                # Filter: same line (Y within 3pt) and to the right of anchor
                same_line = []
                for dr in dots_rects:
                    if abs(dr.y0 - ar.y0) < 3 and dr.x0 >= ar.x0 - 5:
                        key = (page_num, round(dr.x0, 1), round(dr.y0, 1),
                               round(dr.x1, 1), round(dr.y1, 1))
                        if key not in claimed:
                            same_line.append((dr, key))

                if not same_line:
                    continue

                # Take the first unclaimed dots rect (closest to anchor)
                same_line.sort(key=lambda x: x[0].x0)
                dots_rect, rect_key = same_line[0]

                fs, fn, color = self._extract_style(page, dots_rect)
                pending.setdefault(page_num, []).append(
                    PendingReplacement(
                        rect=dots_rect, new_value=repl["new_value"],
                        font_size=fs, font_name=fn, color=color,
                        field_name=repl["field_name"],
                    )
                )
                claimed.add(rect_key)
                return True

        return False

    def _extract_style(
        self, page: fitz.Page, rect: fitz.Rect
    ) -> tuple[float, str, tuple]:
        """Extract font size, Base14 name, and RGB color from text in a rect."""
        font_size = 12.0
        font_name = "helv"
        color = (0, 0, 0)

        try:
            text_dict = page.get_text("dict", clip=rect)
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_size = span.get("size", 12.0)
                        raw_font = span.get("font", "")
                        font_name = _normalize_font_name(raw_font)
                        color_int = span.get("color", 0)
                        color = (
                            ((color_int >> 16) & 0xFF) / 255.0,
                            ((color_int >> 8) & 0xFF) / 255.0,
                            (color_int & 0xFF) / 255.0,
                        )
                        return font_size, font_name, color
        except Exception as e:
            logger.warning("Could not extract style: %s", e)

        return font_size, font_name, color


_replacer = None


def get_pdf_replacer() -> PdfReplacer:
    global _replacer
    if _replacer is None:
        _replacer = PdfReplacer()
    return _replacer
