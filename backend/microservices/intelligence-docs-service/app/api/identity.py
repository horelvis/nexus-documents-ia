"""
Identity document extraction endpoints.

Extracts structured data from DNI, NIE, Passport, and Driver's License
documents using local OCR (doctr) + MRZ parsing.

GDPR: All processing is local (no cloud APIs). Consent required.
"""
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/identity", tags=["identity"])

# Lazy imports — doctr is heavy (~500MB), only load when needed
_ID_SERVICE = None
_ID_SERVICE_AVAILABLE: Optional[bool] = None


def _get_id_service():
    global _ID_SERVICE, _ID_SERVICE_AVAILABLE
    if _ID_SERVICE_AVAILABLE is None:
        try:
            from app.services.id_document_service import id_document_service
            _ID_SERVICE = id_document_service
            _ID_SERVICE_AVAILABLE = True
        except ImportError:
            _ID_SERVICE_AVAILABLE = False
    return _ID_SERVICE


class IdentityDocumentResponse(BaseModel):
    success: bool
    document_type: str
    issuing_country: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    document_number: Optional[str] = None
    date_of_birth: Optional[str] = None
    expiration_date: Optional[str] = None
    nationality: Optional[str] = None
    gender: Optional[str] = None
    mrz_data: Optional[dict] = None
    license_categories: Optional[list[str]] = None
    confidence_score: float
    field_confidences: dict[str, float] = {}
    ocr_engine: str = "doctr"
    processing_time_ms: float = 0.0
    is_valid: bool = False
    validation_errors: list[str] = []
    warnings: list[str] = []


@router.get("/health")
async def identity_health():
    svc = _get_id_service()
    if svc is None:
        return {
            "status": "unavailable",
            "reason": "Identity document dependencies not installed (doctr)",
        }

    doctr_available = False
    mrz_available = False
    try:
        from doctr.models import ocr_predictor  # noqa: F401
        doctr_available = True
    except ImportError:
        pass
    try:
        import mrz  # noqa: F401
        mrz_available = True
    except ImportError:
        pass

    return {
        "status": "healthy" if doctr_available else "degraded",
        "features": {"doctr": doctr_available, "mrz_parser": mrz_available},
        "supported_types": ["dni", "nie", "passport", "driver_license"],
    }


@router.post("/extract", response_model=IdentityDocumentResponse)
async def extract_identity_document(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(default=None),
    consent_given: str = Form(..., description="Must be 'true' to process"),
    purpose: str = Form(default="identity_verification"),
):
    svc = _get_id_service()
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail="Identity document service not available. Required dependencies not installed.",
        )

    if consent_given.lower() != "true":
        raise HTTPException(
            status_code=400,
            detail="Consent is required to process identity documents. Set consent_given='true'.",
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    logger.info(
        f"Identity extraction | file={file.filename or 'document'} "
        f"size={len(contents)} type={document_type or 'auto'} purpose={purpose}"
    )

    try:
        from app.services.id_document_service import IdentityDocumentType

        doc_type = None
        if document_type:
            try:
                doc_type = IdentityDocumentType(document_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid document_type: {document_type}. "
                    f"Supported: dni, nie, passport, driver_license",
                )

        result = await svc.extract_identity_document(
            file_bytes=contents, document_type=doc_type,
        )

        logger.info(
            f"Identity extraction completed | type={result.document_type.value} "
            f"confidence={result.confidence_score:.2f} valid={result.is_valid}"
        )

        return IdentityDocumentResponse(
            success=result.is_valid or result.confidence_score > 0.5,
            document_type=result.document_type.value,
            issuing_country=result.issuing_country,
            full_name=result.full_name,
            first_name=result.first_name,
            last_name=result.last_name,
            document_number=result.document_number,
            date_of_birth=result.date_of_birth.isoformat() if result.date_of_birth else None,
            expiration_date=result.expiration_date.isoformat() if result.expiration_date else None,
            nationality=result.nationality,
            gender=result.gender,
            mrz_data={"lines": result.mrz_lines, "checksum_valid": result.mrz_checksum_valid}
            if result.mrz_lines else None,
            license_categories=result.license_categories or None,
            confidence_score=result.confidence_score,
            field_confidences=result.field_confidences,
            ocr_engine=result.ocr_engine,
            processing_time_ms=result.processing_time_ms,
            is_valid=result.is_valid,
            validation_errors=result.validation_errors,
            warnings=result.warnings,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Identity extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Identity extraction failed: {e}")
