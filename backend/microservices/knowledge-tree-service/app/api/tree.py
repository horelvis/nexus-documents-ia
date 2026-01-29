"""
Tree API endpoints for Knowledge Tree Service.
"""

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.services.tenant_knowledge_service import tenant_knowledge_service
from app.services.structural_indexer import structural_indexer
from app.core.security import verify_api_key
import re
import unicodedata

tree_router = APIRouter()


class TreeContextRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")
    limit: int = Field(15, description="Max number of folders in context")


class TreeContextResponse(BaseModel):
    success: bool
    context_for_llm: str = ""
    metadata: Dict[str, Any] = {}


class SummaryRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")


class SummaryResponse(BaseModel):
    summary: str = ""


class StructuralQueryRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")
    query: str = Field(..., description="Natural language query")
    max_results: int = Field(100, description="Max results to include")


class StructuralQueryResponse(BaseModel):
    route: str = "GRAPH_ONLY"
    confidence: float = 0.95
    context: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    entities: list[str] = Field(default_factory=list)


class StructuralIndexRequest(BaseModel):
    document_id: str = Field(..., description="Document or folder ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    file_path: str = Field("", description="Full file path")
    connector_metadata: Dict[str, Any] = Field(default_factory=dict)
    learned_context: Dict[str, Any] = Field(default_factory=dict)
    weaviate_document_id: str | None = Field(default=None)
    connector_id: str | None = Field(default=None)


class StructuralIndexResponse(BaseModel):
    success: bool
    indexed_to_graph: bool = False
    node_type: str | None = None
    folder_type: str | None = None
    semantic_type: str | None = None
    error: str | None = None


class GraphStatsResponse(BaseModel):
    total_documents: int = 0
    total_folders: int = 0
    types_breakdown: Dict[str, int] = Field(default_factory=dict)
    domains_breakdown: Dict[str, int] = Field(default_factory=dict)


class DocumentIdsResponse(BaseModel):
    document_ids: list[str] = Field(default_factory=list)


@tree_router.post("/context", response_model=TreeContextResponse)
async def tree_context(request: TreeContextRequest, _: bool = Depends(verify_api_key)):
    start_time = time.time()
    ctx = await tenant_knowledge_service.build_toon_context(
        tenant_id=request.tenant_id,
        limit=request.limit,
    )
    return TreeContextResponse(
        success=True,
        context_for_llm=ctx.get("context_for_llm", ""),
        metadata={"latency_ms": int((time.time() - start_time) * 1000)},
    )


@tree_router.post("/summary", response_model=SummaryResponse)
async def summary(request: SummaryRequest, _: bool = Depends(verify_api_key)):
    ctx = await tenant_knowledge_service.build_toon_context(
        tenant_id=request.tenant_id,
        limit=0,
    )
    return SummaryResponse(summary=ctx.get("context_for_llm", ""))


@tree_router.post("/structural/query", response_model=StructuralQueryResponse)
async def structural_query(request: StructuralQueryRequest, _: bool = Depends(verify_api_key)):
    """
    Execute structural query against Apache AGE graph for a tenant.
    Returns GRAPH_ONLY results with structural context and counts.
    """
    await tenant_knowledge_service.initialize()

    totals = await tenant_knowledge_service.get_totals(request.tenant_id)
    container_type_counts = await tenant_knowledge_service.get_container_type_counts(request.tenant_id)
    document_type_counts = await tenant_knowledge_service.get_document_type_counts(request.tenant_id)
    top_folders = await tenant_knowledge_service.get_top_folders(request.tenant_id)
    toon_context = await tenant_knowledge_service.build_toon_context(
        tenant_id=request.tenant_id,
        limit=min(request.max_results, 100),
    )

    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        normalized = normalized.lower().strip()
        if normalized.endswith("s") and len(normalized) > 3:
            normalized = normalized[:-1]
        return normalized

    year_match = re.search(r"\b(19|20)\d{2}\b", request.query or "")
    year = year_match.group(0) if year_match else None
    query_norm = _normalize(request.query or "")

    folder_type_match = None
    doc_type_match = None

    folder_types = list(container_type_counts.keys())
    for ft in folder_types:
        if _normalize(ft) in query_norm:
            folder_type_match = ft
            break

    document_types = list(document_type_counts.keys())
    for dt in document_types:
        if _normalize(dt) in query_norm:
            doc_type_match = dt
            break

    count = None
    count_type = None
    matched_type = None
    if year and folder_type_match:
        count = await tenant_knowledge_service.get_folder_count_by_year_and_type(
            request.tenant_id, year, folder_type_match
        )
        if count == 0:
            count = await tenant_knowledge_service.get_folder_count_by_year_and_path_segment(
                request.tenant_id, year, folder_type_match
            )
        count_type = "folders"
        matched_type = folder_type_match
    elif year and doc_type_match:
        count = await tenant_knowledge_service.get_document_count_by_year_and_type(
            request.tenant_id, year, doc_type_match
        )
        if count == 0:
            count = await tenant_knowledge_service.get_document_count_by_year_and_path_segment(
                request.tenant_id, year, doc_type_match
            )
        count_type = "documents"
        matched_type = doc_type_match
    elif year:
        count = await tenant_knowledge_service.get_folder_count_by_year(request.tenant_id, year)
        count_type = "folders"
        if count == 0:
            count = await tenant_knowledge_service.get_document_count_by_year(request.tenant_id, year)
            count_type = "documents"

    entities: list[str] = []
    entities.extend([f.get("name", "") for f in top_folders if f.get("name")])
    entities.extend([t for t in container_type_counts.keys()])
    entities.extend([t for t in document_type_counts.keys()])
    entities = [e for e in entities if e]
    entities = entities[:20]

    return StructuralQueryResponse(
        route="GRAPH_ONLY",
        confidence=0.95,
        context=toon_context.get("context_for_llm", ""),
        data={
            "totals": totals,
            "container_type_counts": container_type_counts,
            "document_type_counts": document_type_counts,
            "type_counts": document_type_counts,
            "top_folders": top_folders,
            "entities": entities,
            **({"count": count, "year": year, "count_type": count_type, "matched_type": matched_type} if count is not None else {}),
        },
        entities=entities,
    )


@tree_router.post("/index", response_model=StructuralIndexResponse)
async def index_structural(request: StructuralIndexRequest, _: bool = Depends(verify_api_key)):
    result = await structural_indexer.index(request.model_dump())
    return StructuralIndexResponse(**result)


@tree_router.get("/graph/document-ids", response_model=DocumentIdsResponse)
async def graph_document_ids(
    tenant_id: str = Query(..., description="Tenant identifier"),
    limit: int = Query(10000, description="Max number of ids"),
    _: bool = Depends(verify_api_key),
):
    ids = await tenant_knowledge_service.get_document_ids(tenant_id=tenant_id, limit=limit)
    return DocumentIdsResponse(document_ids=ids)


@tree_router.get("/stats", response_model=GraphStatsResponse)
async def graph_stats(
    tenant_id: str = Query(..., description="Tenant identifier"),
    _: bool = Depends(verify_api_key),
):
    """Get knowledge graph statistics for a tenant from Apache AGE."""
    from app.services.age_client import age_client
    from app.core.config import settings

    await age_client.initialize()
    graph = settings.age_graph_name

    total_documents = 0
    total_folders = 0
    types_breakdown: Dict[str, int] = {}
    domains_breakdown: Dict[str, int] = {}

    try:
        # Count documents
        rows = await age_client.execute_cypher(f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                RETURN count(d) as total
            $$) as (total agtype)
        """)
        if rows:
            total_documents = int(str(rows[0]["total"]))

        # Count folders
        rows = await age_client.execute_cypher(f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                RETURN count(f) as total
            $$) as (total agtype)
        """)
        if rows:
            total_folders = int(str(rows[0]["total"]))

        # Documents by semantic_type
        rows = await age_client.execute_cypher(f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                RETURN d.semantic_type as stype, count(d) as total
            $$) as (stype agtype, total agtype)
        """)
        for r in rows:
            stype = str(r["stype"]).strip('"') if r["stype"] else "unknown"
            types_breakdown[stype] = int(str(r["total"]))

        # Folders by folder_type
        rows = await age_client.execute_cypher(f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                RETURN f.folder_type as ftype, count(f) as total
            $$) as (ftype agtype, total agtype)
        """)
        for r in rows:
            ftype = str(r["ftype"]).strip('"') if r["ftype"] else "unknown"
            domains_breakdown[f"folder:{ftype}"] = int(str(r["total"]))

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Graph stats query failed: {e}")

    return GraphStatsResponse(
        total_documents=total_documents,
        total_folders=total_folders,
        types_breakdown=types_breakdown,
        domains_breakdown=domains_breakdown,
    )


@tree_router.get("/graph/structure")
async def graph_structure(
    tenant_id: str = Query(..., description="Tenant identifier"),
    _: bool = Depends(verify_api_key),
):
    """Get full graph structure (nodes + edges) for visualization."""
    from app.services.age_client import age_client
    from app.core.config import settings

    await age_client.initialize()
    graph = settings.age_graph_name

    nodes = []
    edges = []

    try:
        # Get folders with document counts
        rows = await age_client.execute_cypher(f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})
                OPTIONAL MATCH (f)-[:HAS_DOCUMENT]->(d:structural_document)
                RETURN f.path as path, f.name as name, f.folder_type as folder_type, count(d) as doc_count
            $$) as (path agtype, name agtype, folder_type agtype, doc_count agtype)
        """)
        for r in rows:
            path = str(r["path"]).strip('"') if r["path"] else ""
            name = str(r["name"]).strip('"') if r["name"] else path.split("/")[-1]
            folder_type = str(r["folder_type"]).strip('"') if r["folder_type"] else "unknown"
            doc_count = int(str(r["doc_count"])) if r["doc_count"] else 0
            nodes.append({
                "id": f"f:{path}",
                "label": name,
                "node_type": "folder",
                "folder_type": folder_type,
                "doc_count": doc_count,
                "path": path,
            })

        # Get documents
        rows = await age_client.execute_cypher(f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (d:structural_document {{tenant_id: '{tenant_id}'}})
                RETURN d.document_id as document_id, d.title as title,
                       d.semantic_type as semantic_type, d.folder_path as folder_path
            $$) as (document_id agtype, title agtype, semantic_type agtype, folder_path agtype)
        """)
        for r in rows:
            doc_id = str(r["document_id"]).strip('"') if r["document_id"] else ""
            title = str(r["title"]).strip('"') if r["title"] else "Sin título"
            semantic_type = str(r["semantic_type"]).strip('"') if r["semantic_type"] else "unknown"
            folder_path = str(r["folder_path"]).strip('"') if r["folder_path"] else ""
            nodes.append({
                "id": f"d:{doc_id}",
                "label": title,
                "node_type": "document",
                "semantic_type": semantic_type,
                "file_path": folder_path,
            })

        # Get edges (folder -> document)
        rows = await age_client.execute_cypher(f"""
            SELECT * FROM cypher('{graph}', $$
                MATCH (f:structural_folder {{tenant_id: '{tenant_id}'}})-[:HAS_DOCUMENT]->(d:structural_document)
                RETURN f.path as folder_path, d.document_id as document_id
            $$) as (folder_path agtype, document_id agtype)
        """)
        for r in rows:
            fp = str(r["folder_path"]).strip('"') if r["folder_path"] else ""
            did = str(r["document_id"]).strip('"') if r["document_id"] else ""
            edges.append({
                "id": f"e:f:{fp}->d:{did}",
                "source": f"f:{fp}",
                "target": f"d:{did}",
            })

        # Deduplicate folder->document edges
        seen_edge_keys: set[str] = set()
        unique_edges = []
        for e in edges:
            key = f"{e['source']}->{e['target']}"
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                unique_edges.append(e)
        edges = unique_edges

        # Synthesize missing intermediate folders and build parent->child edges
        existing_folder_ids = {n["id"] for n in nodes if n["node_type"] == "folder"}
        folder_paths = [n["path"] for n in nodes if n["node_type"] == "folder"]

        # Collect all intermediate paths that are missing
        missing_paths: set[str] = set()
        for path in folder_paths:
            parts = path.split("/")
            for i in range(2, len(parts)):
                ancestor = "/".join(parts[:i])
                if f"f:{ancestor}" not in existing_folder_ids:
                    missing_paths.add(ancestor)

        # Add synthetic folder nodes for missing intermediates
        for mp in missing_paths:
            node_id = f"f:{mp}"
            nodes.append({
                "id": node_id,
                "label": mp.split("/")[-1],
                "node_type": "folder",
                "folder_type": "virtual",
                "doc_count": 0,
                "path": mp,
            })
            existing_folder_ids.add(node_id)

        # Build parent->child edges for ALL folders
        all_folder_paths = [n["path"] for n in nodes if n["node_type"] == "folder"]
        for path in all_folder_paths:
            if "/" not in path:
                continue
            parent = "/".join(path.split("/")[:-1])
            if not parent:
                continue
            parent_id = f"f:{parent}"
            child_id = f"f:{path}"
            if parent_id in existing_folder_ids:
                key = f"{parent_id}->{child_id}"
                if key not in seen_edge_keys:
                    seen_edge_keys.add(key)
                    edges.append({
                        "id": f"e:{key}",
                        "source": parent_id,
                        "target": child_id,
                    })

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Graph structure query failed: {e}")

    return {"nodes": nodes, "edges": edges}


@tree_router.delete("/graph/clear")
async def clear_graph(
    tenant_id: str = Query(..., description="Tenant identifier"),
    _: bool = Depends(verify_api_key),
):
    result = await tenant_knowledge_service.clear_tenant_graph(tenant_id=tenant_id)
    return {"success": result}
