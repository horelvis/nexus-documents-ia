"""Triggers API — CRUD for Emma Reactive triggers.

Endpoints:
    POST   /triggers         — Create trigger
    GET    /triggers         — List triggers
    GET    /triggers/{id}    — Get trigger details
    PATCH  /triggers/{id}    — Update trigger
    DELETE /triggers/{id}    — Delete trigger
    GET    /triggers/{id}/executions — List execution history
"""
import logging

from fastapi import APIRouter, HTTPException, Query

from app.schemas.triggers import (
    TriggerCreate,
    TriggerUpdate,
    TriggerResponse,
    TriggerListResponse,
)
from app.services.trigger_engine import trigger_engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/triggers", response_model=TriggerResponse)
async def create_trigger(
    body: TriggerCreate,
):
    """Create a new Emma reactive trigger."""
    trigger = await trigger_engine.create_trigger(
        trigger_data=body.model_dump(),
    )
    return TriggerResponse(**trigger)


@router.get("/triggers", response_model=TriggerListResponse)
async def list_triggers():
    """List all triggers."""
    triggers = await trigger_engine.list_triggers()
    return TriggerListResponse(
        triggers=[TriggerResponse(**t) for t in triggers],
        total=len(triggers),
    )


@router.get("/triggers/{trigger_id}", response_model=TriggerResponse)
async def get_trigger(
    trigger_id: str,
):
    """Get a specific trigger."""
    trigger = await trigger_engine.get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return TriggerResponse(**trigger)


@router.patch("/triggers/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    trigger_id: str,
    body: TriggerUpdate,
):
    """Update a trigger."""
    updates = body.model_dump(exclude_unset=True)
    trigger = await trigger_engine.update_trigger(trigger_id, updates)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return TriggerResponse(**trigger)


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: str,
):
    """Delete a trigger."""
    deleted = await trigger_engine.delete_trigger(trigger_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return {"deleted": True}


@router.get("/triggers/{trigger_id}/executions")
async def list_executions(
    trigger_id: str,
    limit: int = Query(default=50, le=200),
):
    """List execution history for a trigger."""
    executions = await trigger_engine.list_executions(
        trigger_id=trigger_id,
        limit=limit,
    )
    return {"executions": executions, "total": len(executions)}
