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
    metadata: Optional[Dict] = None,
    prompt_template: Optional[str] = None,
    agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyze a newly indexed document with Emma AI.

    Triggered by document.indexed events via the trigger engine.
    """
    logger.info(f"Emma analyzing document {document_id}")
    try:
        result = _run_async(_call_emma_background("analyze_document", {
            "document_id": document_id,
            "metadata": metadata or {},
            "prompt_template": prompt_template,
            "agent": agent,
        }))

        # Emit analysis.completed event
        try:
            from worker_app.services.event_publisher import publish_event
            publish_event(
                event_type="analysis.completed",
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
def daily_summary() -> Dict[str, Any]:
    """Generate daily summary."""
    logger.info("Emma generating daily summary")
    try:
        return _run_async(_call_emma_background("daily_summary", {}))
    except Exception as e:
        logger.error(f"Daily summary failed: {e}")
        return {"success": False, "error": str(e)}


@celery_app.task(name="emma.proactive_analysis")
def proactive_analysis(
    analysis_type: str,
    query: str,
    context: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Run a custom proactive analysis via Emma."""
    logger.info(f"Emma proactive analysis: {analysis_type}")
    try:
        return _run_async(_call_emma_background("proactive_analysis", {
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
def heartbeat_check(self) -> Dict[str, Any]:
    """Run a heartbeat evaluation.

    This is the main Heartbeat task that:
    1. Gathers context (documents, contracts, activity)
    2. Evaluates with LLM for actionable insights
    3. Scores and filters by priority threshold
    4. Delivers insights via configured channels

    Scheduled by Celery Beat every 30 minutes.
    """
    logger.info("Emma heartbeat check")
    try:
        result = _run_async(_call_heartbeat_endpoint("run", {
            "force": "false",
        }))

        # Log results
        insights_generated = result.get("insights_generated", 0)
        insights_delivered = result.get("insights_delivered", 0)
        logger.info(
            f"Heartbeat completed: "
            f"{insights_generated} generated, {insights_delivered} delivered"
        )

        return result

    except Exception as exc:
        logger.error(f"Heartbeat check failed: {exc}")
        # Don't retry immediately - will run again on next schedule
        return {"success": False, "error": str(exc)}


@celery_app.task(name="emma.heartbeat_digest")
def heartbeat_digest() -> Dict[str, Any]:
    """Generate and send a daily digest.

    Compiles a summary of:
    - Recent document activity
    - Expiring contracts
    - Pending items requiring attention
    - Low-priority insights batched for delivery

    Scheduled by Celery Beat at the configured digest_hour (default 9 AM).
    """
    logger.info("Emma generating digest")
    try:
        result = _run_async(_call_heartbeat_endpoint("digest", {}))
        return result
    except Exception as e:
        logger.error(f"Digest generation failed: {e}")
        return {"success": False, "error": str(e)}
