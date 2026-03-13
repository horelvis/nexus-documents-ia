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
    docx_bytes: bytes | None = None
    source_title = "document"

    # Path 1: Direct upload
    if file is not None:
        content = await file.read()
        if len(content) > settings.max_document_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {settings.max_document_size_mb}MB limit",
            )
        docx_bytes = content
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
        docx_bytes = await storage.download_document(file_path, tenant_id)
        if not docx_bytes:
            raise HTTPException(status_code=404, detail="Could not download document")
    else:
        raise HTTPException(
            status_code=400, detail="Provide either a file upload or document_id"
        )

    # Extract text from DOCX
    try:
        document_text = _extract_text_from_docx(docx_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse DOCX: {e}",
        )

    if not document_text.strip():
        raise HTTPException(status_code=422, detail="Document contains no extractable text")

    # Try to get a better title
    title = _extract_title_from_docx(docx_bytes, source_title)

    # LLM analysis
    analyzer = get_analyzer()
    result = await analyzer.analyze(
        document_text=document_text,
        document_title=title,
        user_intent=user_intent,
        max_fields=max_fields,
    )

    # Create session and store source DOCX
    store = get_session_store()
    session = await store.create_session(tenant_id, user_id)
    session.source_title = source_title
    session.document_type = result.get("document_type", "")
    session.fields = result.get("fields", [])
    session.confidence = result.get("confidence", 0.0)
    session.status = SessionStatus.ANALYZED
    await store.update_session(session)

    # Store original DOCX bytes for later preparation
    await store.store_blob(session.session_id, "source", docx_bytes)

    return AnalyzeResponse(
        session_id=session.session_id,
        source_title=source_title,
        document_type=result.get("document_type", ""),
        fields=result.get("fields", []),
        confidence=result.get("confidence", 0.0),
    )
