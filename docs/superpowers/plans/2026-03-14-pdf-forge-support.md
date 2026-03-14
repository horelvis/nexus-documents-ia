# PDF-to-PDF Document Forge Support — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend document-forge-service to accept PDF files and produce modified PDFs using PyMuPDF's redact & insert strategy, keeping the existing DOCX pipeline untouched.

**Architecture:** Format auto-detection in `/analyze`, shared LLM field detection, format-aware `/render` that branches between DOCX (existing docxtpl pipeline) and PDF (new PyMuPDF redact & insert). Three-phase batched replacement per page: collect matches → batch redact → insert new text.

**Tech Stack:** PyMuPDF (fitz) for PDF text extraction and replacement, existing FastAPI + Redis session store.

**Spec:** `docs/superpowers/specs/2026-03-14-pdf-forge-support-design.md`

**Base path:** `backend/microservices/document-forge-service/`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/services/pdf_extractor.py` | Extract plain text + title from PDF bytes via PyMuPDF |
| Create | `app/services/pdf_replacer.py` | Three-phase redact & insert text replacement in PDFs |
| Modify | `app/schemas/session.py:17-29` | Add `source_format` field to ForgeSession |
| Modify | `app/api/analyze.py:63-159` | Auto-detect format, branch text extraction |
| Modify | `app/api/render.py:70-162` | Branch PDF vs DOCX pipeline, handle output_formats |
| Modify | `app/api/sessions.py:21-47` | Default download format from session.source_format |
| Modify | `app/api/persist.py:33-45` | Format-aware persist_formats default |
| Modify | `app/services/storage.py:69-84` | Accept PDF-only sessions for Weaviate indexing |
| Modify | `requirements.txt` | Add `pymupdf>=1.24.0,<2.0.0` |

---

## Chunk 1: Core PDF Engine (New Files)

### Task 1: Add PyMuPDF dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add pymupdf to requirements**

Append to `requirements.txt` after line 11 (`pyyaml>=6.0.0`):

```
pymupdf>=1.24.0,<2.0.0
```

- [ ] **Step 2: Rebuild Docker image**

```bash
cd backend/docker && docker compose build document-forge-service 2>&1 | tail -5
```

Expected: Build succeeds, pymupdf installed.

- [ ] **Step 3: Verify import works inside container**

```bash
docker compose exec document-forge-service python -c "import fitz; print(f'PyMuPDF {fitz.version}')"
```

Expected: Prints version like `PyMuPDF 1.25.x`.

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/document-forge-service/requirements.txt
git commit -m "feat(forge): add pymupdf dependency for PDF support"
```

---

### Task 2: Create PDF text extractor

**Files:**
- Create: `app/services/pdf_extractor.py`

- [ ] **Step 1: Create the extractor module**

```python
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
```

- [ ] **Step 2: Test manually with the existing test PDF**

```bash
docker compose exec document-forge-service python -c "
import fitz
with open('/dev/stdin', 'rb') as f:
    pass
# Quick test: extract from a simple PDF
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), 'Test Document Title', fontsize=16)
page.insert_text((72, 100), 'Name: Carlos Martinez', fontsize=12)
pdf_bytes = doc.tobytes()
doc.close()

from app.services.pdf_extractor import extract_text_from_pdf
text, title = extract_text_from_pdf(pdf_bytes)
print(f'Title: {title}')
print(f'Text length: {len(text)}')
assert 'Carlos Martinez' in text
print('OK')
"
```

Expected: Prints title and text, assertion passes.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/document-forge-service/app/services/pdf_extractor.py
git commit -m "feat(forge): add PDF text extractor using PyMuPDF"
```

---

### Task 3: Create PDF replacer engine

**Files:**
- Create: `app/services/pdf_replacer.py`

This is the core engine. It implements the three-phase batched replacement algorithm from the spec.

- [ ] **Step 1: Create the replacer module**

```python
"""PDF text replacement using PyMuPDF redact & insert strategy.

Three-phase algorithm per page:
  Phase 1 — Collect: search all fields, validate matches, capture font styles
  Phase 2 — Redact: batch all redactions, apply once per page
  Phase 3 — Insert: write new text at original positions
"""

import logging
from dataclasses import dataclass, field
from io import BytesIO

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

    normalized = font_name.lower().replace(" ", "").replace(",", ",")

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
```

- [ ] **Step 2: Verify module loads in container**

```bash
docker compose restart document-forge-service
sleep 5
docker compose exec document-forge-service python -c "from app.services.pdf_replacer import get_pdf_replacer; print('OK')"
```

Expected: Prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/document-forge-service/app/services/pdf_extractor.py \
        backend/microservices/document-forge-service/app/services/pdf_replacer.py
git commit -m "feat(forge): add PDF text extractor and replacer engine"
```

---

## Chunk 2: Session Schema + Analyze Endpoint

### Task 4: Add source_format to ForgeSession

**Files:**
- Modify: `app/schemas/session.py:17-29`

- [ ] **Step 1: Add source_format field**

In `ForgeSession` class (line 28, after `confidence: float = 0.0`), add:

```python
    source_format: str = "docx"  # "pdf" or "docx"
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/document-forge-service/app/schemas/session.py
git commit -m "feat(forge): add source_format field to ForgeSession schema"
```

---

### Task 5: Add format auto-detection to /analyze

**Files:**
- Modify: `app/api/analyze.py`

- [ ] **Step 1: Add format detection helper and PDF extractor import**

After line 6 (`from fastapi import ...`), add:

```python
from app.services.pdf_extractor import extract_text_from_pdf
```

After the `_extract_title_from_docx` function (after line 60), add:

```python
def _detect_format(filename: str, content: bytes) -> str:
    """Auto-detect document format from filename and magic bytes.

    Returns: 'pdf' or 'docx'
    """
    # 1. Extension
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext == "pdf":
            return "pdf"
        if ext in ("docx", "doc"):
            return "docx"

    # 2. Magic bytes
    if content[:5] == b"%PDF-":
        return "pdf"
    if content[:4] == b"PK\x03\x04":  # ZIP (DOCX is a ZIP archive)
        return "docx"

    # Default
    return "docx"
```

- [ ] **Step 2: Modify the analyze endpoint to branch by format**

Replace lines 80-129 (from `settings = get_settings()` through `title = _extract_title_from_docx(...)`) with:

```python
    settings = get_settings()
    file_bytes: bytes | None = None
    source_title = "document"

    # Path 1: Direct upload
    if file is not None:
        content = await file.read()
        if len(content) > settings.max_document_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {settings.max_document_size_mb}MB limit",
            )
        file_bytes = content
        source_title = file.filename or "uploaded_document"

    # Path 2: Fetch by document_id
    elif document_id:
        weaviate = get_weaviate_client()
        metadata = await weaviate.get_document_metadata(document_id, tenant_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = metadata.get("file_path", "")
        if not file_path:
            raise HTTPException(status_code=404, detail="Document file path not found")

        source_title = metadata.get("file_name", metadata.get("title", "document"))

        storage = get_storage_client()
        file_bytes = await storage.download_document(file_path, tenant_id)
        if not file_bytes:
            raise HTTPException(status_code=404, detail="Could not download document")
    else:
        raise HTTPException(
            status_code=400, detail="Provide either a file upload or document_id"
        )

    # Auto-detect format
    source_format = _detect_format(source_title, file_bytes)

    # Extract text based on format
    if source_format == "pdf":
        try:
            document_text, title = extract_text_from_pdf(
                file_bytes, max_chars=settings.max_source_chars,
            )
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not parse PDF: {e}")
    else:
        try:
            document_text = _extract_text_from_docx(file_bytes)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not parse DOCX: {e}")
        title = _extract_title_from_docx(file_bytes, source_title)
```

- [ ] **Step 3: Store source_format in session**

Replace lines 140-151 (session creation block) with:

```python
    # Create session and store source bytes
    store = get_session_store()
    session = await store.create_session(tenant_id, user_id)
    session.source_title = source_title
    session.source_format = source_format
    session.document_type = result.get("document_type", "")
    session.fields = result.get("fields", [])
    session.confidence = result.get("confidence", 0.0)
    session.status = SessionStatus.ANALYZED
    await store.update_session(session)

    # Store original file bytes for later rendering
    await store.store_blob(session.session_id, "source", file_bytes)
```

- [ ] **Step 4: Test with the existing PDF**

```bash
API_KEY=$(grep "^MICROSERVICES_API_KEY=" backend/docker/.env | cut -d= -f2)
# Wait for reload
sleep 8
curl -s -X POST http://localhost:8013/analyze \
  -H "X-API-Key: ${API_KEY}" \
  -F "tenant_id=00000000-0000-0000-0000-000000000001" \
  -F "user_id=a060f046-9992-4d1a-87c4-fa5c6f8c066c" \
  -F "user_intent=renewal" \
  -F "file=@${HOME}/RRHH-contrato-duracion-determinada-expira-20-02-2026.pdf" \
  > /tmp/forge_pdf_test.json
python3 -c "
import json; d = json.load(open('/tmp/forge_pdf_test.json'))
print(f'Session: {d[\"session_id\"]}')
print(f'Fields: {len(d.get(\"fields\",[]))}')
print(f'Confidence: {d.get(\"confidence\",0):.0%}')
"
```

Expected: Fields detected (count > 0), no errors.

- [ ] **Step 5: Also test that DOCX still works (regression)**

```bash
curl -s -X POST http://localhost:8013/analyze \
  -H "X-API-Key: ${API_KEY}" \
  -F "tenant_id=00000000-0000-0000-0000-000000000001" \
  -F "user_id=a060f046-9992-4d1a-87c4-fa5c6f8c066c" \
  -F "user_intent=renewal" \
  -F "file=@${HOME}/contrato-test-forge.docx" \
  > /tmp/forge_docx_regression.json
python3 -c "
import json; d = json.load(open('/tmp/forge_docx_regression.json'))
print(f'DOCX regression: {len(d.get(\"fields\",[]))} fields, {d.get(\"confidence\",0):.0%} confidence')
assert len(d.get('fields',[])) > 0, 'REGRESSION: DOCX analysis returned 0 fields'
print('DOCX OK')
"
```

Expected: Fields detected, `DOCX OK` printed.

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/document-forge-service/app/api/analyze.py
git commit -m "feat(forge): add PDF format auto-detection and text extraction to /analyze"
```

---

## Chunk 3: Render Endpoint + Download + Persist

### Task 6: Add PDF branch to /render

**Files:**
- Modify: `app/api/render.py:1-162`

- [ ] **Step 1: Add PDF replacer import**

After line 19 (`from app.services.template_preparer import get_template_preparer`), add:

```python
from app.services.pdf_replacer import get_pdf_replacer
```

- [ ] **Step 2: Add PDF render branch**

Replace lines 75-162 (the entire `render_document` function body after the function signature) with:

```python
    """Fill markers with values and generate final document."""
    store = get_session_store()
    session = await store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # --- PDF pipeline: direct redact & insert (no prepare phase) ---
    if getattr(session, "source_format", "docx") == "pdf":
        if session.status not in (SessionStatus.ANALYZED, SessionStatus.RENDERED):
            raise HTTPException(
                status_code=400,
                detail=f"Session in wrong state: {session.status}. Expected: analyzed",
            )

        source_bytes = await store.get_blob(session.session_id, "source")
        if not source_bytes:
            raise HTTPException(status_code=404, detail="Source PDF not found")

        replacer = get_pdf_replacer()
        pdf_bytes, replaced_count, failed = replacer.replace(
            pdf_bytes=source_bytes,
            fields=session.fields,
            field_values=request.field_values,
        )

        # Store rendered PDF
        await store.store_blob(session.session_id, "pdf", pdf_bytes)

        doc_title = request.document_title or session.source_title.rsplit(".", 1)[0]

        outputs: dict[str, OutputInfo] = {
            "pdf": OutputInfo(
                size_bytes=len(pdf_bytes),
                download_url=f"/sessions/{session.session_id}/download?format=pdf",
            )
        }

        if failed:
            logger.warning("PDF render: %d fields failed: %s", len(failed), failed)

        # Update session
        session.status = SessionStatus.RENDERED
        session.field_values = request.field_values
        session.document_title = doc_title
        await store.update_session(session)

        return RenderResponse(
            session_id=session.session_id,
            outputs=outputs,
            fields_filled=replaced_count,
            document_title=doc_title,
        )

    # --- DOCX pipeline: existing prepare + docxtpl render ---
    # Allow rendering from either PREPARED or ANALYZED state
    # If ANALYZED, we auto-prepare first (mark all fields)
    if session.status == SessionStatus.ANALYZED:
        source_bytes = await store.get_blob(session.session_id, "source")
        if not source_bytes:
            raise HTTPException(status_code=404, detail="Source document not found")

        preparer = get_template_preparer()
        # Only mark fields that have values provided
        fields_to_mark = list(request.field_values.keys())
        template_bytes, inserted, failed = preparer.prepare(
            docx_bytes=source_bytes,
            fields=session.fields,
            fields_to_mark=fields_to_mark,
        )
        await store.store_blob(session.session_id, "template", template_bytes)
        session.status = SessionStatus.PREPARED
        await store.update_session(session)
    elif session.status not in (SessionStatus.PREPARED, SessionStatus.RENDERED):
        raise HTTPException(
            status_code=400,
            detail=f"Session in wrong state: {session.status}. Expected: prepared or analyzed",
        )

    # Get prepared template
    template_bytes = await store.get_blob(session.session_id, "template")
    if not template_bytes:
        raise HTTPException(status_code=404, detail="Prepared template not found")

    # Render with docxtpl
    renderer = get_renderer()
    docx_bytes = renderer.render(template_bytes, request.field_values)

    # Store rendered DOCX
    await store.store_blob(session.session_id, "docx", docx_bytes)

    # Determine document title
    doc_title = request.document_title or session.source_title.rsplit(".", 1)[0]

    outputs: dict[str, OutputInfo] = {}

    # Normalize output formats
    formats = set()
    for fmt in request.output_formats:
        if fmt == "both":
            formats.update(["docx", "pdf"])
        else:
            formats.add(fmt)

    # DOCX output
    if "docx" in formats:
        outputs["docx"] = OutputInfo(
            size_bytes=len(docx_bytes),
            download_url=f"/sessions/{session.session_id}/download?format=docx",
        )

    # PDF output
    if "pdf" in formats:
        converter = get_converter()
        try:
            pdf_bytes = await converter.docx_to_pdf(docx_bytes, f"{doc_title}.docx")
            await store.store_blob(session.session_id, "pdf", pdf_bytes)
            outputs["pdf"] = OutputInfo(
                size_bytes=len(pdf_bytes),
                download_url=f"/sessions/{session.session_id}/download?format=pdf",
            )
        except Exception as e:
            logger.error("PDF conversion failed: %s", e)
            # PDF failure is non-fatal — DOCX still available

    # Update session
    session.status = SessionStatus.RENDERED
    session.field_values = request.field_values
    session.document_title = doc_title
    await store.update_session(session)

    return RenderResponse(
        session_id=session.session_id,
        outputs=outputs,
        fields_filled=len(request.field_values),
        document_title=doc_title,
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/document-forge-service/app/api/render.py
git commit -m "feat(forge): add PDF render branch with redact & insert pipeline"
```

---

### Task 7: Update persist for PDF-only sessions

**Files:**
- Modify: `app/api/persist.py:33-45`
- Modify: `app/services/storage.py:69-84`

- [ ] **Step 1: Make persist format-aware**

In `app/api/persist.py`, replace lines 33-45 (the blob retrieval block) with:

```python
    # Get rendered outputs — format-aware
    docx_bytes = None
    pdf_bytes = None
    source_format = getattr(session, "source_format", "docx")

    # Default persist formats to source format if not explicitly provided
    persist_formats = request.persist_formats
    if persist_formats == ["docx"] and source_format == "pdf":
        persist_formats = ["pdf"]

    if "docx" in persist_formats:
        docx_bytes = await store.get_blob(request.session_id, "docx")
        if not docx_bytes and source_format == "docx":
            raise HTTPException(status_code=404, detail="No DOCX output in session")

    if "pdf" in persist_formats:
        pdf_bytes = await store.get_blob(request.session_id, "pdf")
        if not pdf_bytes and source_format == "pdf":
            raise HTTPException(status_code=404, detail="No PDF output in session")
        elif not pdf_bytes:
            logger.warning("No PDF output in session, skipping PDF persistence")
```

- [ ] **Step 2: Fix Weaviate indexing for PDF-only sessions**

In `app/services/storage.py`, replace lines 68-84 (the Weaviate indexing block) with:

```python
        # Index in Weaviate — accept either DOCX or PDF
        has_docx = docx_bytes and result.get("gcs_paths", {}).get("docx")
        has_pdf = pdf_bytes and result.get("gcs_paths", {}).get("pdf")

        if index_in_weaviate and (has_docx or has_pdf):
            # Prefer DOCX for indexing; fall back to PDF
            if has_docx:
                index_name = f"{document_title}.docx"
                index_path = result["gcs_paths"]["docx"]
                index_type = DOCX_CONTENT_TYPE
            else:
                index_name = f"{document_title}.pdf"
                index_path = result["gcs_paths"]["pdf"]
                index_type = PDF_CONTENT_TYPE

            weaviate = get_weaviate_client()
            index_result = await weaviate.index_document(
                tenant_id=tenant_id,
                document_data={
                    "document_id": result.get("document_id", ""),
                    "file_name": index_name,
                    "file_path": index_path,
                    "content_type": index_type,
                    "user_id": user_id,
                    "folder_path": folder_path,
                },
            )
            if index_result:
                result["weaviate_indexed"] = True
                result["indexed_document_id"] = index_result.get("document_id")
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/document-forge-service/app/api/persist.py \
        backend/microservices/document-forge-service/app/services/storage.py
git commit -m "feat(forge): support PDF-only sessions in persist and Weaviate indexing"
```

---

## Chunk 4: End-to-End Testing

### Task 8: Full PDF E2E test

**Files:** None (test only)

- [ ] **Step 1: Wait for service reload and test full pipeline**

```bash
sleep 8
API_KEY=$(grep "^MICROSERVICES_API_KEY=" backend/docker/.env | cut -d= -f2)

# Step 1: Analyze PDF
echo "=== ANALYZE ==="
curl -s -X POST http://localhost:8013/analyze \
  -H "X-API-Key: ${API_KEY}" \
  -F "tenant_id=00000000-0000-0000-0000-000000000001" \
  -F "user_id=a060f046-9992-4d1a-87c4-fa5c6f8c066c" \
  -F "user_intent=renewal" \
  -F "file=@${HOME}/RRHH-contrato-duracion-determinada-expira-20-02-2026.pdf" \
  > /tmp/forge_pdf_e2e.json

SESSION=$(python3 -c "import json; print(json.load(open('/tmp/forge_pdf_e2e.json'))['session_id'])")
FIELDS=$(python3 -c "import json; d=json.load(open('/tmp/forge_pdf_e2e.json')); print(len(d.get('fields',[])))")
echo "Session: ${SESSION}, Fields: ${FIELDS}"

# Get first 3 field names for render
FIELD_JSON=$(python3 -c "
import json; d = json.load(open('/tmp/forge_pdf_e2e.json'))
vals = {}
for f in d['fields'][:3]:
    vals[f['field_name']] = f['current_value'] + ' MODIFIED'
print(json.dumps(vals))
")

# Step 2: Render PDF
echo ""
echo "=== RENDER ==="
curl -s -X POST http://localhost:8013/render \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"${SESSION}\", \"field_values\": ${FIELD_JSON}, \"output_formats\": [\"pdf\"]}" \
  > /tmp/forge_pdf_render.json

python3 -c "import json; d=json.load(open('/tmp/forge_pdf_render.json')); print(f'Fields filled: {d[\"fields_filled\"]}')"

# Step 3: Download
echo ""
echo "=== DOWNLOAD ==="
curl -s -o /tmp/forge_pdf_output.pdf "http://localhost:8013/sessions/${SESSION}/download?format=pdf" \
  -H "X-API-Key: ${API_KEY}"
file /tmp/forge_pdf_output.pdf
ls -la /tmp/forge_pdf_output.pdf

echo ""
echo "=== VERIFY ==="
python3 -c "
import fitz
doc = fitz.open('/tmp/forge_pdf_output.pdf')
text = ''
for page in doc:
    text += page.get_text('text')
doc.close()
found = text.count('MODIFIED')
print(f'\"MODIFIED\" found {found} times in output PDF')
assert found > 0, 'No replacements found in output!'
print('PDF E2E TEST PASSED')
"
```

Expected: `PDF E2E TEST PASSED`.

- [ ] **Step 2: DOCX regression test**

```bash
echo "=== DOCX REGRESSION ==="
curl -s -X POST http://localhost:8013/analyze \
  -H "X-API-Key: ${API_KEY}" \
  -F "tenant_id=00000000-0000-0000-0000-000000000001" \
  -F "user_id=a060f046-9992-4d1a-87c4-fa5c6f8c066c" \
  -F "user_intent=renewal" \
  -F "file=@${HOME}/contrato-test-forge.docx" \
  > /tmp/forge_docx_reg.json

DSESSION=$(python3 -c "import json; print(json.load(open('/tmp/forge_docx_reg.json'))['session_id'])")
DFIELDS=$(python3 -c "import json; print(len(json.load(open('/tmp/forge_docx_reg.json')).get('fields',[])))")
echo "DOCX: ${DFIELDS} fields"

# Render with first field
DFIELD_JSON=$(python3 -c "
import json; d = json.load(open('/tmp/forge_docx_reg.json'))
f = d['fields'][0]
print(json.dumps({f['field_name']: 'REGRESSION_TEST'}))
")

curl -s -X POST http://localhost:8013/render \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"${DSESSION}\", \"field_values\": ${DFIELD_JSON}, \"output_formats\": [\"docx\"]}" \
  > /tmp/forge_docx_render_reg.json

python3 -c "
import json; d = json.load(open('/tmp/forge_docx_render_reg.json'))
assert 'docx' in d.get('outputs', {}), 'No DOCX output!'
print(f'DOCX regression: {d[\"fields_filled\"]} fields filled')
print('DOCX REGRESSION PASSED')
"
```

Expected: `DOCX REGRESSION PASSED`.
