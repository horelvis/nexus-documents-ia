"""
API endpoints for text extraction using Apache Tika and OCR.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from loguru import logger

from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.text_extraction import ExtractionResponse, HealthResponse, OCRResponse
from app.services.text_extraction_service import (
    extraction_service,
    TextExtractionError,
)

# Conditional import for OCR service
try:
    from app.services.ocr_service import ocr_service, OCRResult
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    ocr_service = None

router = APIRouter(prefix="/api/v1/text-extraction", tags=["Text Extraction"])


@router.get("/health", response_model=HealthResponse)
async def health_check(_: bool = Depends(verify_api_key)) -> HealthResponse:
    """Simple health endpoint used by orchestrators."""
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.service_version,
        backend=extraction_service.primary_backend_name,
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

    Note: MIME type is automatically detected from file content (magic bytes),
    NOT from the filename extension. This handles misleading filenames like
    "GESTOR.docx.pdf" correctly.
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


@router.get("/ocr/health")
async def ocr_health_check(_: bool = Depends(verify_api_key)):
    """Check OCR service health and availability."""
    if not OCR_AVAILABLE:
        return {
            "status": "unavailable",
            "reason": "OCR dependencies not installed",
            "engines": {
                "easyocr": False,
                "tesseract": False,
            },
        }

    # Check available OCR engines
    try:
        import easyocr
        easyocr_available = True
    except ImportError:
        easyocr_available = False

    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        tesseract_available = True
    except Exception:
        tesseract_available = False

    return {
        "status": "healthy" if (easyocr_available or tesseract_available) else "degraded",
        "service": settings.service_name,
        "engines": {
            "easyocr": easyocr_available,
            "tesseract": tesseract_available,
        },
    }


@router.post("/ocr", response_model=OCRResponse)
async def extract_with_ocr(
    file: UploadFile = File(...),
    languages: str = Form(default="es,en"),
    use_hybrid: str = Form(default="false"),
    preprocess: str = Form(default="true"),
    dpi: int = Form(default=300),
    tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    _: bool = Depends(verify_api_key),
) -> OCRResponse:
    """
    Extract text using enhanced OCR (EasyOCR/Tesseract).

    Use this endpoint when standard Tika extraction produces low-quality results,
    typically for scanned PDFs or image-based documents.

    Args:
        file: PDF or image file to process
        languages: Comma-separated language codes (e.g., "es,en")
        use_hybrid: Use both EasyOCR and Tesseract for best results
        preprocess: Apply image preprocessing (contrast, sharpening)
        dpi: DPI for PDF to image conversion (higher = better quality, slower)
        tenant_id: Tenant identifier for logging

    Returns:
        OCRResponse with extracted text and confidence score
    """
    if not OCR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="OCR service not available. Required dependencies not installed."
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "document"
    file_size = len(contents)

    # Parse parameters
    lang_list = [l.strip() for l in languages.split(",") if l.strip()]
    hybrid_mode = use_hybrid.lower() == "true"
    preprocess_mode = preprocess.lower() != "false"

    logger.info(
        "OCR request | tenant=%s file=%s size=%s bytes languages=%s hybrid=%s dpi=%s",
        tenant_id or "unknown",
        filename,
        file_size,
        lang_list,
        hybrid_mode,
        dpi,
    )

    try:
        # Determine if it's a PDF or image
        is_pdf = filename.lower().endswith('.pdf') or contents[:4] == b'%PDF'

        if is_pdf:
            result = await ocr_service.extract_from_pdf(
                pdf_bytes=contents,
                languages=lang_list,
                use_hybrid=hybrid_mode,
            )
        else:
            result = await ocr_service.extract_from_image(
                image_bytes=contents,
                languages=lang_list,
            )

        logger.info(
            "OCR completed | file=%s chars=%s confidence=%.2f engine=%s pages=%s",
            filename,
            len(result.text),
            result.confidence,
            result.engine.value if hasattr(result.engine, 'value') else result.engine,
            result.page_count,
        )

        return OCRResponse(
            success=result.success,
            text=result.text,
            confidence=result.confidence,
            engine=result.engine.value if hasattr(result.engine, 'value') else str(result.engine),
            languages=result.languages,
            page_count=result.page_count,
            processing_time_ms=result.processing_time_ms,
            warnings=result.warnings,
        )

    except Exception as exc:
        logger.exception("OCR extraction failed | file=%s error=%s", filename, exc)
        raise HTTPException(
            status_code=500,
            detail=f"OCR extraction failed: {str(exc)}"
        ) from exc
