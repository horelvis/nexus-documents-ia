"""
API endpoints for text extraction using Apache Tika.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from loguru import logger

from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.text_extraction import ExtractionResponse, HealthResponse
from app.services.text_extraction_service import (
    extraction_service,
    TextExtractionError,
)

router = APIRouter(prefix="/api/v1/text-extraction", tags=["Text Extraction"])


@router.get("/health", response_model=HealthResponse)
async def health_check(_: bool = Depends(verify_api_key)) -> HealthResponse:
    """Simple health endpoint used by orchestrators."""
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.service_version,
        backend="apache-tika",
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_text(
    file: UploadFile = File(...),
    tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
    _: bool = Depends(verify_api_key),
) -> ExtractionResponse:
    """
    Extract plain text from an uploaded document using Apache Tika.

    The endpoint accepts multipart/form-data with the file payload.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "document"
    file_size = len(contents)

    logger.info(
        "Extraction request | tenant=%s user=%s file=%s size=%s bytes",
        tenant_id or "unknown",
        user_id or "unknown",
        filename,
        file_size,
    )

    try:
        result = extraction_service.extract(
            file_bytes=contents,
            filename=filename,
        )
        logger.info(
            "Extraction completed | file=%s chars=%s language=%s",
            filename,
            result.num_characters,
            result.language or "undetected",
        )
    except TextExtractionError as exc:
        logger.warning(
            "Extraction validation error | file=%s reason=%s",
            filename,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error extracting text from %s", filename)
        raise HTTPException(status_code=500, detail="Failed to extract text") from exc

    metadata = dict(result.metadata)
    metadata.update(
        {
            "tenant_id": tenant_id or "",
            "user_id": user_id or "",
        }
    )

    return ExtractionResponse(
        success=True,
        text=result.text,
        characters=result.num_characters,
        language=result.language,
        content_type=result.content_type,
        metadata=metadata,
    )
