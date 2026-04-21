"""Emma Heartbeat System — Proactive Intelligence Module.

This package implements the Heartbeat System, which enables Emma to
proactively evaluate tenant context and generate actionable insights
without explicit user requests.

Architecture:
    Events (Redis Streams) → Celery Beat Schedule
            ↓
    HeartbeatService (orchestrator)
            ↓
    ContextGatherer → TenantContext
            ↓
    InsightEvaluator (LLM) → List[ProactiveInsight]
            ↓
    PriorityScorer → Scored insights
            ↓
    DeliveryManager → Rate-limited notification dispatch

Usage:
    from app.services.heartbeat import heartbeat_service

    # Manual run
    result = await heartbeat_service.run()

    # Get status
    status = await heartbeat_service.get_status()

    # Update config
    await heartbeat_service.update_config({"enabled": False})
"""

from .heartbeat_service import heartbeat_service, HeartbeatService
from .context_gatherer import context_gatherer, ContextGatherer
from .insight_evaluator import insight_evaluator, InsightEvaluator
from .priority_scorer import priority_scorer, PriorityScorer
from .delivery_manager import delivery_manager, DeliveryManager

__all__ = [
    "heartbeat_service",
    "HeartbeatService",
    "context_gatherer",
    "ContextGatherer",
    "insight_evaluator",
    "InsightEvaluator",
    "priority_scorer",
    "PriorityScorer",
    "delivery_manager",
    "DeliveryManager",
]
