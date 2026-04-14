"""Heartbeat Service — Main orchestrator for proactive intelligence.

This is the central service that coordinates:
1. Context gathering from multiple sources
2. LLM-based insight evaluation
3. Priority scoring
4. Rate-limited delivery

Usage:
    from app.services.heartbeat import heartbeat_service

    result = await heartbeat_service.run()
    status = await heartbeat_service.get_status()
    await heartbeat_service.update_config(update)
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.heartbeat import (
    HeartbeatConfig,
    HeartbeatConfigUpdate,
    HeartbeatRunResponse,
    HeartbeatStatusResponse,
)

from .context_gatherer import context_gatherer
from .delivery_manager import delivery_manager
from .insight_evaluator import insight_evaluator
from .priority_scorer import priority_scorer

logger = logging.getLogger(__name__)

# Single-tenant deployment — Redis keys for heartbeat state are global.
HEARTBEAT_CONFIG_KEY = "emma:heartbeat:config"
HEARTBEAT_DELIVERY_KEY = "emma:heartbeat:delivery"
INSIGHTS_LIST_KEY = "emma:insights:list"
INSIGHT_KEY_PREFIX = "emma:insights"

# Legacy tenant placeholder passed to collaborators that still accept the arg
# (context_gatherer, delivery_manager, priority_scorer, insight_evaluator).
# Will be dropped when those modules are refactored in Plan 5.
_LEGACY_TENANT_PLACEHOLDER = ""


class HeartbeatService:
    """Orchestrates the Heartbeat System for proactive intelligence."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
        return self._redis

    async def close(self):
        """Clean up resources."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        await context_gatherer.close()
        await delivery_manager.close()

    # ─────────────────────────────────────────────────────────────────
    # Main Entry Point
    # ─────────────────────────────────────────────────────────────────

    async def run(
        self,
        force: bool = False,
    ) -> HeartbeatRunResponse:
        """Run a heartbeat evaluation.

        Args:
            force: If True, bypass interval checks

        Returns:
            HeartbeatRunResponse with results
        """
        now = datetime.now(timezone.utc)

        # Get configuration
        config = await self.get_config()

        if not config.enabled and not force:
            return HeartbeatRunResponse(
                tenant_id=_LEGACY_TENANT_PLACEHOLDER,
                success=False,
                error="Heartbeat is disabled",
            )

        # Check if enough time has passed since last run
        if not force:
            should_run, reason = await self._should_run(config)
            if not should_run:
                return HeartbeatRunResponse(
                    tenant_id=_LEGACY_TENANT_PLACEHOLDER,
                    success=False,
                    error=reason,
                )

        logger.info("Running heartbeat")

        try:
            # 1. Gather context
            context = await context_gatherer.gather(_LEGACY_TENANT_PLACEHOLDER)

            # 2. Evaluate with LLM (enabled_insight_types are already strings)
            evaluation = await insight_evaluator.evaluate(
                context, config.enabled_insight_types
            )

            if evaluation.no_action_needed:
                await self._update_run_timestamp(now, config)
                return HeartbeatRunResponse(
                    tenant_id=_LEGACY_TENANT_PLACEHOLDER,
                    success=True,
                    insights_generated=0,
                    insights_delivered=0,
                    context_summary={
                        "total_documents": context.total_documents,
                        "documents_indexed_24h": len(context.documents_indexed_24h),
                        "contracts_expiring_7d": len(context.contracts_expiring_7d),
                        "overall_assessment": evaluation.overall_assessment,
                    },
                )

            # 3. Convert candidates to insights
            insight_candidates = insight_evaluator.candidates_to_insights(
                evaluation.insights, _LEGACY_TENANT_PLACEHOLDER
            )

            # 4. Score and filter by priority
            scored_insights = priority_scorer.score_insights(
                insight_candidates, context, config.type_priorities
            )
            filtered_insights = priority_scorer.filter_by_threshold(
                scored_insights, config.priority_threshold
            )

            # 5. Deliver (with rate limiting)
            delivered, deferred = await delivery_manager.deliver_insights(
                filtered_insights, config, _LEGACY_TENANT_PLACEHOLDER
            )

            # 6. Update run timestamp
            await self._update_run_timestamp(now, config)

            return HeartbeatRunResponse(
                tenant_id=_LEGACY_TENANT_PLACEHOLDER,
                success=True,
                insights_generated=len(evaluation.insights),
                insights_delivered=len(delivered),
                insights=delivered,
                context_summary={
                    "total_documents": context.total_documents,
                    "documents_indexed_24h": len(context.documents_indexed_24h),
                    "contracts_expiring_7d": len(context.contracts_expiring_7d),
                    "contracts_expiring_30d": len(context.contracts_expiring_30d),
                    "active_users_24h": context.user_activity.active_users_24h,
                    "anomalies_detected": len(context.anomalies),
                    "deferred_insights": len(deferred),
                    "overall_assessment": evaluation.overall_assessment,
                },
            )

        except Exception as e:
            logger.error(f"Heartbeat run failed: {e}", exc_info=True)
            return HeartbeatRunResponse(
                tenant_id=_LEGACY_TENANT_PLACEHOLDER,
                success=False,
                error=str(e),
            )

    async def _should_run(
        self,
        config: HeartbeatConfig,
    ) -> tuple[bool, str]:
        """Check if heartbeat should run based on interval."""
        r = await self._get_redis()

        last_run_str = await r.hget(HEARTBEAT_CONFIG_KEY, "last_run_at")
        if not last_run_str:
            return True, ""

        try:
            last_run = datetime.fromisoformat(last_run_str)
            now = datetime.now(timezone.utc)
            elapsed_hours = (now - last_run).total_seconds() / 3600

            if elapsed_hours < config.run_interval_hours:
                return False, f"Last run was {elapsed_hours:.1f}h ago, interval is {config.run_interval_hours}h"

            return True, ""

        except Exception:
            return True, ""

    async def _update_run_timestamp(
        self,
        now: datetime,
        config: HeartbeatConfig,
    ):
        """Update the last run timestamp and schedule next run."""
        r = await self._get_redis()

        next_run = now + timedelta(hours=config.run_interval_hours)

        await r.hset(HEARTBEAT_CONFIG_KEY, mapping={
            "last_run_at": now.isoformat(),
            "next_run_at": next_run.isoformat(),
        })

    # ─────────────────────────────────────────────────────────────────
    # Configuration Management
    # ─────────────────────────────────────────────────────────────────

    async def get_config(self) -> HeartbeatConfig:
        """Get heartbeat configuration."""
        r = await self._get_redis()

        config_str = await r.hget(HEARTBEAT_CONFIG_KEY, "config")
        if config_str:
            try:
                config_data = json.loads(config_str)
                return HeartbeatConfig(**config_data)
            except Exception:
                pass

        return HeartbeatConfig()

    async def update_config(
        self,
        update: HeartbeatConfigUpdate,
    ) -> HeartbeatConfig:
        """Update heartbeat configuration."""
        current = await self.get_config()

        # Apply updates
        update_dict = update.model_dump(exclude_unset=True)
        current_dict = current.model_dump()
        current_dict.update(update_dict)

        new_config = HeartbeatConfig(**current_dict)

        r = await self._get_redis()
        await r.hset(HEARTBEAT_CONFIG_KEY, "config", json.dumps(new_config.model_dump()))

        return new_config

    async def get_status(self) -> HeartbeatStatusResponse:
        """Get current status of heartbeat."""
        config = await self.get_config()

        r = await self._get_redis()
        data = await r.hgetall(HEARTBEAT_CONFIG_KEY)

        last_run_at = None
        next_run_at = None
        if data.get("last_run_at"):
            try:
                last_run_at = datetime.fromisoformat(data["last_run_at"])
            except Exception:
                pass
        if data.get("next_run_at"):
            try:
                next_run_at = datetime.fromisoformat(data["next_run_at"])
            except Exception:
                pass

        # Get delivery stats
        delivery_data = await r.hgetall(HEARTBEAT_DELIVERY_KEY)

        # Count pending insights
        insights_count = await r.llen(INSIGHTS_LIST_KEY)

        return HeartbeatStatusResponse(
            tenant_id=_LEGACY_TENANT_PLACEHOLDER,
            enabled=config.enabled,
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            insights_pending=insights_count,
            insights_delivered_today=int(delivery_data.get("today_count", 0)),
            config=config,
        )

    # ─────────────────────────────────────────────────────────────────
    # Insight Management
    # ─────────────────────────────────────────────────────────────────

    async def get_insights(
        self,
        status: Optional[str] = None,
        insight_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get insights with optional filtering."""
        insights = await delivery_manager.get_pending_insights(_LEGACY_TENANT_PLACEHOLDER, limit)

        if status:
            insights = [i for i in insights if i.get("status") == status]
        if insight_type:
            insights = [i for i in insights if i.get("insight_type") == insight_type]

        return insights

    async def update_insight_status(
        self,
        insight_id: str,
        status: str,
    ) -> bool:
        """Update the status of an insight."""
        r = await self._get_redis()
        key = f"{INSIGHT_KEY_PREFIX}:{insight_id}"

        raw = await r.get(key)
        if not raw:
            return False

        data = json.loads(raw)
        data["status"] = status

        now = datetime.now(timezone.utc)
        if status == "dismissed":
            data["dismissed_at"] = now.isoformat()
        elif status == "acted_on":
            data["acted_on_at"] = now.isoformat()

        # Preserve remaining TTL
        ttl = await r.ttl(key)
        if ttl > 0:
            await r.set(key, json.dumps(data), ex=ttl)
        else:
            await r.set(key, json.dumps(data), ex=settings.heartbeat_insight_ttl_seconds)

        return True

    # ─────────────────────────────────────────────────────────────────
    # Digest Generation
    # ─────────────────────────────────────────────────────────────────

    async def generate_digest(self) -> Dict[str, Any]:
        """Generate a daily digest of insights and activity.

        Typically called by Celery Beat at the configured digest_hour.
        """
        context = await context_gatherer.gather(_LEGACY_TENANT_PLACEHOLDER)

        digest: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "documents_indexed_24h": len(context.documents_indexed_24h),
                "total_documents": context.total_documents,
                "contracts_expiring_7d": len(context.contracts_expiring_7d),
                "contracts_expiring_30d": len(context.contracts_expiring_30d),
                "active_users_24h": context.user_activity.active_users_24h,
                "total_queries_24h": context.user_activity.total_queries_24h,
                "anomalies_detected": len(context.anomalies),
            },
            "highlights": [],
            "action_items": [],
        }

        if context.contracts_expiring_7d:
            for c in context.contracts_expiring_7d[:3]:
                digest["highlights"].append(
                    f"Contrato '{c.title}' vence en {c.days_until_expiry} días"
                )

        if context.documents_indexed_24h:
            count = len(context.documents_indexed_24h)
            digest["highlights"].append(f"{count} documentos indexados en las últimas 24h")

        if context.anomalies:
            digest["highlights"].append(
                f"{len(context.anomalies)} anomalías detectadas requieren revisión"
            )

        if context.stale_analyses_7d > 0:
            digest["action_items"].append(
                f"{context.stale_analyses_7d} análisis pendientes por más de 7 días"
            )

        if context.pending_signatures > 0:
            digest["action_items"].append(
                f"{context.pending_signatures} firmas pendientes"
            )

        return digest


# Global singleton
heartbeat_service = HeartbeatService()
