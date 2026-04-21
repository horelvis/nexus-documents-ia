"""Database models for Emma Reactive system.

Tables:
    - emma_triggers: Configurable rules connecting events to actions
    - emma_trigger_executions: Audit trail of trigger runs
    - emma_notifications: In-app + multi-channel notifications
    - emma_notification_preferences: Per-user notification settings
    - emma_channels: Multi-channel messaging configuration
    - emma_channel_messages: Message history for channels
    - emma_heartbeat_configs: Per-tenant heartbeat configuration (Phase 6)
    - emma_proactive_insights: Generated proactive insights (Phase 6)
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.db.base_class import Base


# =====================================================================
# Phase 3: Triggers
# =====================================================================

class EmmaTrigger(Base):
    """Configurable rules that connect events/schedules to Emma actions."""
    __tablename__ = "emma_triggers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    trigger_type = Column(String(50), nullable=False)  # event | schedule | condition
    event_pattern = Column(String(255), nullable=True)
    cron_expression = Column(String(255), nullable=True)
    action_type = Column(String(50), nullable=False)  # analyze | notify | workflow
    action_config = Column(JSONB, nullable=False)
    notification_channels = Column(JSONB, nullable=True)
    filters = Column(JSONB, nullable=True)
    priority = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_emma_triggers_active", "is_active"),
        Index("idx_emma_triggers_type", "trigger_type"),
    )


class EmmaTriggerExecution(Base):
    """Audit trail of trigger executions."""
    __tablename__ = "emma_trigger_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger_id = Column(UUID(as_uuid=True), ForeignKey("emma_triggers.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="pending")  # pending | running | completed | failed
    result = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    tokens_used = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_trigger_exec_status", "status"),
    )


# =====================================================================
# Phase 4: Notifications
# =====================================================================

class EmmaNotification(Base):
    """In-app and multi-channel notifications."""
    __tablename__ = "emma_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    notification_type = Column(String(50), nullable=True)
    title = Column(String(255), nullable=True)
    body = Column(Text, nullable=True)
    # Renamed from 'metadata' (reserved in SQLAlchemy Declarative) as part of the
    # multi-tenancy removal refactor; the underlying column name is preserved.
    notification_metadata = Column("metadata", JSONB, nullable=True)
    action_url = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    priority = Column(String(20), default="normal")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "is_read"),
        Index("idx_notifications_created", "created_at"),
    )


class EmmaNotificationPreference(Base):
    """Per-user notification preferences."""
    __tablename__ = "emma_notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    email_enabled = Column(Boolean, default=True)
    in_app_enabled = Column(Boolean, default=True)
    webhook_url = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_notification_prefs_user"),
    )


# =====================================================================
# Phase 5: Multi-Channel
# =====================================================================

class EmmaChannel(Base):
    """Multi-channel messaging configuration."""
    __tablename__ = "emma_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_type = Column(String(50), nullable=False)  # whatsapp | telegram | slack | email
    channel_name = Column(String(255), nullable=True)
    config = Column(JSONB, nullable=False)
    credentials_encrypted = Column(Text, nullable=True)  # Fernet-encrypted
    auto_respond = Column(Boolean, default=True)
    default_agent = Column(String(50), nullable=True)
    routing_rules = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_emma_channels_type", "channel_type"),
    )


class EmmaChannelMessage(Base):
    """Message history for channels."""
    __tablename__ = "emma_channel_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("emma_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(String(20), nullable=False)  # inbound | outbound
    content = Column(Text, nullable=False)
    emma_thread_id = Column(UUID(as_uuid=True), nullable=True)
    external_user_id = Column(String(255), nullable=True)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_channel_msgs_thread", "emma_thread_id"),
        Index("idx_channel_msgs_created", "channel_id", "created_at"),
    )


# =====================================================================
# Phase 6: Heartbeat & Proactive Intelligence
# =====================================================================

class EmmaHeartbeatConfig(Base):
    """Per-tenant configuration for the Heartbeat System.

    Controls how often Emma proactively evaluates tenant context,
    priority thresholds, rate limiting, and delivery preferences.
    """
    __tablename__ = "emma_heartbeat_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Configuration stored as JSONB for flexibility
    # Schema defined in app/schemas/heartbeat.py::HeartbeatConfig
    config = Column(JSONB, nullable=False, default={
        "enabled": True,
        "run_interval_hours": 4,
        "priority_threshold": 0.6,
        "max_insights_per_day": 5,
        "max_insights_per_hour": 2,
        "min_interval_minutes": 30,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "channel_priority": ["in_app", "email", "telegram", "slack"],
        "batch_low_priority": True,
        "digest_hour": 9,
        "contract_expiry_days_warning": 30,
        "enabled_insight_types": [
            "contract_expiration",
            "compliance_alert",
            "risk_alert",
            "anomaly_detected",
            "task_reminder",
        ],
    })

    # Tracking
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    insights_delivered_today = Column(Integer, default=0)
    last_insight_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EmmaProactiveInsight(Base):
    """Proactive insights generated by the Heartbeat System.

    Each insight represents an actionable piece of information that
    Emma has identified as potentially useful for the tenant, such as
    contract expirations, compliance alerts, or activity summaries.
    """
    __tablename__ = "emma_proactive_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Insight content
    insight_type = Column(String(50), nullable=False)  # contract_expiration | compliance_alert | ...
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    details = Column(Text, nullable=True)

    # Scoring
    priority_score = Column(Float, nullable=False)  # 0.0 to 1.0
    urgency = Column(String(20), default="medium")  # critical | high | medium | low
    confidence = Column(Float, default=0.8)  # LLM confidence in the insight

    # Related entities (stored as JSONB arrays)
    related_documents = Column(JSONB, default=[])  # List of document IDs
    suggested_actions = Column(JSONB, default=[])  # List of {action, action_url, priority}

    # LLM reasoning (for debugging/audit)
    reasoning = Column(Text, nullable=True)

    # Status tracking
    status = Column(String(20), default="pending")  # pending | delivered | dismissed | expired | acted_on
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    acted_on_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_insights_status", "status"),
        Index("idx_insights_type", "insight_type"),
        Index("idx_insights_priority", "priority_score"),
        Index("idx_insights_created", "created_at"),
    )
