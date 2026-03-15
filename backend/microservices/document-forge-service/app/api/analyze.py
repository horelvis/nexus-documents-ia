"""POST /analyze — LLM-powered field detection in documents."""

import logging
from io import BytesIO

from docx import Document
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.clients.storage_client import get_storage_client
from app.clients.weaviate_client import get_weaviate_client
from app.core.config import get_settings
from app.core.security import verify_api_key
from app.schemas.analyze import AnalyzeResponse
from app.services.analyzer import get_analyzer
from app.services.pdf_extractor import (
    extract_text_from_pdf,
    extract_widgets_from_pdf,
    has_form_fields,
    widgets_to_fields,
)
from app.services.session_store import get_session_store
from app.schemas.session import SessionStatus

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract plain text from DOCX bytes."""
    doc = Document(BytesIO(docx_bytes))
    parts = []

    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    for table in doc.tables:
        for row in table.rows:
            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_texts:
                parts.append(" | ".join(row_texts))

    return "\n".join(parts)


def _extract_title_from_docx(docx_bytes: bytes, fallback: str = "document") -> str:
    """Extract document title from DOCX core properties or first heading."""
    try:
        doc = Document(BytesIO(docx_bytes))
        # Try core properties
        if doc.core_properties.title:
            return doc.core_properties.title

        # Try first heading
        for para in doc.paragraphs:
            if para.style and para.style.name and "Heading" in para.style.name:
                if para.text.strip():
                    return para.text.strip()

        # Fallback: first non-empty paragraph
        for para in doc.paragraphs:
            if para.text.strip():
                return para.text.strip()[:80]
    except Exception:
        pass
    return fallback


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


def _enrich_widget_fields(
    widget_fields: list[dict],
    llm_fields: list[dict],
    widgets: list[dict],
) -> None:
    """Enrich widget-based fields with LLM-detected labels and types.

    Matches LLM fields to widget fields by value, then applies the
    LLM's label, field_type, context_hint, and suggested_value.
    Widget fields keep their widget_name as field_name (no renaming).
    """
    # Build value → widget_field index (for filled widgets)
    value_index: dict[str, dict] = {}
    for wf in widget_fields:
        cv = (wf.get("current_value") or "").strip()
        if cv and len(cv) > 1:
            value_index[cv] = wf

    matched_widget_names: set[str] = set()

    for lf in llm_fields:
        lcv = (lf.get("current_value") or "").strip()
        target = None

        # Match by value
        if lcv and lcv in value_index:
            target = value_index[lcv]

        if target and target.get("widget_name") not in matched_widget_names:
            # Apply LLM enrichment
            if lf.get("label"):
                target["label"] = lf["label"]
            if lf.get("field_type") and target.get("field_type") != "checkbox":
                target["field_type"] = lf["field_type"]
            if lf.get("context_hint"):
                target["context_hint"] = lf["context_hint"]
            if lf.get("suggested_value"):
                target["suggested_value"] = lf["suggested_value"]
            matched_widget_names.add(target.get("widget_name", ""))
            logger.info(
                "Enriched widget %s with LLM label '%s'",
                target.get("widget_name"), lf.get("label", "")[:30],
            )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_document(
    tenant_id: str = Form(...),
    user_id: str = Form(...),
    document_id: str = Form(None),
    user_intent: str = Form("modification"),
    max_fields: int = Form(30),
    file: UploadFile | None = File(None),
    _api_key: str = Depends(verify_api_key),
):
    """Detect variable fields in a document.

    Accepts either:
    - Direct file upload (multipart)
    - document_id to fetch from storage
    """
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

    if not document_text.strip():
        raise HTTPException(status_code=422, detail="Document contains no extractable text")

    # --- PDF with AcroForms: use widgets directly as fields ---
    if source_format == "pdf" and has_form_fields(file_bytes):
        widgets = extract_widgets_from_pdf(file_bytes)
        logger.info("PDF form detected: %d widgets", len(widgets))

        # Convert widgets to fields (groups single-digit Cifras)
        fields = widgets_to_fields(widgets)
        logger.info("Converted to %d fields", len(fields))

        # Use LLM to enrich labels for the most important fields
        analyzer = get_analyzer()
        enrichment = await analyzer.analyze(
            document_text=document_text,
            document_title=title,
            user_intent=user_intent,
            max_fields=max_fields,
        )

        # Apply LLM labels/types to widget fields by matching
        llm_fields = enrichment.get("fields", [])
        _enrich_widget_fields(fields, llm_fields, widgets)

        result = {
            "document_type": enrichment.get("document_type", ""),
            "fields": fields,
            "confidence": enrichment.get("confidence", 0.0),
        }
    else:
        # --- Standard flow: LLM detects fields ---
        analyzer = get_analyzer()
        result = await analyzer.analyze(
            document_text=document_text,
            document_title=title,
            user_intent=user_intent,
            max_fields=max_fields,
        )

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

    return AnalyzeResponse(
        session_id=session.session_id,
        source_title=source_title,
        document_type=result.get("document_type", ""),
        fields=result.get("fields", []),
        confidence=result.get("confidence", 0.0),
    )
