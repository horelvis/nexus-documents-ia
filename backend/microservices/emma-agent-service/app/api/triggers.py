"""Triggers API — CRUD for Emma Reactive triggers.

Endpoints:
    POST   /triggers         — Create trigger
    GET    /triggers         — List triggers for tenant
    GET    /triggers/{id}    — Get trigger details
    PATCH  /triggers/{id}    — Update trigger
    DELETE /triggers/{id}    — Delete trigger
    GET    /triggers/{id}/executions — List execution history
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.core.config import settings
from app.schemas.triggers import (
    TriggerCreate,
    TriggerUpdate,
    TriggerResponse,
    TriggerListResponse,
    TriggerExecutionResponse,
)
from app.services.trigger_engine import trigger_engine

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_tenant_id(
    x_tenant_id: Optional[str] = Header(None),
) -> str:
    """Extract tenant ID from header or use default for single-tenant."""
    if x_tenant_id:
        return x_tenant_id
    if settings.single_tenant_mode:
        return settings.default_tenant_id
    raise HTTPException(status_code=400, detail="X-Tenant-ID header required")


@router.post("/triggers", response_model=TriggerResponse)
async def create_trigger(
    body: TriggerCreate,
    x_tenant_id: Optional[str] = Header(None),
):
    """Create a new Emma reactive trigger."""
    tenant_id = _get_tenant_id(x_tenant_id)
    trigger = await trigger_engine.create_trigger(
        tenant_id=tenant_id,
        trigger_data=body.model_dump(),
    )
    return TriggerResponse(**trigger)


@router.get("/triggers", response_model=TriggerListResponse)
async def list_triggers(
    x_tenant_id: Optional[str] = Header(None),
):
    """List all triggers for the tenant."""
    tenant_id = _get_tenant_id(x_tenant_id)
    triggers = await trigger_engine.list_triggers(tenant_id)
    return TriggerListResponse(
        triggers=[TriggerResponse(**t) for t in triggers],
        total=len(triggers),
    )


@router.get("/triggers/{trigger_id}", response_model=TriggerResponse)
async def get_trigger(
    trigger_id: str,
    x_tenant_id: Optional[str] = Header(None),
):
    """Get a specific trigger."""
    tenant_id = _get_tenant_id(x_tenant_id)
    trigger = await trigger_engine.get_trigger(tenant_id, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return TriggerResponse(**trigger)


@router.patch("/triggers/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    trigger_id: str,
    body: TriggerUpdate,
    x_tenant_id: Optional[str] = Header(None),
):
    """Update a trigger."""
    tenant_id = _get_tenant_id(x_tenant_id)
    updates = body.model_dump(exclude_unset=True)
    trigger = await trigger_engine.update_trigger(tenant_id, trigger_id, updates)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return TriggerResponse(**trigger)


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: str,
    x_tenant_id: Optional[str] = Header(None),
):
    """Delete a trigger."""
    tenant_id = _get_tenant_id(x_tenant_id)
    deleted = await trigger_engine.delete_trigger(tenant_id, trigger_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"deleted": True}


@router.get("/triggers/{trigger_id}/executions")
async def list_executions(
    trigger_id: str,
    limit: int = Query(default=50, le=200),
    x_tenant_id: Optional[str] = Header(None),
):
    """List execution history for a trigger."""
    tenant_id = _get_tenant_id(x_tenant_id)
    executions = await trigger_engine.list_executions(
        tenant_id=tenant_id,
        trigger_id=trigger_id,
        limit=limit,
    )
    return {"executions": executions, "total": len(executions)}
