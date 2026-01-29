"""Upload endpoints for temporary document context (non-indexed)."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile

from app.core.security import verify_api_key
from app.services.upload_context_service import upload_context_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/uploads/temp")
async def upload_temp_document(
    file: UploadFile = File(...),
    tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
    _: bool = Depends(verify_api_key),
):
    if not tenant_id or not user_id:
        raise HTTPException(status_code=400, detail="Missing tenant_id or user_id")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "document"
    content_type = file.content_type or "application/octet-stream"

    try:
        payload = await upload_context_service.save_upload(
            tenant_id=tenant_id,
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
        )
    except Exception as exc:
        logger.error("Temp upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to extract uploaded document") from exc

    return {
        "upload_id": payload.get("id"),
        "filename": payload.get("filename"),
        "characters": payload.get("characters"),
    }
