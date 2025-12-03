"""
API endpoints for document extraction
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from loguru import logger

from ..schemas.extraction import (
    ExtractionRequest,
    ExtractionResponse,
    StatsResponse,
    CategorizeRequest,
    CategorizeResponse,
    AlternativeType
)
from ..services.extractor import get_extractor
from ..core.config import settings

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
        logger.error(f"❌ Error en categorización: {e}")
        raise HTTPException(status_code=500, detail=str(e))
