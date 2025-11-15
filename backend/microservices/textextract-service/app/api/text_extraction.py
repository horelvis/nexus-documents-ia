"""
API endpoints for text extraction.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from loguru import logger

from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.text_extraction import (
    ExtractionResponse,
    ExtractionStrategy,
    HealthResponse,
)
from app.services.text_extraction_service import (
    extraction_service,
    TextExtractionError,
)

router = APIRouter(prefix="/api/v1/text-extraction", tags=["Text Extraction"])


@router.get("/health", response_model=HealthResponse)
async def health_check(_: bool = Depends(verify_api_key)) -> HealthResponse:
    """Simple health endpoint used by orchestrators."""
    strategies = {
        "default": settings.default_strategy,
        "supported": ", ".join(strategy.value for strategy in ExtractionStrategy),
    }
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.service_version,
        strategies=strategies,
    )


@router.post("/extract", response_model=ExtractionResponse)
async def extract_text(
    file: UploadFile = File(...),
    strategy: ExtractionStrategy = Form(ExtractionStrategy(settings.default_strategy)),
    tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    user_id: Optional[str] = Header(default=None, alias="X-User-ID"),
    _: bool = Depends(verify_api_key),
) -> ExtractionResponse:
    """
    Extract plain text from an uploaded document.

    The endpoint accepts multipart/form-data with the file payload.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "document"
    file_size = len(contents)

    logger.info(
        "📥 Solicitud de extracción | tenant=%s user=%s file=%s size=%s bytes strategy=%s",
        tenant_id or "unknown",
        user_id or "unknown",
        filename,
        file_size,
        strategy.value,
    )

    try:
        result = extraction_service.extract(
            file_bytes=contents,
            filename=filename,
            strategy=strategy.value,
        )
        logger.info(
            "✅ Extracción completada | file=%s chars=%s language=%s",
            filename,
            result.num_characters,
            result.language or "undetected",
        )
    except TextExtractionError as exc:
        logger.warning(
            "⚠️ Error de validación en extracción | file=%s reason=%s",
            filename,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("❌ Error inesperado extrayendo texto de %s", filename)
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
        metadata=metadata,
    )
