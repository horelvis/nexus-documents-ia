"""
Claims API — Phase 3 GraphRAG Enhancement

Endpoints for querying and extracting structured claims from documents.
Claims are stored in FalkorDB as :Claim nodes linked to :Document and :Entity
nodes via :EXTRACTED_FROM, :ABOUT, and :CONTRADICTS edges.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.services.claim_extractor import claim_extractor
from app.services.falkordb_client import falkordb_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claims", tags=["claims"])


# --- Request/Response Models ---

class ClaimItem(BaseModel):
    claim_id: str = ""
    statement: str = ""
    claim_type: str = ""
    confidence: float = 0.0
    source_chunk: str = ""
    verified: bool = False


class ClaimsListResponse(BaseModel):
    document_id: str
    claims: List[ClaimItem] = Field(default_factory=list)
    total: int = 0


class ContradictionItem(BaseModel):
    claim1_id: str = ""
    claim1_statement: str = ""
    claim1_confidence: float = 0.0
    claim2_id: str = ""
    claim2_statement: str = ""
    claim2_confidence: float = 0.0
    contradiction_type: str = ""
    document_id: str = ""


class ContradictionsResponse(BaseModel):
    contradictions: List[ContradictionItem] = Field(default_factory=list)
    total: int = 0


class ExtractClaimsRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")
    document_id: str = Field(..., description="Document identifier")
    text: str = Field(..., description="Document text to extract claims from")
    domain: str = Field("", description="Document domain (e.g. 'legal')")
    semantic_type: str = Field("", description="Document semantic type (e.g. 'contrato')")


class ExtractClaimsResponse(BaseModel):
    success: bool
    claims_created: int = 0
    claims: List[ClaimItem] = Field(default_factory=list)


# --- Endpoints ---

@router.get("", response_model=ClaimsListResponse)
async def list_claims(
    tenant_id: str = Query(..., description="Tenant identifier"),
    document_id: str = Query(..., description="Document identifier"),
    claim_type: Optional[str] = Query(None, description="Filter by claim type"),
    _: bool = Depends(verify_api_key),
):
    """List claims extracted from a document."""
    await falkordb_client.initialize()

    type_filter = ""
    if claim_type:
        type_filter = "AND c.claim_type = $claim_type"

    cypher = f"""
        MATCH (c:Claim {{tenant_id: $tenant_id}})-[:EXTRACTED_FROM]->(d:Document {{document_id: $document_id}})
        WHERE d.tenant_id = $tenant_id {type_filter}
        RETURN c.claim_id AS claim_id,
               c.statement AS statement,
               c.claim_type AS claim_type,
               c.confidence AS confidence,
               c.source_chunk AS source_chunk,
               c.verified AS verified
        ORDER BY c.confidence DESC
    """

    params: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "document_id": document_id,
    }
    if claim_type:
        params["claim_type"] = claim_type

    try:
        rows = await falkordb_client.execute_cypher(cypher, params)
    except Exception as e:
        logger.error(f"Failed to list claims: {e}")
        return ClaimsListResponse(document_id=document_id)

    claims = [
        ClaimItem(
            claim_id=row.get("claim_id") or "",
            statement=row.get("statement") or "",
            claim_type=row.get("claim_type") or "",
            confidence=row.get("confidence") or 0.0,
            source_chunk=row.get("source_chunk") or "",
            verified=bool(row.get("verified")),
        )
        for row in rows
    ]

    return ClaimsListResponse(
        document_id=document_id,
        claims=claims,
        total=len(claims),
    )


@router.get("/contradictions", response_model=ContradictionsResponse)
async def list_contradictions(
    tenant_id: str = Query(..., description="Tenant identifier"),
    document_id: Optional[str] = Query(None, description="Filter by document"),
    _: bool = Depends(verify_api_key),
):
    """List all contradictions between claims.

    Returns pairs of claims linked by :CONTRADICTS edges, optionally
    scoped to a specific document.
    """
    await falkordb_client.initialize()

    doc_filter = ""
    if document_id:
        doc_filter = "AND d1.document_id = $document_id"

    cypher = f"""
        MATCH (c1:Claim {{tenant_id: $tenant_id}})-[r:CONTRADICTS]->(c2:Claim {{tenant_id: $tenant_id}})
        MATCH (c1)-[:EXTRACTED_FROM]->(d1:Document)
        {f'WHERE d1.document_id = $document_id' if document_id else ''}
        RETURN c1.claim_id AS c1_id,
               c1.statement AS c1_stmt,
               c1.confidence AS c1_conf,
               c2.claim_id AS c2_id,
               c2.statement AS c2_stmt,
               c2.confidence AS c2_conf,
               r.contradiction_type AS contra_type,
               d1.document_id AS doc_id
        ORDER BY c1.confidence DESC
    """

    params: Dict[str, Any] = {"tenant_id": tenant_id}
    if document_id:
        params["document_id"] = document_id

    try:
        rows = await falkordb_client.execute_cypher(cypher, params)
    except Exception as e:
        logger.error(f"Failed to list contradictions: {e}")
        return ContradictionsResponse()

    items = [
        ContradictionItem(
            claim1_id=row.get("c1_id") or "",
            claim1_statement=row.get("c1_stmt") or "",
            claim1_confidence=row.get("c1_conf") or 0.0,
            claim2_id=row.get("c2_id") or "",
            claim2_statement=row.get("c2_stmt") or "",
            claim2_confidence=row.get("c2_conf") or 0.0,
            contradiction_type=row.get("contra_type") or "",
            document_id=row.get("doc_id") or "",
        )
        for row in rows
    ]

    return ContradictionsResponse(
        contradictions=items,
        total=len(items),
    )


@router.post("/extract", response_model=ExtractClaimsResponse)
async def extract_claims(
    request: ExtractClaimsRequest,
    _: bool = Depends(verify_api_key),
):
    """Manually trigger claim extraction for a document.

    Extracts structured claims from the provided text using regex
    patterns and stores them in the knowledge graph.
    """
    try:
        claims = await claim_extractor.extract_claims(
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            text=request.text,
            domain=request.domain,
            semantic_type=request.semantic_type,
        )
    except Exception as e:
        logger.error(f"Claim extraction failed: {e}")
        return ExtractClaimsResponse(success=False)

    claim_items = [
        ClaimItem(
            claim_id=c.get("claim_id", ""),
            statement=c.get("statement", ""),
            claim_type=c.get("claim_type", ""),
            confidence=c.get("confidence", 0.0),
        )
        for c in claims
    ]

    return ExtractClaimsResponse(
        success=True,
        claims_created=len(claims),
        claims=claim_items,
    )
