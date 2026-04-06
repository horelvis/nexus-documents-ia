"""
REST endpoints for TrustGraph triple extraction and structural indexing.

Router prefix: /extract
"""

import logging

from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.services.falkordb_client import falkordb_client
from app.services.triple_store import TripleStore
from app.services.extractors.coordinator import ExtractionCoordinator
from app.schemas.triples import (
    StructuralIndexRequest,
    StructuralIndexResponse,
    TripleExtractionRequest,
    TripleExtractionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/extract",
    tags=["extraction"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/triples", response_model=TripleExtractionResponse)
async def extract_triples(request: TripleExtractionRequest) -> TripleExtractionResponse:
    """Extract and store triples from document chunks via LLM extractors."""
    coordinator = ExtractionCoordinator(falkordb_client)

    result = await coordinator.extract_document(
        chunks=request.chunks,
        document_id=request.document_id,
        user=request.tenant_id,
        collection=request.collection,
        title=request.title,
        file_path=request.file_path,
        semantic_type=request.semantic_type,
        domain=request.domain,
    )

    return TripleExtractionResponse(
        success=result.get("success", True),
        document_uri=result.get("document_uri", ""),
        triples_created=result.get("triples_created", 0),
        contradictions_found=result.get("contradictions_found", 0),
        extraction_time_ms=result.get("extraction_time_ms", 0),
        errors=result.get("errors", []),
    )


@router.post("/structural", response_model=StructuralIndexResponse)
async def structural_index(request: StructuralIndexRequest) -> StructuralIndexResponse:
    """Create a document :Node with structural metadata (no LLM extraction)."""
    ts = TripleStore(falkordb_client)

    document_uri = await ts.store_document_node(
        document_id=request.document_id,
        user=request.tenant_id,
        collection=request.collection,
        title=request.title,
        file_path=request.file_path,
        semantic_type=request.semantic_type,
        domain=request.domain,
    )

    return StructuralIndexResponse(success=True, document_uri=document_uri)
