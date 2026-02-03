"""Celery tasks for Emma Reactive — proactive AI analysis.

These tasks connect the Celery async worker with the Emma Agent Service
for background LangGraph executions (document analysis, summaries, etc.).
"""
import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from worker_app.celery_app import celery_app
from worker_app.core.config import settings

logger = logging.getLogger(__name__)

EMMA_SERVICE_URL = settings.weaviate_service_url.replace(
    "weaviate-service", "emma-agent-service"
).replace(":8000", ":8009") if hasattr(settings, "weaviate_service_url") else "http://emma-agent-service:8009"


def _run_async(coro):
    """Run async coroutine in Celery sync context."""
    return asyncio.run(coro)


async def _call_emma_background(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call Emma Agent Service background endpoint."""
    url = f"{EMMA_SERVICE_URL}/emma/background/{endpoint}"
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            url,
            json=payload,
            headers={"X-API-Key": settings.microservices_api_key},
        )
        response.raise_for_status()
        return response.json()


@celery_app.task(name="emma.analyze_new_document", bind=True, max_retries=2)
def analyze_new_document(
    self,
    document_id: str,
    tenant_id: str,
    metadata: Optional[Dict] = None,
    prompt_template: Optional[str] = None,
    agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyze a newly indexed document with Emma AI.

    Triggered by document.indexed events via the trigger engine.
    """
    logger.info(f"Emma analyzing document {document_id} for tenant {tenant_id}")
    try:
        result = _run_async(_call_emma_background("analyze_document", {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "metadata": metadata or {},
            "prompt_template": prompt_template,
            "agent": agent,
        }))

        # Emit analysis.completed event
        try:
            from worker_app.services.event_publisher import publish_event
            publish_event(
                event_type="analysis.completed",
                tenant_id=tenant_id,
                payload={
                    "document_id": document_id,
                    "success": result.get("success", False),
                    "session_id": result.get("session_id"),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to emit analysis.completed: {e}")

        return result
    except Exception as exc:
        logger.error(f"Emma analyze_new_document failed: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@celery_app.task(name="emma.daily_summary")
def daily_summary(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate daily summary for a tenant (or default tenant)."""
    tid = tenant_id or settings.weaviate_service_url  # fallback; will use default
    # For on-premise single-tenant, use the default tenant
    if not tenant_id:
        import os
        tid = os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")

    logger.info(f"Emma generating daily summary for tenant {tid}")
    try:
        return _run_async(_call_emma_background("daily_summary", {
            "tenant_id": tid,
        }))
    except Exception as e:
        logger.error(f"Daily summary failed: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(name="emma.proactive_analysis")
def proactive_analysis(
    tenant_id: str,
    analysis_type: str,
    query: str,
    context: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Run a custom proactive analysis via Emma."""
    logger.info(f"Emma proactive analysis: {analysis_type} for tenant {tenant_id}")
    try:
        return _run_async(_call_emma_background("proactive_analysis", {
            "tenant_id": tenant_id,
            "analysis_type": analysis_type,
            "query": query,
            "context": context or {},
        }))
    except Exception as e:
        logger.error(f"Proactive analysis failed: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Heartbeat Tasks (Phase 6: Proactive Intelligence)
# =============================================================================

async def _call_heartbeat_endpoint(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Call Emma Agent Service heartbeat endpoint."""
    url = f"{EMMA_SERVICE_URL}/emma/heartbeat/{endpoint}"
    async with httpx.AsyncClient(timeout=300.0) as client:
        if endpoint == "run":
            response = await client.post(
                url,
                params=params,
                headers={"X-API-Key": settings.microservices_api_key},
            )
        else:
            response = await client.get(
                url,
                params=params,
                headers={"X-API-Key": settings.microservices_api_key},
            )
        response.raise_for_status()
        return response.json()


@celery_app.task(name="emma.heartbeat_check", bind=True, max_retries=1)
def heartbeat_check(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Run a heartbeat evaluation for a tenant.

    This is the main Heartbeat task that:
    1. Gathers tenant context (documents, contracts, activity)
    2. Evaluates with LLM for actionable insights
    3. Scores and filters by priority threshold
    4. Delivers insights via configured channels

    Scheduled by Celery Beat every 30 minutes.
    """
    # Use default tenant for single-tenant mode
    if not tenant_id:
        import os
        tenant_id = os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")

    logger.info(f"Emma heartbeat check for tenant {tenant_id}")
    try:
        result = _run_async(_call_heartbeat_endpoint("run", {
            "tenant_id": tenant_id,
            "force": "false",
        }))

        # Log results
        insights_generated = result.get("insights_generated", 0)
        insights_delivered = result.get("insights_delivered", 0)
        logger.info(
            f"Heartbeat completed for {tenant_id}: "
            f"{insights_generated} generated, {insights_delivered} delivered"
        )

        return result

    except Exception as exc:
        logger.error(f"Heartbeat check failed for {tenant_id}: {exc}")
        # Don't retry immediately - will run again on next schedule
        return {"success": False, "error": str(exc), "tenant_id": tenant_id}


@celery_app.task(name="emma.heartbeat_digest")
def heartbeat_digest(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate and send a daily digest for a tenant.

    Compiles a summary of:
    - Recent document activity
    - Expiring contracts
    - Pending items requiring attention
    - Low-priority insights batched for delivery

    Scheduled by Celery Beat at the configured digest_hour (default 9 AM).
    """
    if not tenant_id:
        import os
        tenant_id = os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")

    logger.info(f"Emma generating digest for tenant {tenant_id}")
    try:
        result = _run_async(_call_heartbeat_endpoint("digest", {
            "tenant_id": tenant_id,
        }))
        return result
    except Exception as e:
        logger.error(f"Digest generation failed for {tenant_id}: {e}")
        return {"success": False, "error": str(e), "tenant_id": tenant_id}


@celery_app.task(name="emma.heartbeat_all_tenants")
def heartbeat_all_tenants() -> Dict[str, Any]:
    """Run heartbeat for all active tenants.

    In multi-tenant mode, this iterates over all tenants with heartbeat enabled
    and triggers heartbeat_check for each one.

    In single-tenant mode, this just runs for the default tenant.
    """
    import os

    single_tenant = os.getenv("SINGLE_TENANT_MODE", "true").lower() == "true"

    if single_tenant:
        tenant_id = os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")
        # Call heartbeat_check directly (same process)
        return heartbeat_check(tenant_id)

    # Multi-tenant mode: would need to fetch tenant list from DB
    # For now, just log and return
    logger.info("Multi-tenant heartbeat not yet implemented")
    return {"success": True, "message": "Multi-tenant heartbeat pending implementation"}
