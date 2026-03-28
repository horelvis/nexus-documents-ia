"""
REST endpoints for TrustGraph triple query and stats.

Router prefix: /triples
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.security import verify_api_key
from app.services.falkordb_client import falkordb_client
from app.services.triple_query import TripleQuery
from app.services.triple_store import TripleStore
from app.schemas.triples import (
    BatchNeighborsRequest,
    BatchNeighborsResponse,
    ContextRequest,
    ContextResponse,
    StatsResponse,
    TripleQueryRequest,
    TripleQueryResponse,
    TripleResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/triples",
    tags=["triples"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/query", response_model=TripleQueryResponse)
async def query_triples(request: TripleQueryRequest) -> TripleQueryResponse:
    """Dispatch to the appropriate TripleQuery method based on which fields are set."""
    tq = TripleQuery(falkordb_client)

    rows = []

    if request.subject_uri and request.predicate_uri:
        # by_spo
        rows = await tq.by_spo(
            subject_uri=request.subject_uri,
            predicate_uri=request.predicate_uri,
            user=request.tenant_id,
            collection=request.collection,
        )
    elif request.subject_uri:
        # by_subject
        rows = await tq.by_subject(
            subject_uri=request.subject_uri,
            user=request.tenant_id,
            collection=request.collection,
            limit=request.limit,
        )
    elif request.predicate_uri and request.object_value:
        # by_predicate_object
        rows = await tq.by_predicate_object(
            predicate_uri=request.predicate_uri,
            object_value=request.object_value,
            user=request.tenant_id,
            object_is_node=request.object_is_node,
        )
    elif request.predicate_uri:
        # by_predicate
        rows = await tq.by_predicate(
            predicate_uri=request.predicate_uri,
            user=request.tenant_id,
            collection=request.collection,
            limit=request.limit,
        )
    elif request.object_value and request.object_is_node:
        # by_object_node
        rows = await tq.by_object_node(
            object_uri=request.object_value,
            user=request.tenant_id,
            collection=request.collection,
            limit=request.limit,
        )
    elif request.object_value:
        # by_object_value
        rows = await tq.by_object_value(
            value=request.object_value,
            user=request.tenant_id,
            collection=request.collection,
            limit=request.limit,
        )

    triples = [TripleResult(**row) for row in rows]
    return TripleQueryResponse(triples=triples, count=len(triples))


@router.get("/top-entities")
async def top_entities(
    tenant_id: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
) -> List[Dict[str, Any]]:
    """Return entity URIs with highest degree centrality (most connections).

    Used by the frontend to seed the graph visualization when no specific
    entity is selected.
    """
    tq = TripleQuery(falkordb_client)
    # Find entities with the most Node→Node connections (excluding
    # contradiction edges), prioritizing semantic hubs that produce
    # a rich, connected graph visualization.
    query = (
        "MATCH (n:Node {user: $user})-[r:Rel]-(o:Node {user: $user}) "
        "WHERE n.uri STARTS WITH 'nouxcube://entity/' "
        "AND NOT r.uri ENDS WITH '/contradiction-subject' "
        "WITH n.uri AS uri, count(DISTINCT r) AS degree "
        "ORDER BY degree DESC "
        "LIMIT $limit "
        "RETURN uri, degree"
    )
    params = {"user": tenant_id, "limit": limit}
    rows = await tq._client.execute_cypher(query, params=params)
    return [{"uri": r["uri"], "degree": r["degree"]} for r in rows]


@router.post("/neighbors", response_model=BatchNeighborsResponse)
async def batch_neighbors(request: BatchNeighborsRequest) -> BatchNeighborsResponse:
    """BFS subgraph traversal from one or more seed entity URIs.

    Expands outgoing Node→Node edges hop by hop, up to max_hops rounds,
    collecting at most max_edges triples total.  Predicates matching any
    pattern in exclude_predicates (regex) are omitted from the result.

    Useful for Graph RAG — replaces N individual /triples/query calls with
    a single batched operation.
    """
    tq = TripleQuery(falkordb_client)

    result = await tq.batch_neighbors(
        seed_uris=request.seed_uris,
        user=request.tenant_id,
        collection=request.collection,
        max_hops=request.max_hops,
        max_edges=request.max_edges,
        exclude_predicates=request.exclude_predicates,
    )

    edges = [TripleResult(**e) for e in result["edges"]]
    return BatchNeighborsResponse(
        edges=edges,
        entities_visited=result["entities_visited"],
        hops_used=result["hops_used"],
        count=len(edges),
    )


@router.post("/context", response_model=ContextResponse)
async def build_context(request: ContextRequest) -> ContextResponse:
    """Build an LLM-ready text context from the user's knowledge graph."""
    tq = TripleQuery(falkordb_client)

    context_text = await tq.build_context(user=request.tenant_id, limit=request.limit)
    stats = await tq.get_stats(user=request.tenant_id)

    return ContextResponse(
        success=True,
        context_for_llm=context_text,
        metadata=stats,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    tenant_id: str = Query(...),
    collection: Optional[str] = Query(default=None),
) -> StatsResponse:
    """Return node/literal/rel counts, contradiction count, and entity type breakdown."""
    tq = TripleQuery(falkordb_client)

    stats = await tq.get_stats(user=tenant_id, collection=collection)

    # Count contradiction nodes (URI starts with nouxcube://contradiction/)
    contradiction_query = (
        "MATCH (n:Node {user: $user}) "
        "WHERE n.uri STARTS WITH 'nouxcube://contradiction/' "
        "RETURN count(n) AS cnt"
    )
    contradiction_rows = await falkordb_client.execute_cypher(
        contradiction_query, params={"user": tenant_id}
    )
    contradictions = int(contradiction_rows[0]["cnt"]) if contradiction_rows else 0

    # Entity type breakdown via core/type predicate
    from app.services.uri_builder import URIBuilder

    type_pred_uri = URIBuilder.predicate("core", "type")
    type_query = (
        "MATCH (s:Node {user: $user})"
        "-[r:Rel {uri: $type_pred}]->(o:Literal {user: $user}) "
        "RETURN o.value AS entity_type, count(s) AS cnt "
        "ORDER BY cnt DESC"
    )
    col_params = {"user": tenant_id, "type_pred": type_pred_uri}
    if collection:
        col_params["collection"] = collection
    type_rows = await falkordb_client.execute_cypher(type_query, params=col_params)
    entity_types = {
        row["entity_type"]: int(row["cnt"])
        for row in type_rows
        if row.get("entity_type")
    }

    return StatsResponse(
        nodes=stats["nodes"],
        literals=stats["literals"],
        rels=stats["rels"],
        contradictions=contradictions,
        entity_types=entity_types,
    )


@router.delete("/clear")
async def clear_tenant(tenant_id: str = Query(...)) -> dict:
    """Delete all triples for a given tenant. Returns deleted node count."""
    # Count before deletion
    count_query = (
        "MATCH (n) WHERE (n:Node OR n:Literal) AND n.user = $user RETURN count(n) AS cnt"
    )
    count_rows = await falkordb_client.execute_cypher(
        count_query, params={"user": tenant_id}
    )
    deleted = int(count_rows[0]["cnt"]) if count_rows else 0

    ts = TripleStore(falkordb_client)
    await ts.clear_tenant(user=tenant_id)

    return {"success": True, "deleted": deleted}
