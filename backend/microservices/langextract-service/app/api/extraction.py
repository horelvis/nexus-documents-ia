"""
API endpoints for document extraction
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from loguru import logger

from ..schemas.extraction import (
    ExtractionRequest,
    ExtractionResponse,
    StatsResponse
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
        
        # Perform extraction
        result = await extractor.extract(
            text=request.text,
            document_type=request.document_type.value,
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
