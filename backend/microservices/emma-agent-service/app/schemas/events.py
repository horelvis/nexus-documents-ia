"""Event schemas for Emma Reactive system.

Events flow through Redis Streams between microservices.
Each event carries a type and flexible payload.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Known event types in the Emma Reactive system."""
    # Document lifecycle
    DOCUMENT_INDEXED = "document.indexed"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"

    # Connector lifecycle
    CONNECTOR_SYNCED = "connector.synced"
    CONNECTOR_ERROR = "connector.error"

    # Knowledge graph
    KNOWLEDGE_GRAPH_UPDATED = "knowledge.graph_updated"

    # Emma internal
    ANALYSIS_COMPLETED = "analysis.completed"
    SESSION_IDLE = "session.idle"
    SCHEDULE_TRIGGERED = "schedule.triggered"

    # Trigger execution
    TRIGGER_EXECUTED = "trigger.executed"
    TRIGGER_FAILED = "trigger.failed"


class EmmaEvent(BaseModel):
    """Core event model for the reactive system.

    All events published to Redis Streams follow this schema.
    The payload is intentionally flexible (Dict[str, Any]) to
    accommodate diverse event producers.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(..., description="Dot-separated event type, e.g. 'document.indexed'")
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_service: Optional[str] = Field(None, description="Service that emitted the event")
    correlation_id: Optional[str] = Field(None, description="For tracing across services")

    def to_stream_dict(self) -> Dict[str, str]:
        """Serialize to flat dict for Redis XADD (values must be strings)."""
        import json
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": json.dumps(self.payload),
            "timestamp": self.timestamp,
            "source_service": self.source_service or "",
            "correlation_id": self.correlation_id or "",
        }

    @classmethod
    def from_stream_dict(cls, data: Dict[bytes, bytes]) -> "EmmaEvent":
        """Deserialize from Redis stream entry (bytes keys/values)."""
        import json
        decoded = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in data.items()
        }
        payload_str = decoded.get("payload", "{}")
        return cls(
            event_id=decoded.get("event_id", ""),
            event_type=decoded.get("event_type", ""),
            payload=json.loads(payload_str) if payload_str else {},
            timestamp=decoded.get("timestamp", ""),
            source_service=decoded.get("source_service") or None,
            correlation_id=decoded.get("correlation_id") or None,
        )


class EventFilter(BaseModel):
    """Filter criteria for matching events against triggers."""
    event_type: str
    payload_filters: Dict[str, Any] = Field(default_factory=dict)

    def matches(self, event: EmmaEvent) -> bool:
        """Check if an event matches this filter."""
        if event.event_type != self.event_type:
            return False
        for key, value in self.payload_filters.items():
            if event.payload.get(key) != value:
                return False
        return True
