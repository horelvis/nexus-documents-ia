"""
REST endpoints for TrustGraph triple query and stats.

Router prefix: /triples
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from app.core.auth_headers import (
    EVERYONE_ROLE,
    extract_user_id,
    extract_user_roles,
)
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
    TemplateListItem,
    TemplateRequest,
    TemplateResponse,
    TraceSourcesRequest,
    TraceSourcesResponse,
    TripleQueryRequest,
    TripleQueryResponse,
    TripleResult,
)
from app.services.template_executor import TemplateExecutor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/triples",
    tags=["triples"],
    dependencies=[Depends(verify_api_key)],
)


def _graph_scope(user_roles: List[str]) -> str:
    """Resolve the scalar scope token used by the current single-storage model.

    Until the full Node property rename (`user` → `role`) lands, every write
    uses the EVERYONE sentinel and every read queries that same sentinel. The
    multi-role ACL filter (`role IN $allowed_roles`) is handled in a later
    wave; for now we collapse the caller's roles to the EVERYONE bucket so
    the existing Cypher in the service layer keeps working unchanged.
    """
    return EVERYONE_ROLE


@router.post("/query", response_model=TripleQueryResponse)
async def query_triples(request: TripleQueryRequest) -> TripleQueryResponse:
    """Dispatch to the appropriate TripleQuery method based on which fields are set."""
    tq = TripleQuery(falkordb_client)
    scope = _graph_scope(request.user_roles)

    rows = []

    if request.subject_uri and request.predicate_uri:
        # by_spo
        rows = await tq.by_spo(
            subject_uri=request.subject_uri,
            predicate_uri=request.predicate_uri,
            user=scope,
            collection=request.collection,
        )
    elif request.subject_uri:
        # by_subject
        rows = await tq.by_subject(
            subject_uri=request.subject_uri,
            user=scope,
            collection=request.collection,
            limit=request.limit,
        )
    elif request.predicate_uri and request.object_value:
        # by_predicate_object
        rows = await tq.by_predicate_object(
            predicate_uri=request.predicate_uri,
            object_value=request.object_value,
            user=scope,
            object_is_node=request.object_is_node,
        )
    elif request.predicate_uri:
        # by_predicate
        rows = await tq.by_predicate(
            predicate_uri=request.predicate_uri,
            user=scope,
            collection=request.collection,
            limit=request.limit,
        )
    elif request.object_value and request.object_is_node:
        # by_object_node
        rows = await tq.by_object_node(
            object_uri=request.object_value,
            user=scope,
            collection=request.collection,
            limit=request.limit,
        )
    elif request.object_value:
        # by_object_value
        rows = await tq.by_object_value(
            value=request.object_value,
            user=scope,
            collection=request.collection,
            limit=request.limit,
        )

    triples = [TripleResult(**row) for row in rows]
    return TripleQueryResponse(triples=triples, count=len(triples))


@router.get("/top-entities")
async def top_entities(
    limit: int = Query(default=10, ge=1, le=50),
    user_roles: List[str] = Depends(extract_user_roles),
    user_id: Optional[str] = Depends(extract_user_id),
) -> List[Dict[str, Any]]:
    """Return entity URIs with highest degree centrality (most connections).

    Used by the frontend to seed the graph visualization when no specific
    entity is selected.
    """
    tq = TripleQuery(falkordb_client)
    scope = _graph_scope(user_roles)
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
    params = {"user": scope, "limit": limit}
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
        user=_graph_scope(request.user_roles),
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


@router.post("/trace-sources", response_model=TraceSourcesResponse)
async def trace_sources(request: TraceSourcesRequest) -> TraceSourcesResponse:
    """Trace edges back to source document chunks for provenance resolution."""
    tq = TripleQuery(falkordb_client)

    sources = await tq.trace_sources(
        edges=request.edges,
        user=_graph_scope(request.user_roles),
        collection=request.collection,
    )
    return TraceSourcesResponse(sources=sources)


@router.post("/context", response_model=ContextResponse)
async def build_context(request: ContextRequest) -> ContextResponse:
    """Build an LLM-ready text context from the user's knowledge graph."""
    tq = TripleQuery(falkordb_client)
    scope = _graph_scope(request.user_roles)

    context_text = await tq.build_context(user=scope, limit=request.limit)
    stats = await tq.get_stats(user=scope)

    return ContextResponse(
        success=True,
        context_for_llm=context_text,
        metadata=stats,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    collection: Optional[str] = Query(default=None),
    user_roles: List[str] = Depends(extract_user_roles),
    user_id: Optional[str] = Depends(extract_user_id),
) -> StatsResponse:
    """Return node/literal/rel counts, contradiction count, and entity type breakdown."""
    tq = TripleQuery(falkordb_client)
    scope = _graph_scope(user_roles)

    stats = await tq.get_stats(user=scope, collection=collection)

    # Count contradiction nodes (URI starts with nouxcube://contradiction/)
    contradiction_query = (
        "MATCH (n:Node {user: $user}) "
        "WHERE n.uri STARTS WITH 'nouxcube://contradiction/' "
        "RETURN count(n) AS cnt"
    )
    contradiction_rows = await falkordb_client.execute_cypher(
        contradiction_query, params={"user": scope}
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
    col_params = {"user": scope, "type_pred": type_pred_uri}
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
async def clear_graph(
    user_roles: List[str] = Depends(extract_user_roles),
    user_id: Optional[str] = Depends(extract_user_id),
) -> dict:
    """Delete all triples for the current scope. Returns deleted node count."""
    scope = _graph_scope(user_roles)
    # Count before deletion
    count_query = (
        "MATCH (n) WHERE (n:Node OR n:Literal) AND n.user = $user RETURN count(n) AS cnt"
    )
    count_rows = await falkordb_client.execute_cypher(
        count_query, params={"user": scope}
    )
    deleted = int(count_rows[0]["cnt"]) if count_rows else 0

    ts = TripleStore(falkordb_client)
    await ts.clear_tenant(user=scope)

    return {"success": True, "deleted": deleted}


_template_executor = TemplateExecutor()


@router.post("/template", response_model=TemplateResponse)
async def execute_template(request: TemplateRequest) -> TemplateResponse:
    """Execute a named Cypher template with parameters."""
    from fastapi import HTTPException

    try:
        result = await _template_executor.execute(
            name=request.template_name,
            client=falkordb_client,
            user=_graph_scope(request.user_roles),
            collection=request.collection,
            **request.params,
        )
        return TemplateResponse(**result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/templates", response_model=List[TemplateListItem])
async def list_templates() -> List[TemplateListItem]:
    """List all available Cypher templates."""
    return _template_executor.list_templates()
