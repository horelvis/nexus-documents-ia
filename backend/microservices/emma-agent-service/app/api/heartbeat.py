"""Heartbeat API — Endpoints for proactive intelligence management.

Provides:
- Manual heartbeat trigger
- Status and configuration management
- Insight retrieval and status updates
- Digest generation

All endpoints require X-API-Key authentication.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.schemas.heartbeat import (
    HeartbeatConfig,
    HeartbeatConfigUpdate,
    HeartbeatRunResponse,
    HeartbeatStatusResponse,
    InsightListResponse,
    ProactiveInsight,
    ProactiveInsightUpdate,
)
from app.services.heartbeat import heartbeat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/heartbeat", tags=["heartbeat"])


def get_tenant_id(tenant_id: Optional[str] = Query(None)) -> str:
    """Get tenant ID from query param or use default."""
    if tenant_id:
        return tenant_id
    if settings.single_tenant_mode:
        return settings.default_tenant_id
    raise HTTPException(status_code=400, detail="tenant_id is required")


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat Execution
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/run", response_model=HeartbeatRunResponse)
async def run_heartbeat(
    tenant_id: str = Depends(get_tenant_id),
    force: bool = Query(False, description="Bypass interval checks"),
) -> HeartbeatRunResponse:
    """Manually trigger a heartbeat evaluation for a tenant.

    This runs the full heartbeat pipeline:
    1. Gather context from PostgreSQL/Weaviate/Redis
    2. Evaluate with LLM for insights
    3. Score and filter by priority
    4. Deliver insights (respecting rate limits)

    Use `force=true` to bypass the interval check and run immediately.
    """
    return await heartbeat_service.run(tenant_id, force=force)


@router.get("/status", response_model=HeartbeatStatusResponse)
async def get_heartbeat_status(
    tenant_id: str = Depends(get_tenant_id),
) -> HeartbeatStatusResponse:
    """Get current heartbeat status for a tenant.

    Returns:
    - enabled: Whether heartbeat is enabled
    - last_run_at: Timestamp of last run
    - next_run_at: Scheduled next run
    - insights_pending: Number of undelivered insights
    - insights_delivered_today: Count for rate limiting
    - config: Current configuration
    """
    return await heartbeat_service.get_status(tenant_id)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/config", response_model=HeartbeatConfig)
async def get_heartbeat_config(
    tenant_id: str = Depends(get_tenant_id),
) -> HeartbeatConfig:
    """Get heartbeat configuration for a tenant."""
    return await heartbeat_service.get_config(tenant_id)


@router.patch("/config", response_model=HeartbeatConfig)
async def update_heartbeat_config(
    update: HeartbeatConfigUpdate,
    tenant_id: str = Depends(get_tenant_id),
) -> HeartbeatConfig:
    """Update heartbeat configuration for a tenant.

    Partial update — only provided fields are modified.

    Example:
    ```json
    {
        "enabled": false,
        "priority_threshold": 0.7,
        "max_insights_per_day": 3
    }
    ```
    """
    return await heartbeat_service.update_config(tenant_id, update)


# ─────────────────────────────────────────────────────────────────────────────
# Insight Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/insights", response_model=InsightListResponse)
async def list_insights(
    tenant_id: str = Depends(get_tenant_id),
    status: Optional[str] = Query(None, description="Filter by status: pending, delivered, dismissed"),
    insight_type: Optional[str] = Query(None, description="Filter by type: contract_expiration, etc."),
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
) -> InsightListResponse:
    """List proactive insights for a tenant.

    Supports filtering by status and insight type.
    Results are ordered by creation date (newest first).
    """
    insights = await heartbeat_service.get_insights(
        tenant_id=tenant_id,
        status=status,
        insight_type=insight_type,
        limit=limit,
    )

    # Convert dict results to match response model
    insight_objects = []
    for i in insights:
        try:
            # Ensure title is never empty
            if not i.get("title"):
                i["title"] = "Sin título"
            # Pass all available fields (JSON storage preserves everything)
            insight_objects.append(ProactiveInsight(
                **{k: v for k, v in i.items() if k != "tenant_id"},
                tenant_id=tenant_id,
            ))
        except Exception:
            continue

    return InsightListResponse(
        insights=insight_objects,
        total=len(insight_objects),
        page=page,
        page_size=limit,
        has_more=len(insight_objects) == limit,
    )


@router.get("/insights/{insight_id}")
async def get_insight(
    insight_id: str,
    tenant_id: str = Depends(get_tenant_id),
) -> Dict[str, Any]:
    """Get a specific insight by ID."""
    insights = await heartbeat_service.get_insights(tenant_id, limit=100)
    for insight in insights:
        if insight.get("id") == insight_id:
            return insight
    raise HTTPException(status_code=404, detail="Insight not found")


@router.patch("/insights/{insight_id}")
async def update_insight(
    insight_id: str,
    update: ProactiveInsightUpdate,
    tenant_id: str = Depends(get_tenant_id),
) -> Dict[str, str]:
    """Update an insight's status.

    Valid status transitions:
    - pending → delivered (when sent to user)
    - delivered → dismissed (user dismissed)
    - delivered → acted_on (user took action)
    """
    if update.status:
        success = await heartbeat_service.update_insight_status(
            tenant_id=tenant_id,
            insight_id=insight_id,
            status=update.status.value if hasattr(update.status, 'value') else str(update.status),
        )
        if not success:
            raise HTTPException(status_code=404, detail="Insight not found")
        return {"status": "updated", "insight_id": insight_id}
    return {"status": "no changes", "insight_id": insight_id}


@router.post("/insights/{insight_id}/dismiss")
async def dismiss_insight(
    insight_id: str,
    tenant_id: str = Depends(get_tenant_id),
) -> Dict[str, str]:
    """Dismiss an insight (mark as dismissed)."""
    success = await heartbeat_service.update_insight_status(
        tenant_id=tenant_id,
        insight_id=insight_id,
        status="dismissed",
    )
    if not success:
        raise HTTPException(status_code=404, detail="Insight not found")
    return {"status": "dismissed", "insight_id": insight_id}


@router.post("/insights/{insight_id}/acted")
async def mark_insight_acted(
    insight_id: str,
    tenant_id: str = Depends(get_tenant_id),
) -> Dict[str, str]:
    """Mark an insight as acted upon."""
    success = await heartbeat_service.update_insight_status(
        tenant_id=tenant_id,
        insight_id=insight_id,
        status="acted_on",
    )
    if not success:
        raise HTTPException(status_code=404, detail="Insight not found")
    return {"status": "acted_on", "insight_id": insight_id}


# ─────────────────────────────────────────────────────────────────────────────
# Digest
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/digest")
async def get_daily_digest(
    tenant_id: str = Depends(get_tenant_id),
) -> Dict[str, Any]:
    """Generate a daily digest of insights and activity.

    Returns a summary of:
    - Recent document activity
    - Expiring contracts
    - Pending items
    - Anomalies detected
    - Action items
    """
    return await heartbeat_service.generate_digest(tenant_id)
