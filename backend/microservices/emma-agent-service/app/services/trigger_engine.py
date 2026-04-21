"""Trigger Engine — Evaluates events against triggers and dispatches actions.

The engine:
1. Receives events from the event listener
2. Queries active triggers
3. Matches events against trigger patterns
4. Dispatches matching actions (analyze, notify, workflow)
5. Records execution results

Pattern syntax: "event_type:key1=value1,key2=value2"
  - "document.indexed" → matches all document.indexed events
  - "document.indexed:collection=contracts" → matches only contracts collection
  - "connector.synced:status=healthy" → matches healthy syncs
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.events import EmmaEvent

logger = logging.getLogger(__name__)

# Redis keys for trigger storage (single-tenant deployment — no tenant segment)
TRIGGERS_KEY_PREFIX = "emma:triggers"
EXECUTIONS_KEY_PREFIX = "emma:trigger_executions"
TRIGGERS_INDEX_KEY = f"{TRIGGERS_KEY_PREFIX}:index"


def parse_event_pattern(pattern: str) -> Tuple[str, Dict[str, str]]:
    """Parse 'event_type:key=val,key=val' into (event_type, filters)."""
    if ":" not in pattern:
        return pattern.strip(), {}

    event_type, filter_str = pattern.split(":", 1)
    filters = {}
    for pair in filter_str.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            filters[k.strip()] = v.strip()
    return event_type.strip(), filters


def event_matches_pattern(event: EmmaEvent, pattern: str) -> bool:
    """Check if an event matches a trigger's event_pattern."""
    expected_type, filters = parse_event_pattern(pattern)

    if event.event_type != expected_type:
        return False

    for key, value in filters.items():
        payload_value = event.payload.get(key)
        if payload_value is None:
            return False
        # Support list membership (e.g., tags=labor matches ["labor", "hr"])
        if isinstance(payload_value, list):
            if value not in payload_value:
                return False
        elif str(payload_value) != value:
            return False

    return True


class TriggerEngine:
    """Evaluates events against triggers and dispatches actions."""

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
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    # ── Trigger CRUD (Redis-backed) ──────────────────────────────────

    async def create_trigger(self, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new trigger."""
        r = await self._get_redis()
        trigger_id = str(uuid.uuid4())
        trigger = {
            "id": trigger_id,
            **trigger_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        key = f"{TRIGGERS_KEY_PREFIX}:{trigger_id}"
        await r.set(key, json.dumps(trigger))
        await r.sadd(TRIGGERS_INDEX_KEY, trigger_id)
        logger.info(f"Created trigger '{trigger_data.get('name')}' [{trigger_id}]")
        return trigger

    async def get_trigger(self, trigger_id: str) -> Optional[Dict[str, Any]]:
        r = await self._get_redis()
        data = await r.get(f"{TRIGGERS_KEY_PREFIX}:{trigger_id}")
        return json.loads(data) if data else None

    async def list_triggers(self) -> List[Dict[str, Any]]:
        r = await self._get_redis()
        trigger_ids = await r.smembers(TRIGGERS_INDEX_KEY)
        triggers = []
        for tid in trigger_ids:
            data = await r.get(f"{TRIGGERS_KEY_PREFIX}:{tid}")
            if data:
                triggers.append(json.loads(data))
        return sorted(triggers, key=lambda t: t.get("priority", 5))

    async def update_trigger(self, trigger_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        trigger = await self.get_trigger(trigger_id)
        if not trigger:
            return None
        trigger.update(updates)
        r = await self._get_redis()
        await r.set(f"{TRIGGERS_KEY_PREFIX}:{trigger_id}", json.dumps(trigger))
        return trigger

    async def delete_trigger(self, trigger_id: str) -> bool:
        r = await self._get_redis()
        deleted = await r.delete(f"{TRIGGERS_KEY_PREFIX}:{trigger_id}")
        await r.srem(TRIGGERS_INDEX_KEY, trigger_id)
        return deleted > 0

    # ── Event Evaluation ─────────────────────────────────────────────

    async def evaluate_event(self, event: EmmaEvent):
        """Evaluate an event against all active triggers."""
        triggers = await self.list_triggers()
        matched = 0

        for trigger in triggers:
            if not trigger.get("is_active", True):
                continue
            if trigger.get("trigger_type") != "event":
                continue

            pattern = trigger.get("event_pattern", "")
            if not pattern:
                continue

            if event_matches_pattern(event, pattern):
                matched += 1
                await self._execute_trigger(trigger, event)

        if matched > 0:
            logger.info(f"Event {event.event_type} matched {matched} trigger(s)")

    async def _execute_trigger(self, trigger: Dict[str, Any], event: EmmaEvent):
        """Execute a matched trigger's action."""
        execution_id = str(uuid.uuid4())
        trigger_id = trigger["id"]

        # Record execution start
        execution = {
            "id": execution_id,
            "trigger_id": trigger_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "event": event.model_dump(),
        }
        r = await self._get_redis()
        exec_key = f"{EXECUTIONS_KEY_PREFIX}:{execution_id}"
        await r.set(exec_key, json.dumps(execution), ex=86400)  # TTL 24h

        try:
            action_type = trigger.get("action_type", "analyze")
            action_config = trigger.get("action_config", {})

            if action_type == "analyze":
                result = await self._dispatch_analyze(event, action_config)
            elif action_type == "notify":
                result = await self._dispatch_notify(event, trigger)
            elif action_type == "workflow":
                result = await self._dispatch_workflow(event, action_config)
            else:
                result = {"error": f"Unknown action type: {action_type}"}

            execution["status"] = "completed"
            execution["result"] = result
            execution["completed_at"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            logger.error(f"Trigger execution failed [{trigger_id}]: {e}", exc_info=True)
            execution["status"] = "failed"
            execution["result"] = {"error": str(e)}
            execution["completed_at"] = datetime.now(timezone.utc).isoformat()

        await r.set(exec_key, json.dumps(execution), ex=86400)

        # Also notify via notification channels if configured
        channels = trigger.get("notification_channels", [])
        if channels and execution["status"] == "completed":
            await self._send_notifications(trigger, execution, channels)

    async def _dispatch_analyze(self, event: EmmaEvent, config: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch an analyze action via Emma Background Service."""
        from app.services.emma_background_service import emma_background_service
        return await emma_background_service.analyze_document(
            document_id=event.payload.get("doc_id", ""),
            prompt_template=config.get("prompt_template"),
            agent=config.get("agent"),
            metadata=event.payload,
        )

    async def _dispatch_notify(self, event: EmmaEvent, trigger: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a notification action."""
        try:
            from app.services.notification_service import notification_service
            await notification_service.send_trigger_notification(
                trigger_name=trigger.get("name", ""),
                event=event,
                channels=trigger.get("notification_channels", ["in_app"]),
            )
            return {"notified": True}
        except ImportError:
            logger.debug("Notification service not available yet")
            return {"notified": False, "reason": "notification_service_not_available"}

    async def _dispatch_workflow(self, event: EmmaEvent, config: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch a workflow action."""
        from app.services.emma_background_service import emma_background_service
        return await emma_background_service.proactive_analysis(
            analysis_type=config.get("workflow_type", "custom"),
            query=config.get("query", ""),
            context={"event": event.model_dump(), **config},
        )

    async def _send_notifications(
        self,
        trigger: Dict[str, Any],
        execution: Dict[str, Any],
        channels: List[str],
    ):
        """Send notifications for completed trigger executions."""
        try:
            from app.services.notification_service import notification_service
            await notification_service.send_trigger_result(
                trigger_name=trigger.get("name", ""),
                execution=execution,
                channels=channels,
            )
        except ImportError:
            logger.debug("Notification service not available yet (Phase 4)")
        except Exception as e:
            logger.warning(f"Failed to send trigger notification: {e}")

    # ── Execution History ────────────────────────────────────────────

    async def list_executions(
        self, trigger_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List recent trigger executions."""
        r = await self._get_redis()
        pattern = f"{EXECUTIONS_KEY_PREFIX}:*"
        executions = []
        async for key in r.scan_iter(match=pattern, count=100):
            data = await r.get(key)
            if data:
                ex = json.loads(data)
                if trigger_id and ex.get("trigger_id") != trigger_id:
                    continue
                executions.append(ex)
        # Sort by started_at descending
        executions.sort(key=lambda e: e.get("started_at", ""), reverse=True)
        return executions[:limit]


# Global singleton
trigger_engine = TriggerEngine()
