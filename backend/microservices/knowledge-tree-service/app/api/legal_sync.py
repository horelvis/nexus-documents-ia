"""
Legal Sync API — BKG Phase 6

Endpoints for syncing legal proxy nodes from knowledge_graph_public
to the active sector graph.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import verify_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


class LegalSyncRequest(BaseModel):
    force: bool = Field(False, description="Force re-sync even if recently synced")


class LegalSyncResponse(BaseModel):
    synced_laws: int = 0
    synced_edges: int = 0
    new_laws: int = 0
    updated_laws: int = 0
    elapsed_ms: int = 0


class LegalSyncStatusResponse(BaseModel):
    law_count: int = 0
    last_sync: Optional[str] = None
    graph: str = ""


class LegalLinkRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier")
    document_id: str = Field(..., description="Document identifier")
    text_sample: str = Field(..., description="First ~2000 chars of document text")
    semantic_type: str = Field("", description="Document semantic type")
    domain: str = Field("", description="Document domain")


class LegalLinkResponse(BaseModel):
    edges_created: int = 0
    matches: list = Field(default_factory=list)
    elapsed_ms: int = 0


@router.post("/tree/legal-sync", response_model=LegalSyncResponse)
async def sync_legal_proxies(
    request: Optional[LegalSyncRequest] = None,
    _: bool = Depends(verify_api_key),
):
    """Sync LegalLaw proxy nodes from knowledge_graph_public to sector graph."""
    from app.services.legal_proxy_sync import legal_proxy_sync

    graph_name = settings.age_graph_name
    if not graph_name:
        return LegalSyncResponse()

    force = request.force if request else False
    result = await legal_proxy_sync.sync(graph_name, force=force)
    return LegalSyncResponse(**result)


@router.get("/tree/legal-sync/status", response_model=LegalSyncStatusResponse)
async def legal_sync_status(_: bool = Depends(verify_api_key)):
    """Get current legal proxy sync status."""
    from app.services.legal_proxy_sync import legal_proxy_sync

    graph_name = settings.age_graph_name
    if not graph_name:
        return LegalSyncStatusResponse()

    result = await legal_proxy_sync.get_sync_status(graph_name)
    return LegalSyncStatusResponse(**result)


@router.post("/tree/legal-links/extract-and-store", response_model=LegalLinkResponse)
async def extract_and_store_legal_links(
    request: LegalLinkRequest,
    _: bool = Depends(verify_api_key),
):
    """Extract legal references from document text and create APLICA edges."""
    from app.services.legal_reference_bridge import legal_reference_bridge

    result = await legal_reference_bridge.extract_and_link(
        tenant_id=request.tenant_id,
        document_id=request.document_id,
        text_sample=request.text_sample,
        semantic_type=request.semantic_type,
        domain=request.domain,
    )
    return LegalLinkResponse(**result)
