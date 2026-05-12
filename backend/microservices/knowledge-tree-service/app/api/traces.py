"""
REST endpoints for reasoning-trace persistence (Pieza C of the
TrustGraph Provenance DAG).

Router prefix: /traces

Emma-agent-service POSTs the reasoning trace produced at the SSE
`complete` event to `/traces/persist`, mirroring the Redis 24h-TTL
write into a permanent :Trace subgraph in FalkorDB. The trace links
to the same :Node and :Chunk records visited during ReAct execution,
so cross-trace queries like "every trace that touched X" become
first-class Cypher.

Failure here MUST NOT affect the Emma response — callers are expected
to fire-and-forget and swallow exceptions.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.services.falkordb_client import falkordb_client
from app.services.triple_store import TripleStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/traces",
    tags=["traces"],
    dependencies=[Depends(verify_api_key)],
)


class PersistTraceRequest(BaseModel):
    """Payload mirrors the Redis trace shape written by emma.py at
    the SSE `complete` event."""

    trace_data: Dict[str, Any] = Field(
        ...,
        description=(
            "Trace payload. Required keys: thread_id, message_index. "
            "Optional: total_execution_ms, sources_cited, tools_used, "
            "answer, timeline, evidence_graph."
        ),
    )
    collection: str = Field(
        default="default",
        description="Graph collection scope.",
    )


class PersistTraceResponse(BaseModel):
    ok: bool
    trace_uri: str


@router.post("/persist", response_model=PersistTraceResponse)
async def persist_trace(request: PersistTraceRequest) -> PersistTraceResponse:
    """Materialize a reasoning trace into the FalkorDB graph.

    Idempotent — re-posting the same (thread_id, message_index) merges
    in place. Designed to be called fire-and-forget by emma-agent-service.
    """
    store = TripleStore(falkordb_client)
    try:
        trace_uri = await store.persist_trace(
            trace_data=request.trace_data,
            collection=request.collection,
        )
    except ValueError as exc:
        # Invalid payload shape — caller error.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        # Any FalkorDB or Cypher failure: log + 502 so the caller
        # treats it as an external-store failure (not its own bug).
        logger.exception("persist_trace failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="trace persistence failed",
        ) from exc

    return PersistTraceResponse(ok=True, trace_uri=trace_uri)
