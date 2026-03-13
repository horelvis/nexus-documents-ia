"""
Legal Knowledge Graph API — Proxy to knowledge-tree-service

All legal graph operations are now handled by knowledge-tree-service.
This module proxies requests to maintain backwards compatibility for
existing clients while the consolidation is in progress.

Once all clients are updated to call knowledge-tree-service directly,
this proxy can be removed.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
import logging

from app.core.security import verify_api_key
from app.clients.knowledge_tree_client import knowledge_tree_legal_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legal", tags=["legal-knowledge-graph"])


# =============================================================================
# Schemas
# =============================================================================

class LegalDomainEnum(str, Enum):
    """Legal domains for categorizing laws."""
    LABOR = "labor"
    FISCAL = "fiscal"
    PRIVACY = "privacy"
    CIVIL = "civil"
    MERCANTILE = "mercantile"
    ADMINISTRATIVE = "administrative"
    COMPLIANCE = "compliance"
    IP = "intellectual_property"
    COMMERCE = "commerce"
    REAL_ESTATE = "real_estate"
    EDUCATION = "education"
    GENERAL = "general"


class LawStatusEnum(str, Enum):
    """Status of a law."""
    VIGENTE = "vigente"
    DEROGADA = "derogada"
    PARCIALMENTE_DEROGADA = "parcialmente_derogada"
    PENDIENTE = "pendiente"


class LawCreateRequest(BaseModel):
    """Request to create a law."""
    boe_id: str = Field(..., description="BOE identifier (e.g., BOE-A-2015-11430)")
    title: str = Field(..., description="Full title of the law")
    short_name: str = Field(..., description="Short name (e.g., ET, RGPD)")
    domain: LegalDomainEnum = Field(..., description="Legal domain")
    status: LawStatusEnum = Field(LawStatusEnum.VIGENTE, description="Law status")
    publication_date: Optional[str] = Field(None, description="Publication date (ISO format)")
    effective_date: Optional[str] = Field(None, description="Effective date (ISO format)")
    eli_uri: Optional[str] = Field(None, description="European Legislation Identifier URI")
    summary: Optional[str] = Field(None, description="Brief summary of the law")
    keywords: List[str] = Field(default_factory=list, description="Keywords for search")


class LawResponse(BaseModel):
    """Response model for a law."""
    boe_id: str
    title: str
    short_name: str
    domain: str
    status: str
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    eli_uri: Optional[str] = None
    summary: Optional[str] = None
    keywords: List[str] = []
    weaviate_uuid: Optional[str] = None  # Link to PublicKnowledge document


class ArticleCreateRequest(BaseModel):
    """Request to create an article."""
    article_number: str = Field(..., description="Article number (e.g., 34, 31bis)")
    title: Optional[str] = Field(None, description="Article title")
    summary: Optional[str] = Field(None, description="Brief summary (NOT full text)")
    key_concepts: List[str] = Field(default_factory=list, description="Key concepts covered")


class ArticleResponse(BaseModel):
    """Response model for an article."""
    article_id: str
    law_boe_id: str
    article_number: str
    title: Optional[str] = None
    summary: Optional[str] = None
    key_concepts: List[str] = []
    is_derogated: bool = False


class DocumentLawLinkRequest(BaseModel):
    """Request to link a document to a law."""
    law_boe_id: str = Field(..., description="BOE ID of the applicable law")
    relationship_type: str = Field("governed_by", description="Type of relationship")
    articles: List[str] = Field(default_factory=list, description="Specific articles that apply")


class LegalGraphStats(BaseModel):
    """Statistics about the legal knowledge graph."""
    total_laws: int
    total_articles: int
    laws_by_domain: dict


# =============================================================================
# API Endpoints
# =============================================================================

def _to_law_response(law: dict) -> LawResponse:
    return LawResponse(
        boe_id=law.get("boe_id", ""),
        title=law.get("title", ""),
        short_name=law.get("short_name", ""),
        domain=law.get("domain", ""),
        status=law.get("status", "vigente"),
        publication_date=law.get("publication_date"),
        effective_date=law.get("effective_date"),
        eli_uri=law.get("eli_uri"),
        summary=law.get("summary"),
        keywords=law.get("keywords", []),
        weaviate_uuid=law.get("weaviate_uuid"),
    )


# All endpoints proxy to knowledge-tree-service via HTTP client

@router.get("/laws", response_model=List[LawResponse])
async def list_laws(
    domain: Optional[LegalDomainEnum] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List all laws (proxied to knowledge-tree-service)."""
    try:
        if domain:
            laws = await knowledge_tree_legal_client.get_laws_by_domain(domain.value)
        else:
            laws = await knowledge_tree_legal_client.get_all_laws()
        return [_to_law_response(law) for law in laws[:limit]]
    except Exception as e:
        logger.error(f"Failed to list laws: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws/{boe_id}", response_model=LawResponse)
async def get_law(boe_id: str):
    """Get a specific law by BOE ID."""
    law = await knowledge_tree_legal_client.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")
    return _to_law_response(law)


@router.get("/laws/domain/{domain}", response_model=List[LawResponse])
async def get_laws_by_domain(domain: LegalDomainEnum):
    """Get all laws for a specific domain."""
    laws = await knowledge_tree_legal_client.get_laws_by_domain(domain.value)
    return [_to_law_response(law) for law in laws]


@router.post("/laws", response_model=LawResponse)
async def create_law(
    request: LawCreateRequest,
    api_key: str = Depends(verify_api_key),
):
    """Add a new law (proxied to knowledge-tree-service)."""
    try:
        law_data = request.model_dump()
        law_data["domain"] = request.domain.value
        law_data["status"] = request.status.value
        success = await knowledge_tree_legal_client.add_law(law_data)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add law")
        return LawResponse(**{k: v for k, v in law_data.items() if k in LawResponse.model_fields})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create law: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws/{boe_id}/articles")
async def get_articles_for_law(boe_id: str):
    """Get all articles for a specific law."""
    law = await knowledge_tree_legal_client.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")
    # Proxy to knowledge-tree-service
    try:
        return await knowledge_tree_legal_client._request("GET", f"/legal/laws/{boe_id}/articles")
    except Exception:
        return []


@router.post("/laws/{boe_id}/articles")
async def create_article(
    boe_id: str,
    request: ArticleCreateRequest,
    api_key: str = Depends(verify_api_key),
):
    """Add an article to a law."""
    law = await knowledge_tree_legal_client.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")
    try:
        return await knowledge_tree_legal_client._request(
            "POST", f"/legal/laws/{boe_id}/articles",
            json=request.model_dump(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{document_id}/link-law")
async def link_document_to_law(
    document_id: str,
    request: DocumentLawLinkRequest,
    tenant_id: str = Query(...),
    api_key: str = Depends(verify_api_key),
):
    """Link a document to an applicable law."""
    success = await knowledge_tree_legal_client.link_document_to_law(
        document_id=document_id,
        law_boe_id=request.law_boe_id,
        tenant_id=tenant_id,
        relationship_type=request.relationship_type,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to link document to law")
    return {"success": True, "document_id": document_id, "law_boe_id": request.law_boe_id}


@router.get("/documents/{document_id}/applicable-laws", response_model=List[LawResponse])
async def get_applicable_laws(
    document_id: str,
    tenant_id: str = Query(...),
):
    """Get all laws applicable to a document."""
    laws = await knowledge_tree_legal_client.get_applicable_laws(document_id, tenant_id)
    return [_to_law_response(law) for law in laws]


@router.get("/suggest-laws")
async def suggest_applicable_laws(
    document_type: str = Query(...),
    domain: Optional[str] = Query(None),
):
    """Suggest laws that might apply to a document type."""
    laws = await knowledge_tree_legal_client.get_laws_by_domain(domain or "general")
    return {
        "document_type": document_type,
        "domain": domain,
        "suggested_laws": [
            {"boe_id": law.get("boe_id", ""), "short_name": law.get("short_name", ""),
             "title": law.get("title", ""), "domain": law.get("domain", "")}
            for law in laws
        ],
    }


@router.get("/graph/structure")
async def get_legal_graph_structure():
    """Get full legal graph structure for D3 visualization."""
    try:
        return await knowledge_tree_legal_client.get_graph_structure()
    except Exception as e:
        logger.error(f"Failed to get legal graph structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/enriched")
async def get_enriched_legal_graph():
    """Get enriched graph with domain clusters and metrics."""
    try:
        return await knowledge_tree_legal_client.get_enriched_graph_structure()
    except Exception as e:
        logger.error(f"Failed to get enriched legal graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/search")
async def search_legal_graph(
    q: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    boe_id: Optional[str] = Query(None),
    include_neighbors: bool = Query(True),
    limit: int = Query(20, ge=1, le=100),
):
    """Search the legal graph (proxied, filtering done server-side)."""
    try:
        structure = await knowledge_tree_legal_client.get_graph_structure()
        nodes = structure.get("nodes", [])
        edges = structure.get("edges", [])

        if not nodes:
            return {"nodes": [], "edges": [], "query": {"q": q, "domain": domain, "boe_id": boe_id}}

        matched_ids = set()
        if boe_id:
            matched_ids.update(n["id"] for n in nodes if n.get("id") == boe_id)
        if domain:
            dl = domain.lower()
            matched_ids.update(n["id"] for n in nodes if n.get("domain", "").lower() == dl)
        if q:
            ql = q.lower()
            matched_ids.update(
                n["id"] for n in nodes
                if ql in n.get("id", "").lower() or ql in n.get("label", "").lower() or ql in n.get("title", "").lower()
            )
        if not q and not domain and not boe_id:
            matched_ids = {n["id"] for n in nodes[:limit]}
        if include_neighbors and matched_ids:
            for e in edges:
                if e.get("source") in matched_ids:
                    matched_ids.add(e["target"])
                if e.get("target") in matched_ids:
                    matched_ids.add(e["source"])
        matched_ids = set(list(matched_ids)[:limit])

        return {
            "nodes": [n for n in nodes if n.get("id") in matched_ids],
            "edges": [e for e in edges if e.get("source") in matched_ids and e.get("target") in matched_ids],
            "query": {"q": q, "domain": domain, "boe_id": boe_id, "matched_count": len(matched_ids)},
        }
    except Exception as e:
        logger.error(f"Failed to search legal graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_legal_graph_stats():
    """Get statistics about the legal knowledge graph."""
    stats = await knowledge_tree_legal_client.get_stats()
    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])
    return stats
