"""Document Forge API endpoints

Proxy router for document-forge-service (template-based document generation).
Follows the same pattern as emma.py for consistency.
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

FORGE_SERVICE_URL = settings.DOCUMENT_FORGE_SERVICE_URL.rstrip("/")


def _check_enabled():
    """Raise 503 if Document Forge is disabled."""
    if not settings.DOCUMENT_FORGE_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Document Forge service is disabled",
        )


@router.post("/analyze")
async def forge_analyze(
    current_user: UserProfile = Depends(get_current_user_async),
    document_id: Optional[str] = Form(None),
    user_intent: str = Form("modification"),
    max_fields: int = Form(30),
    file: Optional[UploadFile] = File(None),
):
    """
    Analyze a document to detect variable fields.

    Accepts either a direct file upload (multipart) or a document_id
    to fetch from storage. Proxies to document-forge-service.
    """
    _check_enabled()
    try:
        # Build multipart form data for the forge service
        form_data = {
            "user_id": current_user.sub,
            "user_intent": user_intent,
            "max_fields": str(max_fields),
        }
        if document_id:
            form_data["document_id"] = document_id

        files = None
        if file is not None:
            file_bytes = await file.read()
            if not file_bytes:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            files = {"file": (file.filename or "document", file_bytes, file.content_type)}

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(
                f"{FORGE_SERVICE_URL}/analyze",
                data=form_data,
                files=files,
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"Forge analyze error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forge analyze proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/render")
async def forge_render(
    request: Request,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Render a document with field values.

    Fills detected fields with provided values and generates DOCX/PDF output.
    Proxies to document-forge-service. Rewrites download_url paths to Main API.
    """
    _check_enabled()
    try:
        body = await request.json()
        body["user_id"] = current_user.sub

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(
                f"{FORGE_SERVICE_URL}/render",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                logger.error(f"Forge render error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)

            result = response.json()

            # Rewrite download_url from forge-relative paths to Main API paths
            # e.g. /sessions/abc/download?format=docx -> /api/v1/forge/sessions/abc/download?format=docx
            outputs = result.get("outputs", {})
            for fmt, info in outputs.items():
                if isinstance(info, dict) and "download_url" in info:
                    original = info["download_url"]
                    if original.startswith("/sessions/"):
                        info["download_url"] = f"/api/v1/forge{original}"

            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forge render proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/persist")
async def forge_persist(
    request: Request,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Persist a rendered document permanently to GCS and optionally index in Weaviate.

    Proxies to document-forge-service.
    """
    _check_enabled()
    try:
        body = await request.json()
        body["user_id"] = current_user.sub

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                f"{FORGE_SERVICE_URL}/persist",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY or "",
                },
            )
            if response.status_code != 200:
                logger.error(f"Forge persist error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forge persist proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/info")
async def forge_session_info(
    session_id: str,
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Get session metadata (fields, status, timestamps).

    Proxies to document-forge-service.
    """
    _check_enabled()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                f"{FORGE_SERVICE_URL}/sessions/{session_id}/info",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"Forge session info error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forge session info proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/download")
async def forge_session_download(
    session_id: str,
    format: str = "docx",
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Download a generated document (DOCX or PDF) from a forge session.

    Proxies to document-forge-service and streams bytes back.
    """
    _check_enabled()
    if format not in ("docx", "pdf"):
        raise HTTPException(status_code=400, detail="format must be 'docx' or 'pdf'")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(
                f"{FORGE_SERVICE_URL}/sessions/{session_id}/download",
                params={"format": format},
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY or ""},
            )
            if response.status_code != 200:
                logger.error(f"Forge download error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)

            return Response(
                content=response.content,
                media_type=response.headers.get("content-type", "application/octet-stream"),
                headers={
                    k: v for k, v in response.headers.items()
                    if k.lower() in ("content-disposition",)
                },
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forge download proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
