"""
API endpoints for Legal Knowledge Graph

Provides access to the legal knowledge graph for:
- Managing laws (add, get, list)
- Managing articles (add, get by law)
- Linking documents to applicable laws
- Querying legal applicability

Endpoints:
- GET /legal/laws - List all laws
- GET /legal/laws/{boe_id} - Get a specific law
- GET /legal/laws/domain/{domain} - Get laws by domain
- POST /legal/laws - Add a new law (admin only)
- GET /legal/laws/{boe_id}/articles - Get articles for a law
- POST /legal/laws/{boe_id}/articles - Add an article to a law
- POST /legal/documents/{doc_id}/link-law - Link document to law
- GET /legal/documents/{doc_id}/applicable-laws - Get applicable laws
- GET /legal/stats - Get legal graph statistics
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
import logging

from app.core.security import verify_api_key

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

@router.get("/laws", response_model=List[LawResponse])
async def list_laws(
    domain: Optional[LegalDomainEnum] = Query(None, description="Filter by domain"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
):
    """
    List all laws in the legal knowledge graph.

    Optionally filter by domain.
    """
    from app.services.sil.legal_graph_service import legal_graph, LegalDomain

    try:
        if domain:
            laws = await legal_graph.get_laws_by_domain(LegalDomain(domain.value))
        else:
            laws = await legal_graph.get_all_laws()

        return [
            LawResponse(
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
            for law in laws[:limit]
        ]

    except Exception as e:
        logger.error(f"Failed to list laws: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws/{boe_id}", response_model=LawResponse)
async def get_law(boe_id: str):
    """Get a specific law by BOE ID."""
    from app.services.sil.legal_graph_service import legal_graph

    law = await legal_graph.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")

    return LawResponse(
        boe_id=law.get("boe_id", boe_id),
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


@router.get("/laws/domain/{domain}", response_model=List[LawResponse])
async def get_laws_by_domain(domain: LegalDomainEnum):
    """Get all laws for a specific domain."""
    from app.services.sil.legal_graph_service import legal_graph, LegalDomain

    laws = await legal_graph.get_laws_by_domain(LegalDomain(domain.value))

    return [
        LawResponse(
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
        for law in laws
    ]


@router.post("/laws", response_model=LawResponse)
async def create_law(
    request: LawCreateRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Add a new law to the legal knowledge graph.

    Requires API key authentication.
    """
    from app.services.sil.legal_graph_service import (
        legal_graph,
        LegalLaw,
        LegalDomain,
        LawStatus,
    )

    try:
        law = LegalLaw(
            boe_id=request.boe_id,
            title=request.title,
            short_name=request.short_name,
            domain=LegalDomain(request.domain.value),
            status=LawStatus(request.status.value),
            publication_date=request.publication_date,
            effective_date=request.effective_date,
            eli_uri=request.eli_uri,
            summary=request.summary,
            keywords=request.keywords,
        )

        success = await legal_graph.add_law(law)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add law")

        return LawResponse(
            boe_id=law.boe_id,
            title=law.title,
            short_name=law.short_name,
            domain=law.domain.value,
            status=law.status.value,
            publication_date=law.publication_date,
            effective_date=law.effective_date,
            eli_uri=law.eli_uri,
            summary=law.summary,
            keywords=law.keywords,
        )

    except Exception as e:
        logger.error(f"Failed to create law: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws/{boe_id}/articles", response_model=List[ArticleResponse])
async def get_articles_for_law(boe_id: str):
    """Get all articles for a specific law."""
    from app.services.sil.legal_graph_service import legal_graph

    # First verify law exists
    law = await legal_graph.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")

    articles = await legal_graph.get_articles_for_law(boe_id)

    return [
        ArticleResponse(
            article_id=art.get("article_id", ""),
            law_boe_id=art.get("law_boe_id", boe_id),
            article_number=art.get("article_number", ""),
            title=art.get("title"),
            summary=art.get("summary"),
            key_concepts=art.get("key_concepts", []),
            is_derogated=art.get("is_derogated", False),
        )
        for art in articles
    ]


@router.post("/laws/{boe_id}/articles", response_model=ArticleResponse)
async def create_article(
    boe_id: str,
    request: ArticleCreateRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Add an article to a law.

    Requires API key authentication.
    """
    from app.services.sil.legal_graph_service import legal_graph

    # Verify law exists
    law = await legal_graph.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")

    success = await legal_graph.add_article(
        law_boe_id=boe_id,
        article_number=request.article_number,
        title=request.title,
        summary=request.summary,
        key_concepts=request.key_concepts,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to add article")

    article_id = f"{boe_id}:art:{request.article_number}"

    return ArticleResponse(
        article_id=article_id,
        law_boe_id=boe_id,
        article_number=request.article_number,
        title=request.title,
        summary=request.summary,
        key_concepts=request.key_concepts,
        is_derogated=False,
    )


@router.post("/documents/{document_id}/link-law")
async def link_document_to_law(
    document_id: str,
    request: DocumentLawLinkRequest,
    tenant_id: str = Query(..., description="Tenant ID"),
    api_key: str = Depends(verify_api_key),
):
    """
    Link a document to an applicable law.

    This creates a `governed_by` relationship between the document
    and the law in the knowledge graph.

    Requires API key authentication.
    """
    from app.services.sil.legal_graph_service import legal_graph

    # Verify law exists
    law = await legal_graph.get_law(request.law_boe_id)
    if not law:
        raise HTTPException(
            status_code=404,
            detail=f"Law '{request.law_boe_id}' not found"
        )

    success = await legal_graph.link_document_to_law(
        document_id=document_id,
        law_boe_id=request.law_boe_id,
        tenant_id=tenant_id,
        relationship_type=request.relationship_type,
        articles=request.articles,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to link document to law")

    return {
        "success": True,
        "document_id": document_id,
        "law_boe_id": request.law_boe_id,
        "relationship": request.relationship_type,
    }


@router.get("/documents/{document_id}/applicable-laws", response_model=List[LawResponse])
async def get_applicable_laws(
    document_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
):
    """
    Get all laws applicable to a document.

    Returns the laws that have been linked to this document
    via the `governed_by` relationship.
    """
    from app.services.sil.legal_graph_service import legal_graph

    laws = await legal_graph.get_applicable_laws(document_id, tenant_id)

    return [
        LawResponse(
            boe_id=law.get("boe_id", ""),
            title=law.get("title", ""),
            short_name=law.get("short_name", ""),
            domain=law.get("domain", ""),
            status=law.get("status", "vigente"),
        )
        for law in laws
    ]


@router.get("/suggest-laws")
async def suggest_applicable_laws(
    document_type: str = Query(..., description="Document semantic type"),
    domain: Optional[str] = Query(None, description="Business domain"),
):
    """
    Suggest laws that might apply to a document type.

    Uses heuristics based on document type and domain to
    suggest potentially applicable legislation.
    """
    from app.services.sil.legal_graph_service import legal_graph

    laws = await legal_graph.find_applicable_laws_for_domain(
        document_type=document_type,
        domain=domain,
    )

    return {
        "document_type": document_type,
        "domain": domain,
        "suggested_laws": [
            {
                "boe_id": law.get("boe_id", ""),
                "short_name": law.get("short_name", ""),
                "title": law.get("title", ""),
                "domain": law.get("domain", ""),
            }
            for law in laws
        ],
    }


@router.get("/graph/structure")
async def get_legal_graph_structure():
    """Get full legal graph structure (nodes + edges) for D3 visualization."""
    from app.services.sil.legal_graph_service import legal_graph

    try:
        await legal_graph.initialize()
        structure = await legal_graph.get_graph_structure()
        return structure
    except Exception as e:
        logger.error(f"Failed to get legal graph structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/enriched")
async def get_enriched_legal_graph():
    """
    Get enriched legal graph with domain clusters, topics, and metrics.

    Returns:
    - nodes: Law nodes + Domain cluster nodes + Topic nodes
    - edges: Law relationships + Domain membership + Topic coverage
    - stats: Graph statistics (hub laws, edge types, domain counts)

    Node types:
    - law: Actual legislation (BOE documents)
    - domain: Cluster nodes grouping laws by legal domain
    - topic: Shared topics/keywords connecting multiple laws

    Edge types:
    - MODIFIES, REFERENCES, DEROGATES: Law-to-law relationships
    - CONTAINS: Domain-to-law membership
    - COVERS: Topic-to-law coverage
    """
    from app.services.sil.legal_graph_service import legal_graph

    try:
        await legal_graph.initialize()
        structure = await legal_graph.get_enriched_graph_structure()
        return structure
    except Exception as e:
        logger.error(f"Failed to get enriched legal graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/search")
async def search_legal_graph(
    q: Optional[str] = Query(None, description="Search query (matches title, short_name, boe_id)"),
    domain: Optional[str] = Query(None, description="Filter by domain (labor, fiscal, civil, etc.)"),
    boe_id: Optional[str] = Query(None, description="Get specific law and its neighbors"),
    include_neighbors: bool = Query(True, description="Include connected laws in results"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
):
    """
    Search the legal graph for laws matching criteria.

    Use cases:
    - Search by keyword: ?q=despido
    - Filter by domain: ?domain=labor
    - Get law and neighbors: ?boe_id=BOE-A-2015-11430
    - Combined: ?q=contrato&domain=civil

    Returns filtered graph structure with matching nodes and their connections.
    """
    from app.services.sil.legal_graph_service import legal_graph

    try:
        await legal_graph.initialize()
        structure = await legal_graph.get_graph_structure()
        nodes = structure.get("nodes", [])
        edges = structure.get("edges", [])

        if not nodes:
            return {"nodes": [], "edges": [], "query": {"q": q, "domain": domain, "boe_id": boe_id}}

        matched_ids = set()

        # Filter by specific BOE ID
        if boe_id:
            for node in nodes:
                if node.get("id") == boe_id:
                    matched_ids.add(boe_id)
                    break

        # Filter by domain
        if domain:
            domain_lower = domain.lower()
            for node in nodes:
                if node.get("domain", "").lower() == domain_lower:
                    matched_ids.add(node.get("id"))

        # Filter by search query
        if q:
            q_lower = q.lower()
            for node in nodes:
                node_id = node.get("id", "").lower()
                label = node.get("label", "").lower()
                title = node.get("title", "").lower()

                if q_lower in node_id or q_lower in label or q_lower in title:
                    matched_ids.add(node.get("id"))

        # If no filters, return all (limited)
        if not q and not domain and not boe_id:
            matched_ids = {n.get("id") for n in nodes[:limit]}

        # Include neighbors if requested
        if include_neighbors and matched_ids:
            neighbor_ids = set()
            for edge in edges:
                src = edge.get("source")
                tgt = edge.get("target")
                if src in matched_ids:
                    neighbor_ids.add(tgt)
                if tgt in matched_ids:
                    neighbor_ids.add(src)
            matched_ids.update(neighbor_ids)

        # Limit results
        matched_ids = set(list(matched_ids)[:limit])

        # Filter nodes and edges
        filtered_nodes = [n for n in nodes if n.get("id") in matched_ids]
        filtered_edges = [
            e for e in edges
            if e.get("source") in matched_ids and e.get("target") in matched_ids
        ]

        # Generate deep link URL for frontend
        focus_boe = boe_id or (list(matched_ids)[0] if matched_ids else None)

        return {
            "nodes": filtered_nodes,
            "edges": filtered_edges,
            "query": {
                "q": q,
                "domain": domain,
                "boe_id": boe_id,
                "matched_count": len(filtered_nodes),
            },
            "deep_link": f"/admin/knowledge-tree?focus={focus_boe}" if focus_boe else None,
        }

    except Exception as e:
        logger.error(f"Failed to search legal graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=LegalGraphStats)
async def get_legal_graph_stats():
    """Get statistics about the legal knowledge graph."""
    from app.services.sil.legal_graph_service import legal_graph

    stats = await legal_graph.get_stats()

    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])

    return LegalGraphStats(
        total_laws=stats.get("total_laws", 0),
        total_articles=stats.get("total_articles", 0),
        laws_by_domain=stats.get("laws_by_domain", {}),
    )
