"""Pydantic schemas for the Emma Trigger system."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    EVENT = "event"
    SCHEDULE = "schedule"
    CONDITION = "condition"


class ActionType(str, Enum):
    ANALYZE = "analyze"
    NOTIFY = "notify"
    WORKFLOW = "workflow"


class TriggerStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Request/Response schemas ──────────────────────────────────────

class TriggerCreate(BaseModel):
    name: str = Field(..., max_length=255)
    trigger_type: TriggerType
    event_pattern: Optional[str] = Field(
        None,
        description="Event matching pattern, e.g. 'document.indexed:collection=contracts,tags=labor'"
    )
    cron_expression: Optional[str] = Field(None, description="Cron schedule, e.g. '0 9 * * 1'")
    action_type: ActionType
    action_config: Dict[str, Any] = Field(
        ...,
        description="Action configuration: {agent, prompt_template, ...}"
    )
    notification_channels: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    priority: int = Field(default=5, ge=1, le=10)
    is_active: bool = True


class TriggerUpdate(BaseModel):
    name: Optional[str] = None
    event_pattern: Optional[str] = None
    cron_expression: Optional[str] = None
    action_config: Optional[Dict[str, Any]] = None
    notification_channels: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class TriggerResponse(BaseModel):
    id: str
    name: str
    trigger_type: TriggerType
    event_pattern: Optional[str] = None
    cron_expression: Optional[str] = None
    action_type: ActionType
    action_config: Dict[str, Any]
    notification_channels: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    priority: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TriggerExecutionResponse(BaseModel):
    id: str
    trigger_id: str
    status: TriggerStatus
    result: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tokens_used: Optional[int] = None

    class Config:
        from_attributes = True


class TriggerListResponse(BaseModel):
    triggers: List[TriggerResponse]
    total: int
