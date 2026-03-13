"""GET /sessions/{id}/* — download and info endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import verify_api_key
from app.schemas.session import ForgeSession
from app.services.session_store import get_session_store

logger = logging.getLogger(__name__)
router = APIRouter()

MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


@router.get("/sessions/{session_id}/download")
async def download_document(
    session_id: str,
    format: str = Query("docx", regex="^(docx|pdf)$"),
    _api_key: str = Depends(verify_api_key),
):
    """Download a generated document from the session cache."""
    store = get_session_store()
    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    blob = await store.get_blob(session_id, format)
    if not blob:
        raise HTTPException(
            status_code=404,
            detail=f"No {format.upper()} output found for this session",
        )

    title = session.document_title or session.source_title.rsplit(".", 1)[0]
    filename = f"{title}.{format}"

    return Response(
        content=blob,
        media_type=MIME_TYPES.get(format, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sessions/{session_id}/info", response_model=ForgeSession)
async def session_info(
    session_id: str,
    _api_key: str = Depends(verify_api_key),
):
    """Get session metadata (fields, status, timestamps)."""
    store = get_session_store()
    session = await store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session
