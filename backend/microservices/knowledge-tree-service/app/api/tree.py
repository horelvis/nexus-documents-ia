"""
Tree API endpoints for Knowledge Tree Service.
"""

import logging
import time
from typing import Any, Dict, List, Optional

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
    connector_type: str | None = Field(default=None, description="Connector type (alfresco, google_drive, onedrive, database)")


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
    Execute structural query against FalkorDB graph for a tenant.
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
    elif doc_type_match:
        count = document_type_counts.get(doc_type_match, 0)
        count_type = "documents"
        matched_type = doc_type_match
    elif folder_type_match:
        count = container_type_counts.get(folder_type_match, 0)
        count_type = "folders"
        matched_type = folder_type_match

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


class BatchIndexRequest(BaseModel):
    items: List[StructuralIndexRequest] = Field(..., description="Items to index (max 100)", max_length=100)


class BatchIndexResponse(BaseModel):
    success: int = 0
    errors: int = 0
    results: List[StructuralIndexResponse] = Field(default_factory=list)


@tree_router.post("/index/batch", response_model=BatchIndexResponse)
async def index_structural_batch(request: BatchIndexRequest, _: bool = Depends(verify_api_key)):
    """Batch index multiple items sequentially. Avoids N HTTP round-trips during backfill."""
    logger = logging.getLogger(__name__)
    response = BatchIndexResponse()
    for item in request.items:
        try:
            result = await structural_indexer.index(item.model_dump())
            item_response = StructuralIndexResponse(**result)
            response.results.append(item_response)
            if item_response.success:
                response.success += 1
            else:
                response.errors += 1
        except Exception as e:
            logger.warning(f"Batch index error for {item.document_id}: {e}")
            response.errors += 1
            response.results.append(StructuralIndexResponse(success=False, error=str(e)[:200]))
    return response


class GraphQueryRequest(BaseModel):
    cypher: str = Field(..., description="Native openCypher query (no AGE SQL wrapping)")
    graph_name: str = Field("", description="Graph name (ignored, uses configured FalkorDB graph)")
    tenant_id: str = Field(..., description="Tenant identifier")


class GraphQueryResponse(BaseModel):
    results: list[Dict[str, Any]] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


@tree_router.post("/graph/query", response_model=GraphQueryResponse)
async def graph_query(request: GraphQueryRequest, _: bool = Depends(verify_api_key)):
    """Execute a native openCypher query against FalkorDB for sector-aware entity expansion."""
    from app.services.falkordb_client import falkordb_client

    await falkordb_client.initialize()

    results: list[Dict[str, Any]] = []
    paths: list[str] = []

    try:
        rows = await falkordb_client.execute_cypher(request.cypher)
        for row in rows:
            parsed: Dict[str, Any] = {}
            for key, val in row.items():
                parsed[key] = val
            results.append(parsed)

            # Build path string from node-rel-node triples
            if "n" in parsed and "rel" in parsed and "m" in parsed:
                paths.append(f"{parsed['n']} --[{parsed['rel']}]--> {parsed['m']}")
    except Exception as e:
        logging.getLogger(__name__).error(f"Graph query execution failed: {e}")

    return GraphQueryResponse(results=results, paths=paths)


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
    """Get knowledge graph statistics for a tenant from FalkorDB."""
    from app.services.falkordb_client import falkordb_client

    await falkordb_client.initialize()

    total_documents = 0
    total_folders = 0
    types_breakdown: Dict[str, int] = {}
    domains_breakdown: Dict[str, int] = {}

    try:
        # Count documents
        rows = await falkordb_client.execute_cypher(
            "MATCH (d:Document {tenant_id: $tenant_id}) RETURN count(d) as total",
            {"tenant_id": tenant_id},
        )
        if rows:
            total_documents = int(rows[0].get("total", 0))

        # Count folders
        rows = await falkordb_client.execute_cypher(
            "MATCH (f:Folder {tenant_id: $tenant_id}) RETURN count(f) as total",
            {"tenant_id": tenant_id},
        )
        if rows:
            total_folders = int(rows[0].get("total", 0))

        # Documents by semantic_type
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (d:Document {tenant_id: $tenant_id})
            RETURN d.semantic_type as stype, count(d) as total
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            stype = r.get("stype") or "unknown"
            types_breakdown[stype] = int(r.get("total", 0))

        # Folders by folder_type
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (f:Folder {tenant_id: $tenant_id})
            RETURN f.folder_type as ftype, count(f) as total
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            ftype = r.get("ftype") or "unknown"
            domains_breakdown[f"folder:{ftype}"] = int(r.get("total", 0))

    except Exception as e:
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
    from app.services.falkordb_client import falkordb_client

    await falkordb_client.initialize()

    nodes = []
    edges = []

    try:
        # Get folders with document counts
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (f:Folder {tenant_id: $tenant_id})
            OPTIONAL MATCH (d:Document)-[:CONTAINED_IN]->(f)
            RETURN f.path as path, f.name as name, f.folder_type as folder_type, count(d) as doc_count
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            path = r.get("path") or ""
            name = r.get("name") or path.split("/")[-1] if path else ""
            folder_type = r.get("folder_type") or "unknown"
            doc_count = int(r.get("doc_count", 0))
            nodes.append({
                "id": f"f:{path}",
                "label": name,
                "node_type": "folder",
                "folder_type": folder_type,
                "doc_count": doc_count,
                "path": path,
            })

        # Get documents
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (d:Document {tenant_id: $tenant_id})
            RETURN d.document_id as document_id, d.title as title,
                   d.semantic_type as semantic_type, d.folder_path as folder_path
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            doc_id = r.get("document_id") or ""
            title = r.get("title") or "Sin titulo"
            semantic_type = r.get("semantic_type") or "unknown"
            folder_path = r.get("folder_path") or ""
            nodes.append({
                "id": f"d:{doc_id}",
                "label": title,
                "node_type": "document",
                "semantic_type": semantic_type,
                "file_path": folder_path,
            })

        # Get edges (document -> folder via CONTAINED_IN)
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (d:Document {tenant_id: $tenant_id})-[:CONTAINED_IN]->(f:Folder)
            RETURN f.path as folder_path, d.document_id as document_id
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            fp = r.get("folder_path") or ""
            did = r.get("document_id") or ""
            edges.append({
                "id": f"e:f:{fp}->d:{did}",
                "source": f"f:{fp}",
                "target": f"d:{did}",
                "label": "CONTAINED_IN",
            })

        # Get Entity nodes (persons, orgs, concepts, etc.)
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (e:Entity {tenant_id: $tenant_id})
            OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
            RETURN e.name as name, e.entity_type as entity_type,
                   e.normalized_name as normalized_name,
                   count(d) as doc_count
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            ename = r.get("name") or r.get("normalized_name") or ""
            etype = r.get("entity_type") or "unknown"
            doc_count = int(r.get("doc_count", 0))
            node_id = f"e:{ename}"
            # Map entity_type to frontend node_type
            if etype in ("person", "persona"):
                node_type = "person"
            elif etype in ("law", "legal_law"):
                node_type = "law"
            else:
                node_type = "entity_type"
            nodes.append({
                "id": node_id,
                "label": ename,
                "node_type": node_type,
                "semantic_type": etype,
                "doc_count": doc_count,
            })

        # Get MENTIONED_IN edges (Entity → Document)
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (e:Entity {tenant_id: $tenant_id})-[:MENTIONED_IN]->(d:Document)
            RETURN e.name as entity_name, d.document_id as document_id
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            ename = r.get("entity_name") or ""
            did = r.get("document_id") or ""
            edges.append({
                "id": f"e:mi:{ename}->{did}",
                "source": f"e:{ename}",
                "target": f"d:{did}",
                "label": "MENTIONED_IN",
            })

        # Get RELATED_TO edges (Entity ↔ Entity)
        rows = await falkordb_client.execute_cypher(
            """
            MATCH (e1:Entity {tenant_id: $tenant_id})-[:RELATED_TO]->(e2:Entity)
            RETURN e1.name as source_name, e2.name as target_name
            LIMIT 200
            """,
            {"tenant_id": tenant_id},
        )
        for r in rows:
            src = r.get("source_name") or ""
            tgt = r.get("target_name") or ""
            edges.append({
                "id": f"e:rt:{src}->{tgt}",
                "source": f"e:{src}",
                "target": f"e:{tgt}",
                "label": "RELATED_TO",
            })

        # Deduplicate edges
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
                        "label": "CONTAINS",
                    })

    except Exception as e:
        logging.getLogger(__name__).error(f"Graph structure query failed: {e}")

    return {"nodes": nodes, "edges": edges}


class EntityDocumentRequest(BaseModel):
    """Request to find documents linked to a named entity via the graph."""
    tenant_id: str = Field(..., description="Tenant identifier")
    entity_name: str = Field(..., description="Entity name to search (e.g., person name)")
    entity_type: str = Field(default="person", description="Entity type (e.g., person, organization)")


class EntityDocumentResponse(BaseModel):
    document_ids: List[str] = Field(default_factory=list)


async def _batch_documents_by_entity(entity_name: str, tenant_id: str, client=None) -> List[str]:
    """Find document IDs by entity name using batched query.

    Searches 3 sources in one query instead of 3 sequential fallbacks:
    1. Entity nodes linked via relationships
    2. Document associated_person property
    3. Folder names matching entity

    Args:
        entity_name: Name to search for (case-insensitive substring match).
        tenant_id: Tenant scope for all graph queries.
        client: Optional FalkorDBClient to use; defaults to the module singleton.
    """
    if client is None:
        from app.services.falkordb_client import falkordb_client as _client
        client = _client

    sanitized = re.sub(r'[\\"\';]', '', entity_name).lower()
    if not sanitized:
        return []

    # Try UNION first (covers all 3 sources in 1 query)
    try:
        rows = await client.execute_cypher(
            """
            MATCH (d:Document)-[]-(e:Entity)
            WHERE toLower(e.name) CONTAINS $name AND d.tenant_id = $tid
            RETURN DISTINCT d.document_id AS doc_id
            UNION
            MATCH (d:Document)
            WHERE d.associated_person IS NOT NULL
              AND toLower(d.associated_person) CONTAINS $name
              AND d.tenant_id = $tid
            RETURN DISTINCT d.document_id AS doc_id
            UNION
            MATCH (d:Document)-[:CONTAINED_IN]->(f:Folder)
            WHERE toLower(f.name) CONTAINS $name AND d.tenant_id = $tid
            RETURN DISTINCT d.document_id AS doc_id
            """,
            {"name": sanitized, "tid": tenant_id},
        )
    except Exception:
        # FalkorDB may not support UNION — fall back to 2 separate queries
        rows1 = await client.execute_cypher(
            """
            MATCH (d:Document {tenant_id: $tid})
            OPTIONAL MATCH (d)-[]-(e:Entity)
            WITH d, e
            WHERE (e IS NOT NULL AND toLower(e.name) CONTAINS $name)
               OR (d.associated_person IS NOT NULL AND toLower(d.associated_person) CONTAINS $name)
            RETURN DISTINCT d.document_id AS doc_id
            """,
            {"name": sanitized, "tid": tenant_id},
        )
        rows2 = await client.execute_cypher(
            """
            MATCH (d:Document {tenant_id: $tid})-[:CONTAINED_IN]->(f:Folder)
            WHERE toLower(f.name) CONTAINS $name
            RETURN DISTINCT d.document_id AS doc_id
            """,
            {"name": sanitized, "tid": tenant_id},
        )
        rows = rows1 + rows2

    # Deduplicate while preserving order
    seen: set = set()
    doc_ids: List[str] = []
    for row in rows:
        did = row.get("doc_id")
        if did and did not in seen:
            seen.add(did)
            doc_ids.append(did)
    return doc_ids[:50]


@tree_router.post("/graph/documents-by-entity", response_model=EntityDocumentResponse)
async def documents_by_entity(
    request: EntityDocumentRequest,
    _: bool = Depends(verify_api_key),
):
    """Fast: get document IDs linked to a named entity in the knowledge graph."""
    from app.services.falkordb_client import falkordb_client

    await falkordb_client.initialize()

    doc_ids: List[str] = []

    try:
        doc_ids = await _batch_documents_by_entity(request.entity_name, request.tenant_id, client=falkordb_client)
    except Exception as e:
        logging.getLogger(__name__).error(f"Documents-by-entity query failed: {e}")

    return EntityDocumentResponse(document_ids=doc_ids)


@tree_router.delete("/graph/clear")
async def clear_graph(
    tenant_id: str = Query(..., description="Tenant identifier"),
    _: bool = Depends(verify_api_key),
):
    result = await tenant_knowledge_service.clear_tenant_graph(tenant_id=tenant_id)
    return {"success": result}


# --- GraphRAG: Subgraph Extraction ---

class EntitySeed(BaseModel):
    value: str = Field(..., description="Entity name or value to search")
    type: Optional[str] = Field(None, description="Optional entity type hint (persona, organization)")


class SubgraphRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")
    entities: List[EntitySeed] = Field(..., description="Seed entities for subgraph extraction")
    max_hops: int = Field(2, ge=1, le=3, description="Max traversal depth")
    max_nodes: int = Field(30, ge=5, le=100, description="Max nodes in response")
    include_legal: bool = Field(True, description="Include Law nodes in traversal")
    include_memories: bool = Field(False, description="Include Memory nodes")


@tree_router.post("/graph/subgraph")
async def extract_subgraph(
    request: SubgraphRequest,
    _: bool = Depends(verify_api_key),
):
    """Extract a multi-hop subgraph rooted at query entities (GraphRAG).

    Returns structured nodes and edges for LLM consumption instead of
    flat document IDs. Optionally includes Law nodes for applicable
    legislation.
    """
    import time
    start = time.time()

    from app.services.subgraph_extractor import subgraph_extractor

    entities = [{"value": e.value, "type": e.type} for e in request.entities]

    result = await subgraph_extractor.extract(
        tenant_id=request.tenant_id,
        entities=entities,
        max_hops=request.max_hops,
        max_nodes=request.max_nodes,
        include_legal=request.include_legal,
        include_memories=request.include_memories,
    )

    result["latency_ms"] = int((time.time() - start) * 1000)
    return result
