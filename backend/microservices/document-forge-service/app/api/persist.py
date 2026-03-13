"""POST /persist — store generated document permanently in GCS + Weaviate."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_api_key
from app.schemas.session import PersistRequest, PersistResponse, SessionStatus
from app.services.session_store import get_session_store
from app.services.storage import get_storage_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/persist", response_model=PersistResponse)
async def persist_document(
    request: PersistRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Store generated document permanently in GCS and index in Weaviate."""
    store = get_session_store()
    session = await store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if session.status != SessionStatus.RENDERED:
        raise HTTPException(
            status_code=400,
            detail=f"Session must be rendered before persisting. Current: {session.status}",
        )

    # Get rendered outputs
    docx_bytes = None
    pdf_bytes = None

    if "docx" in request.persist_formats:
        docx_bytes = await store.get_blob(request.session_id, "docx")
        if not docx_bytes:
            raise HTTPException(status_code=404, detail="No DOCX output in session")

    if "pdf" in request.persist_formats:
        pdf_bytes = await store.get_blob(request.session_id, "pdf")
        if not pdf_bytes:
            logger.warning("No PDF output in session, skipping PDF persistence")

    doc_title = session.document_title or session.source_title.rsplit(".", 1)[0]

    # Persist to GCS + Weaviate
    storage = get_storage_service()
    result = await storage.persist(
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        document_title=doc_title,
        docx_bytes=docx_bytes,
        pdf_bytes=pdf_bytes,
        folder_path=request.folder_path,
        index_in_weaviate=request.index_in_weaviate,
    )

    # Update session status
    session.status = SessionStatus.PERSISTED
    await store.update_session(session)

    return PersistResponse(
        document_id=result.get("document_id"),
        gcs_paths=result.get("gcs_paths", {}),
        weaviate_indexed=result.get("weaviate_indexed", False),
        indexed_document_id=result.get("indexed_document_id"),
    )
