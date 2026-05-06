"""API endpoints for knowledge graph report assembly."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_api_key
from app.schemas.reports import AssembleRequest, AssembleResponse
from app.services.falkordb_client import falkordb_client
from app.services.graph_assembler import GraphAssembler
from app.services.template_executor import TemplateExecutor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/graph",
    tags=["reports"],
    dependencies=[Depends(verify_api_key)],
)

_assembler: GraphAssembler | None = None


def _get_assembler() -> GraphAssembler:
    global _assembler
    if _assembler is None:
        _assembler = GraphAssembler(falkordb_client, TemplateExecutor())
    return _assembler


@router.post("/assemble", response_model=AssembleResponse)
async def assemble_graph(request: AssembleRequest):
    """Assemble graph data for a knowledge report."""
    t0 = time.monotonic()

    try:
        assembler = _get_assembler()
        # Multi-role ACL filtering is applied in a later wave; for now we
        # resolve to the EVERYONE sentinel that every write uses.
        result = await assembler.assemble(
            entity_uri=request.entity_uri,
            report_type=request.report_type,
            collection=request.collection,
        )
    except Exception as exc:
        logger.error("Graph assembly failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Assembly failed: {exc}")

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    return AssembleResponse(assembled=result, elapsed_ms=elapsed_ms)
