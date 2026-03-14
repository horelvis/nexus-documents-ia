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

**IMPORTANT**: Redactions must be batched per page. Calling `apply_redactions()` rewrites the page content stream, invalidating text positions for subsequent `search_for()` calls. The algorithm is therefore **three-phase per page**:

**Phase 1 — Collect**: For each field with a new value, search all pages and collect match info:
```python
@dataclass
class PendingReplacement:
    rect: fitz.Rect          # bounding box of original text
    new_value: str            # replacement text
    font_size: float          # detected from original
    font_name: str            # mapped to Base14 (or "helv" fallback)
    color: tuple              # RGB from original span
```

For each match found via `page.search_for(current_value)`:
1. **Validate**: Confirm `page.get_text("text", clip=rect).strip()` matches `current_value` (prevents redacting overlapping content that is not the target).
2. **Capture style**: Extract font properties from `page.get_text("dict", clip=rect)` spans — `size`, `font` (mapped via font table), `color`.
3. Append to `pending_replacements[page_number]` list.

**Phase 2 — Redact**: For each page that has pending replacements:
```python
for repl in pending_replacements[page_num]:
    page.add_redact_annot(repl.rect, text="", fill=(1, 1, 1))
page.apply_redactions()  # ONCE per page
```

The `text=""` parameter is required to prevent PyMuPDF from inserting default replacement text.

**Phase 3 — Insert**: For each pending replacement on the page:
```python
for repl in pending_replacements[page_num]:
    # Baseline positioning: use rect bottom minus descent estimate
    baseline_y = repl.rect.y1 - (repl.font_size * 0.2)  # ~20% descent
    page.insert_text(
        point=(repl.rect.x0, baseline_y),
        text=repl.new_value,
        fontsize=repl.font_size,
        fontname=repl.font_name,
        color=repl.color,
    )
```

The baseline formula `rect.y1 - (font_size * 0.2)` approximates the text baseline. The 20% descent factor works for most Latin fonts. This must be validated against the test PDFs and adjusted if needed.

### Text Overflow Behavior

When the new text is longer than the original, the text **overflows** (extends beyond the original bounding box). The font size is NOT adjusted. This is intentional:
- Preserves document readability and design consistency
- Legal documents require legible, consistent font sizes
- Users can see and adjust if overlap occurs

### Font Handling

PyMuPDF cannot reuse most embedded PDF fonts for new text insertion. Strategy:
- If the detected font matches a PDF Base14 font (Helvetica, Times, Courier, etc.) → use it directly
- Otherwise → fallback to "helv" (Helvetica), preserving the original size and color

**Font name mapping table** (embedded PDF name → Base14):
```python
_FONT_MAP = {
    "arial": "helv",
    "arialmt": "helv",
    "arial-bold": "hebo",
    "arial-boldmt": "hebo",
    "arial-italic": "heit",
    "helvetica": "helv",
    "timesnewroman": "tiro",
    "timesnewromanpsmt": "tiro",
    "timesnewroman-bold": "tibo",
    "courier": "cour",
    "couriernew": "cour",
    "calibri": "helv",        # no Calibri in Base14, closest is Helvetica
    "calibri-bold": "hebo",
    "cambria": "tiro",        # serif, closest is Times
}
```

Font name normalization: strip subset prefix (e.g., `ABCDEF+ArialMT` → `arialmt`), lowercase, remove spaces. If not in map, fallback to `"helv"`.

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
- Check `session.source_format` **before** the auto-prepare block
- If `"pdf"`:
  - **Bypass the entire auto-prepare block** (the `if session.status == SessionStatus.ANALYZED:` branch that calls `get_template_preparer()` must NOT execute for PDF — it would crash trying to parse PDF bytes as DOCX)
  - Load source PDF from Redis blob "source"
  - Call `PdfReplacer.replace(pdf_bytes, session.fields, request.field_values)`
  - Store result in Redis blob "pdf"
  - Return `failed_fields` in response if any replacements failed
  - Return download URL with `?format=pdf`
- If `"docx"`: existing pipeline unchanged (auto-prepare + docxtpl render)

**`output_formats` handling for PDF sessions**:
- `["pdf"]` → return the forged PDF (primary output)
- `["docx"]` → ignored for PDF sessions (no DOCX available), omit from outputs
- `["both"]` or `["docx", "pdf"]` → return only PDF, omit DOCX (no cross-format conversion)
- The frontend `forge.service.ts` sends `['docx', 'pdf']` by default — backend gracefully returns only what's available

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

### `app/services/storage.py`

The Weaviate indexing condition currently requires `docx_bytes`:
```python
if index_in_weaviate and docx_bytes and result.get("gcs_paths", {}).get("docx"):
```

Change to also accept PDF-only sessions:
```python
has_indexable = (docx_bytes and result.get("gcs_paths", {}).get("docx")) or \
               (pdf_bytes and result.get("gcs_paths", {}).get("pdf"))
if index_in_weaviate and has_indexable:
```

The `PersistRequest.persist_formats` default changes from `["docx"]` to session-aware: use `[session.source_format]` when no explicit formats provided.

### `requirements.txt`

Add:
```
pymupdf>=1.24.0,<2.0.0
```

Upper bound `<2.0.0` for safety — PyMuPDF has a history of breaking API changes between major versions.

## Files NOT Changed

These files require zero modifications:
- `app/services/analyzer.py` — receives plain text, format-agnostic
- `app/services/template_preparer.py` — only used for DOCX pipeline
- `app/services/renderer.py` — only used for DOCX pipeline
- `app/services/converter.py` — DOCX→PDF conversion, still available
- `app/clients/llm_client.py` — format-agnostic
- `app/core/config.py` — no new config needed
- All frontend files — no changes needed

## Frontend Impact

**Minimal**. The frontend uploads a file, receives detected fields, sends field values, and downloads the result. It does not need to know whether the source was PDF or DOCX. The `source_format` field is included in session info responses, allowing the frontend to default the download format correctly (e.g., show "Download PDF" instead of "Download DOCX" for PDF-source sessions). This is a display improvement, not a requirement.

## Known Limitations

1. **Scanned PDFs**: If the PDF is a scanned image (no text layer), `search_for()` returns nothing. The analyzer will detect 0 fields. OCR support is out of scope.

2. **Non-standard fonts**: Embedded custom fonts (corporate branding, etc.) are replaced with Helvetica. The size and color are preserved but the typeface changes.

3. **Multi-line fields**: If a field value spans multiple lines in the PDF, `search_for()` may not find it as a single match. The LLM's `current_value` must match a single contiguous text block.

4. **White background assumption**: The redact annotation fills with white `(1,1,1)`. Documents with colored backgrounds will show white patches.

5. **Text overflow**: Longer replacement text extends beyond the original bounding box. No automatic resizing.

6. **Right-to-left text**: Not tested. PyMuPDF supports RTL but the replacement logic assumes LTR positioning.

7. **Text matching fragility**: The LLM extracts `current_value` from `page.get_text("text")` output, but `page.search_for()` searches the PDF's internal text representation. These may differ in whitespace, ligatures (e.g., "fi" stored as U+FB01), or Unicode normalization. The Phase 1 validation step (`get_text("text", clip=rect)` vs `current_value`) catches false positives but cannot fix cases where `search_for()` fails to find valid text. If a field is not found, it appears in `failed_fields`.

8. **Overlapping text regions**: `apply_redactions()` removes ALL content under the redact rect, not just the target text. If PDF text spans overlap visually (common with kerning or layered elements), adjacent characters may be destroyed. The Phase 1 validation mitigates this by confirming the rect content matches before redacting.

## Testing

- Use existing test PDF: `~/RRHH-contrato-duracion-determinada-expira-20-02-2026.pdf` (2 pages, text-based)
- Create additional test PDF via the DOCX test contract: convert `~/contrato-test-forge.docx` to PDF with LibreOffice
- Verify: all 8 field types detected, text replaced, font preserved, multi-instance replacement works
