# PDF-to-PDF Document Forge Support — Design Spec

**Date**: 2026-03-14
**Status**: Draft
**Scope**: Extend document-forge-service to accept PDF input and produce PDF output using PyMuPDF (fitz) for direct text replacement.

## Context

The document-forge-service currently only supports DOCX files: it extracts text via python-docx, detects variable fields via LLM, inserts Jinja2 markers via a template preparer, and renders final documents via docxtpl. Many real-world documents exist only as PDFs (scanned contracts, government forms, signed agreements). This extension adds PDF-to-PDF support using PyMuPDF's redact & insert strategy.

## Architecture

### Strategy Pattern by Format

The session stores `source_format: "pdf" | "docx"`. Each phase selects the correct pipeline:

```
                    ┌─────────────────────────────────┐
   File upload ──►  │  /analyze (auto-detect format)   │
                    │  PDF → PyMuPDF text extraction    │
                    │  DOCX → python-docx extraction    │
                    │  → LLM field detection (shared)   │
                    │  → session.source_format = X      │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │  /render (format-aware)           │
                    │  DOCX → prepare markers + docxtpl │
                    │  PDF → redact & insert (PyMuPDF)  │
                    │  → output: same format as input   │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │  /download + /persist (unchanged) │
                    └─────────────────────────────────┘
```

- The LLM analysis is identical for both formats — only text extraction differs.
- PDF skips the prepare phase (no Jinja2 markers). Replacement is direct: search text → redact → insert new value.
- Output format matches input format (PDF→PDF, DOCX→DOCX).
- Cross-format conversion (DOCX→PDF) remains available via Gotenberg as an additional output format.

### Format Auto-Detection

The `/analyze` endpoint detects the input format by:
1. File extension (`.pdf` vs `.docx`)
2. Content-type header (`application/pdf` vs `application/vnd.openxmlformats-officedocument.wordprocessingml.document`)
3. Magic bytes fallback (PDF starts with `%PDF-`, DOCX is a ZIP archive)

The detected format is stored as `session.source_format` and used by downstream endpoints.

## PDF Text Extraction

**New file**: `app/services/pdf_extractor.py`

Extracts plain text from PDF pages using PyMuPDF:

```python
import fitz  # PyMuPDF

def extract_text_from_pdf(pdf_bytes: bytes, max_chars: int = 20000) -> tuple[str, str]:
    """Extract text and title from PDF bytes.

    Returns: (text, title)
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # Title: PDF metadata > first line of text
    title = doc.metadata.get("title", "") or ""

    text_parts = []
    for page in doc:
        text_parts.append(page.get_text("text"))

    full_text = "\n".join(text_parts)

    if not title:
        # Use first non-empty line as title
        for line in full_text.split("\n"):
            line = line.strip()
            if line and len(line) > 3:
                title = line[:100]
                break

    doc.close()
    return full_text[:max_chars], title
```

This replaces the DOCX-specific text extraction in `analyze.py` when the input is PDF.

## PDF Replacement Engine

**New file**: `app/services/pdf_replacer.py`

### Class: PdfReplacer

Performs text replacement in PDF files using PyMuPDF's redact & insert strategy:

```python
class PdfReplacer:
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
```

### Replacement Algorithm

For each field that has a new value:

1. **Search**: Use `page.search_for(current_value)` to find all instances of the text on each page. Returns a list of `fitz.Rect` bounding boxes.

2. **Capture style**: Extract font properties from the matched region using `page.get_text("dict", clip=rect)`:
   - `font_size`: from span `size`
   - `font_name`: from span `font` (fallback to "helv" / Helvetica if not a standard PDF font)
   - `color`: from span `color` (RGB tuple)

3. **Redact**: Apply `page.add_redact_annot(rect, fill=(1, 1, 1))` to white-out the original text, then `page.apply_redactions()` to commit.

4. **Insert**: Write the new value at the same position using `page.insert_text(point, text, fontsize, fontname, color)`. The insertion point is `(rect.x0, rect.y0 + font_size)` (PyMuPDF uses bottom-left baseline for text positioning).

### Text Overflow Behavior

When the new text is longer than the original, the text **overflows** (extends beyond the original bounding box). The font size is NOT adjusted. This is intentional:
- Preserves document readability and design consistency
- Legal documents require legible, consistent font sizes
- Users can see and adjust if overlap occurs

### Font Handling

PyMuPDF cannot reuse most embedded PDF fonts for new text insertion. Strategy:
- If the detected font matches a PDF Base14 font (Helvetica, Times, Courier, etc.) → use it directly
- Otherwise → fallback to "helv" (Helvetica), preserving the original size and color
- A mapping of common font names to Base14 equivalents handles common cases (e.g., "Arial" → "helv", "TimesNewRomanPSMT" → "tiro")

### Multi-Instance Replacement

If a field's `current_value` appears multiple times in the document (e.g., a person's name in header and signature), ALL instances are replaced. This matches the DOCX template_preparer behavior.

### Sort Order

Replacements are sorted by `current_value` length descending (longest first) to avoid partial matches. Same strategy as the DOCX template_preparer.

## Changes to Existing Files

### `app/api/analyze.py`

- Auto-detect format from uploaded file (extension, content-type, magic bytes)
- If PDF: extract text with `pdf_extractor.extract_text_from_pdf()`
- If DOCX: existing python-docx extraction (unchanged)
- Store `source_format` in session
- Store source bytes in Redis blob (same key "source", works for both formats)
- LLM analysis call is unchanged — receives plain text regardless of format

### `app/api/render.py`

In the `/render` endpoint:
- Check `session.source_format`
- If `"docx"`: existing pipeline (auto-prepare + docxtpl render)
- If `"pdf"`: call `PdfReplacer.replace()` directly with source bytes + field_values
  - Skip prepare phase entirely (no Jinja2 markers for PDF)
  - Store result in Redis blob "pdf" (not "docx")
  - Return download URL with `?format=pdf`

### `app/schemas/session.py`

Add to `ForgeSession`:
```python
source_format: str = "docx"  # "pdf" or "docx"
```

Default is "docx" for backward compatibility with existing sessions.

### `app/api/sessions.py`

- The download endpoint already accepts `format` query param
- Add logic: when `session.source_format == "pdf"`, the default download format is "pdf"
- Content-type: `application/pdf` for PDF downloads

### `requirements.txt`

Add:
```
pymupdf>=1.24.0
```

## Files NOT Changed

These files require zero modifications:
- `app/services/analyzer.py` — receives plain text, format-agnostic
- `app/services/template_preparer.py` — only used for DOCX pipeline
- `app/services/renderer.py` — only used for DOCX pipeline
- `app/services/converter.py` — DOCX→PDF conversion, still available
- `app/clients/llm_client.py` — format-agnostic
- `app/core/config.py` — no new config needed
- `app/api/persist.py` — stores whatever blob format the session has
- All frontend files — no changes needed

## Frontend Impact

**Zero**. The frontend uploads a file, receives detected fields, sends field values, and downloads the result. It does not need to know or care whether the source was PDF or DOCX. The `source_format` field in session metadata is available for display purposes but not required for functionality.

## Known Limitations

1. **Scanned PDFs**: If the PDF is a scanned image (no text layer), `search_for()` returns nothing. The analyzer will detect 0 fields. OCR support is out of scope.

2. **Non-standard fonts**: Embedded custom fonts (corporate branding, etc.) are replaced with Helvetica. The size and color are preserved but the typeface changes.

3. **Multi-line fields**: If a field value spans multiple lines in the PDF, `search_for()` may not find it as a single match. The LLM's `current_value` must match a single contiguous text block.

4. **White background assumption**: The redact annotation fills with white `(1,1,1)`. Documents with colored backgrounds will show white patches.

5. **Text overflow**: Longer replacement text extends beyond the original bounding box. No automatic resizing.

6. **Right-to-left text**: Not tested. PyMuPDF supports RTL but the replacement logic assumes LTR positioning.

## Testing

- Use existing test PDF: `~/RRHH-contrato-duracion-determinada-expira-20-02-2026.pdf` (2 pages, text-based)
- Create additional test PDF via the DOCX test contract: convert `~/contrato-test-forge.docx` to PDF with LibreOffice
- Verify: all 8 field types detected, text replaced, font preserved, multi-instance replacement works
