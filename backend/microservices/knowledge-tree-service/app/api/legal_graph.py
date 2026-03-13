"""
Legal Knowledge Graph API — Consolidated endpoints

This is the single source of truth for all legal graph operations.
Other services (weaviate-service, emma-agent-service) call these
endpoints via HTTP instead of direct singleton access.

Endpoints fall in two categories:
- Public API: CRUD for laws, graph visualization, stats
- Internal API: Reference extraction/storage used by BOE pipeline
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
import logging

from app.core.security import verify_api_key
from app.services.legal_graph_service import (
    legal_graph,
    LegalLaw,
    LegalDomain,
    LawStatus,
)
from app.services.extractors import (
    legal_reference_extractor,
    LegalReferences,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legal", tags=["legal-knowledge-graph"])


# ── Schemas ───────────────────────────────────────────────────────────

class LegalDomainEnum(str, Enum):
    LABOR = "labor"
    FISCAL = "fiscal"
    PRIVACY = "privacy"
    CIVIL = "civil"
    MERCANTILE = "mercantile"
    ADMINISTRATIVE = "administrative"
    COMPLIANCE = "compliance"
    IP = "ip"
    COMMERCE = "commerce"
    REAL_ESTATE = "real_estate"
    EDUCATION = "education"
    GENERAL = "general"


class LawStatusEnum(str, Enum):
    VIGENTE = "vigente"
    DEROGADA = "derogada"
    PARCIALMENTE_DEROGADA = "parcialmente_derogada"


class LawCreateRequest(BaseModel):
    boe_id: str = Field(..., description="BOE identifier")
    title: str = Field(..., description="Full title")
    short_name: str = Field(..., description="Short name (ET, RGPD)")
    domain: LegalDomainEnum = Field(LegalDomainEnum.GENERAL)
    status: LawStatusEnum = Field(LawStatusEnum.VIGENTE)
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    eli_uri: Optional[str] = None
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    weaviate_uuid: Optional[str] = None


class LawResponse(BaseModel):
    boe_id: str
    title: str = ""
    short_name: str = ""
    domain: str = ""
    status: str = "vigente"
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    eli_uri: Optional[str] = None
    summary: Optional[str] = None
    keywords: List[str] = []
    weaviate_uuid: Optional[str] = None


class ArticleCreateRequest(BaseModel):
    article_number: str
    content_hash: str = ""


class DocumentLawLinkRequest(BaseModel):
    law_boe_id: str
    relationship_type: str = "GOVERNED_BY"
    tenant_id: str = ""


class ReferenceStoreRequest(BaseModel):
    """Request to extract and store references for a law."""
    boe_id: str
    text: str = Field(..., description="Full legislation text for extraction")


class AddReferenceRequest(BaseModel):
    """Request to add a single reference edge."""
    source_boe_id: str
    target_boe_id: str
    relationship_type: str = "REFERENCES"
    context_snippet: str = ""
    articles_affected: List[str] = Field(default_factory=list)


class NeighborRequest(BaseModel):
    """Request for law neighbor traversal."""
    boe_id: str
    max_depth: int = 2
    relationship_types: Optional[List[str]] = None


# ── Helper ────────────────────────────────────────────────────────────

def _law_dict_to_response(law: Dict[str, Any]) -> LawResponse:
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


# ── Public API: Law CRUD ──────────────────────────────────────────────

@router.get("/laws", response_model=List[LawResponse])
async def list_laws(
    domain: Optional[LegalDomainEnum] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List all laws, optionally filtered by domain."""
    try:
        if domain:
            laws = await legal_graph.get_laws_by_domain(LegalDomain(domain.value))
        else:
            laws = await legal_graph.get_all_laws()
        return [_law_dict_to_response(law) for law in laws[:limit]]
    except Exception as e:
        logger.error(f"Failed to list laws: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws/{boe_id}", response_model=LawResponse)
async def get_law(boe_id: str):
    """Get a specific law by BOE ID."""
    law = await legal_graph.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")
    return _law_dict_to_response(law)


@router.get("/laws/domain/{domain}", response_model=List[LawResponse])
async def get_laws_by_domain(domain: LegalDomainEnum):
    """Get all laws for a specific domain."""
    laws = await legal_graph.get_laws_by_domain(LegalDomain(domain.value))
    return [_law_dict_to_response(law) for law in laws]


@router.post("/laws", response_model=LawResponse)
async def create_law(
    request: LawCreateRequest,
    _: bool = Depends(verify_api_key),
):
    """Add or update a law node. Requires API key."""
    try:
        law = LegalLaw(
            boe_id=request.boe_id,
            title=request.title,
            short_name=request.short_name,
            domain=LegalDomain(request.domain.value),
            status=LawStatus(request.status.value),
            publication_date=request.publication_date or "",
            effective_date=request.effective_date or "",
            eli_uri=request.eli_uri or "",
            summary=request.summary or "",
            keywords=request.keywords,
            weaviate_uuid=request.weaviate_uuid,
        )
        success = await legal_graph.add_law(law)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add law")
        return LawResponse(
            boe_id=law.boe_id, title=law.title,
            short_name=law.short_name, domain=law.domain.value,
            status=law.status.value, publication_date=law.publication_date,
            effective_date=law.effective_date, eli_uri=law.eli_uri,
            summary=law.summary, keywords=law.keywords,
            weaviate_uuid=law.weaviate_uuid,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create law: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Articles ──────────────────────────────────────────────────────────

@router.get("/laws/{boe_id}/articles")
async def get_articles_for_law(boe_id: str):
    """Get all articles for a specific law."""
    law = await legal_graph.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")
    return await legal_graph.get_articles_for_law(boe_id)


@router.post("/laws/{boe_id}/articles")
async def create_article(
    boe_id: str,
    request: ArticleCreateRequest,
    _: bool = Depends(verify_api_key),
):
    """Add an article to a law. Requires API key."""
    law = await legal_graph.get_law(boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{boe_id}' not found")
    success = await legal_graph.add_article(
        boe_id=boe_id,
        article_number=request.article_number,
        content_hash=request.content_hash,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add article")
    return {"success": True, "boe_id": boe_id, "article_number": request.article_number}


# ── Document-Law Linking ──────────────────────────────────────────────

@router.post("/documents/{document_id}/link-law")
async def link_document_to_law(
    document_id: str,
    request: DocumentLawLinkRequest,
    _: bool = Depends(verify_api_key),
):
    """Link a tenant document to a law. Requires API key."""
    law = await legal_graph.get_law(request.law_boe_id)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{request.law_boe_id}' not found")
    success = await legal_graph.link_document_to_law(
        document_id=document_id,
        law_boe_id=request.law_boe_id,
        tenant_id=request.tenant_id,
        relationship=request.relationship_type,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to link document to law")
    return {"success": True, "document_id": document_id, "law_boe_id": request.law_boe_id}


@router.get("/documents/{document_id}/applicable-laws")
async def get_applicable_laws(
    document_id: str,
    tenant_id: str = Query(...),
):
    """Get laws linked to a document."""
    laws = await legal_graph.get_applicable_laws(document_id, tenant_id)
    return [_law_dict_to_response(law) for law in laws]


@router.get("/suggest-laws")
async def suggest_applicable_laws(
    document_type: str = Query(...),
    domain: Optional[str] = Query(None),
):
    """Suggest laws that might apply to a document type."""
    laws = await legal_graph.find_applicable_laws_for_domain(document_type, domain or "")
    return {
        "document_type": document_type,
        "domain": domain,
        "suggested_laws": [
            {"boe_id": law.get("boe_id", ""), "short_name": law.get("short_name", ""),
             "title": law.get("title", ""), "domain": law.get("domain", "")}
            for law in laws
        ],
    }


# ── Graph Visualization ──────────────────────────────────────────────

@router.get("/graph/structure")
async def get_legal_graph_structure():
    """Get full legal graph structure (nodes + edges) for D3 visualization."""
    try:
        await legal_graph.initialize()
        return await legal_graph.get_graph_structure()
    except Exception as e:
        logger.error(f"Failed to get legal graph structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/enriched")
async def get_enriched_legal_graph():
    """Get enriched graph with domain clusters and metrics."""
    try:
        await legal_graph.initialize()
        return await legal_graph.get_enriched_graph_structure()
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
    """Search the legal graph for laws matching criteria."""
    try:
        await legal_graph.initialize()
        structure = await legal_graph.get_graph_structure()
        nodes = structure.get("nodes", [])
        edges = structure.get("edges", [])

        if not nodes:
            return {"nodes": [], "edges": [], "query": {"q": q, "domain": domain, "boe_id": boe_id}}

        matched_ids = set()

        if boe_id:
            for node in nodes:
                if node.get("id") == boe_id:
                    matched_ids.add(boe_id)
                    break

        if domain:
            domain_lower = domain.lower()
            for node in nodes:
                if node.get("domain", "").lower() == domain_lower:
                    matched_ids.add(node.get("id"))

        if q:
            q_lower = q.lower()
            for node in nodes:
                if (q_lower in node.get("id", "").lower()
                        or q_lower in node.get("label", "").lower()
                        or q_lower in node.get("title", "").lower()):
                    matched_ids.add(node.get("id"))

        if not q and not domain and not boe_id:
            matched_ids = {n.get("id") for n in nodes[:limit]}

        if include_neighbors and matched_ids:
            neighbor_ids = set()
            for edge in edges:
                src, tgt = edge.get("source"), edge.get("target")
                if src in matched_ids:
                    neighbor_ids.add(tgt)
                if tgt in matched_ids:
                    neighbor_ids.add(src)
            matched_ids.update(neighbor_ids)

        matched_ids = set(list(matched_ids)[:limit])
        filtered_nodes = [n for n in nodes if n.get("id") in matched_ids]
        filtered_edges = [
            e for e in edges
            if e.get("source") in matched_ids and e.get("target") in matched_ids
        ]

        return {
            "nodes": filtered_nodes,
            "edges": filtered_edges,
            "query": {"q": q, "domain": domain, "boe_id": boe_id, "matched_count": len(filtered_nodes)},
        }
    except Exception as e:
        logger.error(f"Failed to search legal graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stats ─────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_legal_graph_stats():
    """Get statistics about the public legal graph."""
    stats = await legal_graph.get_stats()
    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])
    return stats


# ── Internal API: Reference Extraction & Storage ──────────────────────
# Used by weaviate-service BOE pipeline via HTTP

@router.post("/references/extract")
async def extract_references(
    request: ReferenceStoreRequest,
    _: bool = Depends(verify_api_key),
):
    """Extract legal references from text. Internal API for BOE pipeline."""
    try:
        refs = await legal_reference_extractor.extract(
            text=request.text, boe_id=request.boe_id
        )
        return refs.to_dict()
    except Exception as e:
        logger.error(f"Failed to extract references for {request.boe_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/references/extract-and-store")
async def extract_and_store_references(
    request: ReferenceStoreRequest,
    _: bool = Depends(verify_api_key),
):
    """Extract references from text AND store as graph edges. Internal API."""
    try:
        refs = await legal_reference_extractor.extract(
            text=request.text, boe_id=request.boe_id
        )
        counts = await legal_graph.store_references(request.boe_id, refs)
        return {
            "extracted": refs.to_dict(),
            "stored": counts,
        }
    except Exception as e:
        logger.error(f"Failed to extract+store references for {request.boe_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/references/add")
async def add_reference(
    request: AddReferenceRequest,
    _: bool = Depends(verify_api_key),
):
    """Add a single reference edge between two laws. Internal API."""
    success = await legal_graph.add_reference(
        source_boe_id=request.source_boe_id,
        target_boe_id=request.target_boe_id,
        relationship_type=request.relationship_type,
        context_snippet=request.context_snippet,
        articles_affected=request.articles_affected,
    )
    return {"success": success}


@router.post("/references/enrich-boe")
async def enrich_from_boe_api(
    boe_id: str = Query(...),
    _: bool = Depends(verify_api_key),
):
    """Fetch BOE /analisis API for posterior/anterior references. Internal API."""
    try:
        analysis = await legal_reference_extractor.enrich_from_boe_api(boe_id)
        return {
            "boe_id": boe_id,
            "posterior_references": analysis.posterior_references,
            "anterior_references": analysis.anterior_references,
            "materias": analysis.materias,
        }
    except Exception as e:
        logger.error(f"Failed to enrich from BOE API for {boe_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/neighbors")
async def get_law_neighbors(request: NeighborRequest):
    """Get neighboring laws via graph traversal."""
    try:
        neighbors = await legal_graph.get_law_neighbors(
            boe_id=request.boe_id,
            max_depth=request.max_depth,
            relationship_types=request.relationship_types,
        )
        return {"boe_id": request.boe_id, "neighbors": neighbors}
    except Exception as e:
        logger.error(f"Failed to get neighbors for {request.boe_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
