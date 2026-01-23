"""
API endpoints for document extraction
"""
from fastapi import APIRouter, File, Form, HTTPException, Depends, Header, UploadFile
from typing import Optional
from loguru import logger

from ..schemas.extraction import (
    ExtractionRequest,
    ExtractionResponse,
    StatsResponse,
    CategorizeRequest,
    CategorizeResponse,
    AlternativeType,
    IdentityDocumentResponse,
)
from ..services.extractor import get_extractor
from ..core.config import settings

# Conditional import for identity document service
try:
    from ..services.id_document_service import (
        id_document_service,
        IdentityDocumentType,
        IdentityExtractionResult,
    )
    ID_SERVICE_AVAILABLE = True
except ImportError:
    ID_SERVICE_AVAILABLE = False
    id_document_service = None

router = APIRouter(prefix="/api/v1/extraction", tags=["extraction"])


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> bool:
    """Verify API key for authentication"""
    if not x_api_key or x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@router.post("/extract", response_model=ExtractionResponse)
async def extract_document(
    request: ExtractionRequest,
    _: bool = Depends(verify_api_key)
) -> ExtractionResponse:
    """
    Extract structured information from document text
    
    This endpoint uses LangExtract to extract entities, relationships,
    and structured data from unstructured text.
    """
    try:
        logger.info(
            f"Extraction request for {request.document_type} document "
            f"(provider: {request.provider or 'default'})"
        )
        
        # Get extractor service
        extractor = get_extractor()
        
        # Perform extraction (document_type is now a string, not enum)
        result = await extractor.extract(
            text=request.text,
            document_type=request.document_type,
            filename=request.filename,
            provider=request.provider.value if request.provider else None
        )
        
        # Check if extraction succeeded
        if not result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Extraction failed")
            )
        
        logger.info(
            f"Extraction completed: {result['metadata']['total_extractions']} extractions found"
        )
        
        return ExtractionResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=StatsResponse)
async def get_extraction_stats(
    _: bool = Depends(verify_api_key)
) -> StatsResponse:
    """Get extraction service statistics and capabilities"""
    try:
        extractor = get_extractor()
        stats = extractor.get_extraction_stats()
        return StatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/categorize", response_model=CategorizeResponse)
async def categorize_document_type(
    request: CategorizeRequest,
    _: bool = Depends(verify_api_key)
) -> CategorizeResponse:
    """
    Detecta automáticamente el tipo de documento usando análisis inteligente del LLM.
    NO usa mapeos hardcodeados - el análisis se basa en contenido y estructura.

    Tipos soportados:
    - contract: Contratos, acuerdos legales
    - invoice: Facturas, recibos
    - report: Informes, análisis
    - nomina: Nóminas laborales
    - modelo_111: Modelo tributario 111 (IRPF trimestral)
    - modelo_190: Modelo tributario 190 (Resumen anual)
    - modelo_303: Modelo tributario 303 (IVA)
    - certificado: Certificados laborales
    - comunicacion_itss: Comunicaciones ITSS
    - correspondence: Cartas, emails
    - technical: Documentación técnica
    - legal: Documentos legales generales
    - general: Otros documentos
    """
    try:
        logger.info(f"📋 Categorizando documento: {request.filename or 'Sin nombre'}")

        extractor = get_extractor()

        # Detectar tipo de documento de forma inteligente
        result = await extractor.detect_document_type(
            text=request.text,
            filename=request.filename,
            context=request.context
        )

        if not result.get("detected_type"):
            raise HTTPException(
                status_code=500,
                detail="No se pudo detectar el tipo de documento"
            )

        logger.info(
            f"✅ Detectado: {result['detected_type']} "
            f"(confianza: {result.get('confidence', 0):.2f})"
        )

        # Construir respuesta con alternativas
        alternatives = [
            AlternativeType(type=alt["type"], confidence=alt["confidence"])
            for alt in result.get("alternative_types", [])
        ]

        # Debug: verificar visualization_html
        viz_html = result.get("visualization_html")
        logger.info(f"🔧 En endpoint: visualization_html = {viz_html is not None}")
        if viz_html:
            logger.info(f"🔧 Length: {len(viz_html)}")

        return CategorizeResponse(
            detected_type=result["detected_type"],
            confidence=result.get("confidence", 0.0),
            reasoning=result.get("reasoning", ""),
            alternative_types=alternatives,
            extractions=result.get("extractions", []),
            summary=result.get("summary", {}),
            visualization_html=viz_html  # ✅ AGREGADO
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en categorización: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/identity/health")
async def identity_service_health(
    _: bool = Depends(verify_api_key)
):
    """Check identity document extraction service health"""
    if not ID_SERVICE_AVAILABLE:
        return {
            "status": "unavailable",
            "reason": "Identity document service dependencies not installed",
            "features": {
                "doctr": False,
                "mrz_parser": False,
            },
        }

    # Check available features
    try:
        from doctr.models import ocr_predictor
        doctr_available = True
    except ImportError:
        doctr_available = False

    try:
        import mrz
        mrz_available = True
    except ImportError:
        mrz_available = False

    return {
        "status": "healthy" if doctr_available else "degraded",
        "features": {
            "doctr": doctr_available,
            "mrz_parser": mrz_available,
        },
        "supported_types": ["dni", "nie", "passport", "driver_license"],
    }


@router.post("/identity/extract", response_model=IdentityDocumentResponse)
async def extract_identity_document(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(default=None),
    consent_given: str = Form(..., description="Must be 'true' to process"),
    purpose: str = Form(default="identity_verification"),
    tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    _: bool = Depends(verify_api_key)
) -> IdentityDocumentResponse:
    """
    Extract structured data from an identity document (DNI, NIE, Passport, Driver's License).

    IMPORTANT: This endpoint processes Personally Identifiable Information (PII).
    - consent_given MUST be 'true' to proceed
    - All access is logged for GDPR compliance
    - Data is processed locally (no cloud APIs)

    Args:
        file: Image or PDF of the identity document
        document_type: Expected type (dni, nie, passport, driver_license) - auto-detected if not provided
        consent_given: User consent for PII processing (required, must be 'true')
        purpose: Purpose for processing (e.g., 'identity_verification', 'kyc')
        tenant_id: Tenant identifier for audit logging

    Returns:
        IdentityDocumentResponse with extracted data and confidence scores
    """
    if not ID_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Identity document service not available. Required dependencies not installed."
        )

    # Verify consent
    if consent_given.lower() != "true":
        raise HTTPException(
            status_code=400,
            detail="Consent is required to process identity documents. Set consent_given='true' to proceed."
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "document"
    file_size = len(contents)

    logger.info(
        f"Identity document extraction | tenant={tenant_id or 'unknown'} "
        f"file={filename} size={file_size} type={document_type or 'auto'} purpose={purpose}"
    )

    try:
        # Parse document type
        doc_type = None
        if document_type:
            try:
                doc_type = IdentityDocumentType(document_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid document_type: {document_type}. "
                    f"Supported: dni, nie, passport, driver_license"
                )

        # Extract identity data
        result = await id_document_service.extract_identity_document(
            file_bytes=contents,
            document_type=doc_type,
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
            mrz_data={
                "lines": result.mrz_lines,
                "checksum_valid": result.mrz_checksum_valid,
            } if result.mrz_lines else None,
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
        raise HTTPException(
            status_code=500,
            detail=f"Identity document extraction failed: {str(e)}"
        )
