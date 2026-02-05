"""Heartbeat schemas for Emma Proactive Intelligence.

This module defines the data models for the Heartbeat System, which enables
Emma to proactively evaluate tenant context and generate insights without
explicit user requests — similar to OpenClaw's Heartbeat System.

The system periodically:
1. Gathers context (documents, contracts, user activity)
2. Evaluates with LLM for potential insights
3. Scores and filters insights by priority
4. Delivers through appropriate channels with rate limiting
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Insight Types
# ─────────────────────────────────────────────────────────────────────────────

class InsightType(str, Enum):
    """Types of proactive insights Emma can generate."""

    CONTRACT_EXPIRATION = "contract_expiration"
    """Contract expiring within 30 days."""

    COMPLIANCE_ALERT = "compliance_alert"
    """Detected gap in regulatory compliance."""

    RISK_ALERT = "risk_alert"
    """Risk identified in document analysis."""

    ANOMALY_DETECTED = "anomaly_detected"
    """Duplicate documents, indexing failures, unusual patterns."""

    TASK_REMINDER = "task_reminder"
    """Pending analyses or signatures for >7 days."""

    ACTIVITY_SUMMARY = "activity_summary"
    """Periodic summary of document activity."""

    DOCUMENT_UPDATE = "document_update"
    """Important document has been updated."""

    DEADLINE_APPROACHING = "deadline_approaching"
    """Generic deadline approaching (not contract-specific)."""


class InsightUrgency(str, Enum):
    """Urgency levels for insights."""
    CRITICAL = "critical"  # Requires immediate action
    HIGH = "high"          # Should address today
    MEDIUM = "medium"      # Address this week
    LOW = "low"            # Informational


class InsightStatus(str, Enum):
    """Status of a proactive insight."""
    PENDING = "pending"      # Generated, waiting for delivery
    DELIVERED = "delivered"  # Sent to user via notification
    DISMISSED = "dismissed"  # User dismissed the insight
    EXPIRED = "expired"      # TTL exceeded, no longer relevant
    ACTED_ON = "acted_on"    # User took action based on insight


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat Configuration
# ─────────────────────────────────────────────────────────────────────────────

class HeartbeatConfig(BaseModel):
    """Per-tenant configuration for the Heartbeat System.

    Controls how often the system runs, what priority threshold to use
    for sending notifications, rate limiting, and quiet hours.
    """

    enabled: bool = Field(
        default=True,
        description="Whether heartbeat is enabled for this tenant"
    )

    run_interval_hours: int = Field(
        default=4,
        ge=1,
        le=24,
        description="Hours between heartbeat evaluations"
    )

    priority_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum priority score to generate notification (0.0-1.0)"
    )

    max_insights_per_day: int = Field(
        default=5,
        ge=0,
        le=50,
        description="Maximum insights to deliver per day"
    )

    max_insights_per_hour: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Maximum insights to deliver per hour"
    )

    min_interval_minutes: int = Field(
        default=30,
        ge=5,
        le=180,
        description="Minimum minutes between notifications"
    )

    quiet_hours_start: str = Field(
        default="22:00",
        description="Start of quiet hours (no notifications), format HH:MM"
    )

    quiet_hours_end: str = Field(
        default="08:00",
        description="End of quiet hours, format HH:MM"
    )

    channel_priority: List[str] = Field(
        default=["in_app", "email", "telegram", "slack"],
        description="Ordered list of notification channels"
    )

    email_recipients: List[str] = Field(
        default_factory=list,
        description="List of email addresses to receive heartbeat notifications"
    )

    batch_low_priority: bool = Field(
        default=True,
        description="Batch low-priority insights into daily digest"
    )

    digest_hour: int = Field(
        default=9,
        ge=0,
        le=23,
        description="Hour to send daily digest (0-23)"
    )

    # Contract-specific settings
    contract_expiry_days_warning: int = Field(
        default=30,
        description="Days before expiry to generate contract warnings"
    )

    # Insight type toggles (strings allow dynamic types from Langfuse prompts)
    enabled_insight_types: List[str] = Field(
        default=[
            "contract_expiration",
            "compliance_alert",
            "risk_alert",
            "anomaly_detected",
            "task_reminder",
        ],
        description="Which insight types are enabled for this tenant (extensible via Langfuse)"
    )

    # Configurable priority weights per insight type (merge with defaults)
    type_priorities: Dict[str, float] = Field(
        default={
            "contract_expiration": 0.85,
            "compliance_alert": 0.80,
            "risk_alert": 0.75,
            "deadline_approaching": 0.70,
            "anomaly_detected": 0.60,
            "task_reminder": 0.55,
            "document_update": 0.50,
            "activity_summary": 0.40,
        },
        description="Base priority weights per insight type (0.0-1.0). New types default to 0.50."
    )

    class Config:
        use_enum_values = True


class HeartbeatConfigUpdate(BaseModel):
    """Partial update for heartbeat configuration."""

    enabled: Optional[bool] = None
    run_interval_hours: Optional[int] = Field(None, ge=1, le=24)
    priority_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_insights_per_day: Optional[int] = Field(None, ge=0, le=50)
    max_insights_per_hour: Optional[int] = Field(None, ge=0, le=10)
    min_interval_minutes: Optional[int] = Field(None, ge=5, le=180)
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    channel_priority: Optional[List[str]] = None
    email_recipients: Optional[List[str]] = None
    batch_low_priority: Optional[bool] = None
    digest_hour: Optional[int] = Field(None, ge=0, le=23)
    contract_expiry_days_warning: Optional[int] = None
    enabled_insight_types: Optional[List[str]] = None
    type_priorities: Optional[Dict[str, float]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Tenant Context (gathered data)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentSummary(BaseModel):
    """Summary of a document for context gathering."""
    id: str
    title: str
    collection: Optional[str] = None
    indexed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContractInfo(BaseModel):
    """Contract information for expiration tracking."""
    document_id: str
    title: str
    counterparty: Optional[str] = None
    expiry_date: Optional[datetime] = None
    days_until_expiry: Optional[int] = None
    contract_type: Optional[str] = None


class UserActivityStats(BaseModel):
    """User activity statistics."""
    active_users_24h: int = 0
    total_queries_24h: int = 0
    top_queried_topics: List[str] = Field(default_factory=list)
    queries_by_hour: Dict[str, int] = Field(default_factory=dict)


class AnomalyInfo(BaseModel):
    """Information about detected anomalies."""
    anomaly_type: str  # duplicate, indexing_failure, size_anomaly
    description: str
    document_ids: List[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TenantContext(BaseModel):
    """Aggregated context for a tenant, used by the Heartbeat evaluator.

    This is gathered from PostgreSQL, Weaviate, and Redis before
    being sent to the LLM for insight evaluation.
    """

    tenant_id: str
    gathered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Recent document activity
    documents_indexed_24h: List[DocumentSummary] = Field(default_factory=list)
    documents_indexed_7d: int = 0
    documents_by_collection: Dict[str, int] = Field(default_factory=dict)
    total_documents: int = 0

    # Contract tracking
    contracts_expiring_7d: List[ContractInfo] = Field(default_factory=list)
    contracts_expiring_30d: List[ContractInfo] = Field(default_factory=list)

    # User activity
    user_activity: UserActivityStats = Field(default_factory=UserActivityStats)

    # Pending items
    pending_analyses: int = 0
    pending_signatures: int = 0
    stale_analyses_7d: int = 0  # Analyses pending for >7 days

    # Anomalies
    anomalies: List[AnomalyInfo] = Field(default_factory=list)
    duplicate_documents: int = 0
    indexing_failures_24h: int = 0

    # Last insight delivery (for rate limiting)
    last_insight_delivered_at: Optional[datetime] = None
    insights_delivered_today: int = 0
    insights_delivered_this_hour: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Proactive Insight
# ─────────────────────────────────────────────────────────────────────────────

class SuggestedAction(BaseModel):
    """A suggested action for the user to take."""
    action: str
    action_url: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=5)


class ProactiveInsight(BaseModel):
    """A proactive insight generated by the Heartbeat System.

    This represents an actionable piece of information that Emma
    has identified as potentially useful for the user.
    """

    id: Optional[str] = None
    tenant_id: str

    insight_type: str
    title: str = Field(..., max_length=255)
    summary: str = Field(..., max_length=500)
    details: Optional[str] = None

    # Scoring
    priority_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Priority score from 0.0 (lowest) to 1.0 (highest)"
    )
    urgency: InsightUrgency = InsightUrgency.MEDIUM
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="LLM confidence in the insight validity"
    )

    # Related entities
    related_documents: List[str] = Field(
        default_factory=list,
        description="Document IDs related to this insight"
    )
    suggested_actions: List[SuggestedAction] = Field(default_factory=list)

    # LLM reasoning (for debugging/audit)
    reasoning: Optional[str] = Field(
        None,
        description="LLM's reasoning for generating this insight"
    )

    # Status tracking
    status: InsightStatus = InsightStatus.PENDING
    delivered_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    acted_on_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    class Config:
        use_enum_values = True


class ProactiveInsightCreate(BaseModel):
    """Schema for creating a new insight."""

    tenant_id: str
    insight_type: str
    title: str = Field(..., max_length=255)
    summary: str = Field(..., max_length=500)
    details: Optional[str] = None
    priority_score: float = Field(..., ge=0.0, le=1.0)
    urgency: InsightUrgency = InsightUrgency.MEDIUM
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    related_documents: List[str] = Field(default_factory=list)
    suggested_actions: List[SuggestedAction] = Field(default_factory=list)
    reasoning: Optional[str] = None
    expires_at: Optional[datetime] = None


class ProactiveInsightUpdate(BaseModel):
    """Partial update for an insight."""

    status: Optional[InsightStatus] = None
    delivered_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None
    acted_on_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# API Response Models
# ─────────────────────────────────────────────────────────────────────────────

class HeartbeatStatusResponse(BaseModel):
    """Status of the Heartbeat System for a tenant."""

    tenant_id: str
    enabled: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    insights_pending: int = 0
    insights_delivered_today: int = 0
    config: HeartbeatConfig


class HeartbeatRunResponse(BaseModel):
    """Response from a manual heartbeat run."""

    tenant_id: str
    success: bool
    insights_generated: int = 0
    insights_delivered: int = 0
    insights: List[ProactiveInsight] = Field(default_factory=list)
    context_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class InsightListResponse(BaseModel):
    """Paginated list of insights."""

    insights: List[ProactiveInsight]
    total: int
    page: int = 1
    page_size: int = 20
    has_more: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# LLM Evaluation Types
# ─────────────────────────────────────────────────────────────────────────────

class LLMInsightCandidate(BaseModel):
    """Insight candidate extracted from LLM response.

    This is the raw output from the LLM before priority scoring
    and delivery filtering.
    """

    insight_type: str
    title: str
    summary: str
    urgency: str = "medium"
    confidence: float = 0.8
    related_document_ids: List[str] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)
    reasoning: str = ""


class LLMEvaluationResult(BaseModel):
    """Result from LLM context evaluation."""

    insights: List[LLMInsightCandidate] = Field(default_factory=list)
    overall_assessment: str = ""
    no_action_needed: bool = False
    raw_response: Optional[str] = None
