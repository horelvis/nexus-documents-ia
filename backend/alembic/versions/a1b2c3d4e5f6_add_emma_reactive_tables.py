"""add emma reactive tables

Revision ID: a1b2c3d4e5f6
Revises: 20260127_indexing_duration
Create Date: 2026-02-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '20260127_indexing_duration'
branch_labels = None
depends_on = None


def upgrade():
    # ── Phase 3: Triggers ────────────────────────────────────────
    op.create_table(
        'emma_triggers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('trigger_type', sa.String(50), nullable=False),
        sa.Column('event_pattern', sa.String(255), nullable=True),
        sa.Column('cron_expression', sa.String(255), nullable=True),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('action_config', JSONB, nullable=False),
        sa.Column('notification_channels', JSONB, nullable=True),
        sa.Column('filters', JSONB, nullable=True),
        sa.Column('priority', sa.Integer(), server_default='5'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_emma_triggers_tenant_active', 'emma_triggers', ['tenant_id', 'is_active'])
    op.create_index('idx_emma_triggers_type', 'emma_triggers', ['trigger_type'])

    op.create_table(
        'emma_trigger_executions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('trigger_id', UUID(as_uuid=True), sa.ForeignKey('emma_triggers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('result', JSONB, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
    )
    op.create_index('idx_trigger_exec_trigger', 'emma_trigger_executions', ['trigger_id'])
    op.create_index('idx_trigger_exec_status', 'emma_trigger_executions', ['tenant_id', 'status'])

    # ── Phase 4: Notifications ───────────────────────────────────
    op.create_table(
        'emma_notifications',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('notification_type', sa.String(50), nullable=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('action_url', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default='false'),
        sa.Column('priority', sa.String(20), server_default="'normal'"),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_notifications_user_unread', 'emma_notifications', ['user_id', 'is_read'])
    op.create_index('idx_notifications_tenant_created', 'emma_notifications', ['tenant_id', 'created_at'])

    op.create_table(
        'emma_notification_preferences',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), server_default='true'),
        sa.Column('in_app_enabled', sa.Boolean(), server_default='true'),
        sa.Column('webhook_url', sa.Text(), nullable=True),
        sa.UniqueConstraint('tenant_id', 'user_id', name='uq_notification_prefs_tenant_user'),
    )

    # ── Phase 5: Multi-Channel ───────────────────────────────────
    op.create_table(
        'emma_channels',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('channel_type', sa.String(50), nullable=False),
        sa.Column('channel_name', sa.String(255), nullable=True),
        sa.Column('config', JSONB, nullable=False),
        sa.Column('credentials_encrypted', sa.Text(), nullable=True),
        sa.Column('auto_respond', sa.Boolean(), server_default='true'),
        sa.Column('default_agent', sa.String(50), nullable=True),
        sa.Column('routing_rules', JSONB, nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_emma_channels_tenant_type', 'emma_channels', ['tenant_id', 'channel_type'])

    op.create_table(
        'emma_channel_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('channel_id', UUID(as_uuid=True), sa.ForeignKey('emma_channels.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('direction', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('emma_thread_id', UUID(as_uuid=True), nullable=True),
        sa.Column('external_user_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(50), server_default="'pending'"),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_channel_msgs_thread', 'emma_channel_messages', ['emma_thread_id'])
    op.create_index('idx_channel_msgs_created', 'emma_channel_messages', ['channel_id', 'created_at'])
    op.create_index('idx_channel_msgs_tenant', 'emma_channel_messages', ['tenant_id'])


def downgrade():
    op.drop_table('emma_channel_messages')
    op.drop_table('emma_channels')
    op.drop_table('emma_notification_preferences')
    op.drop_table('emma_notifications')
    op.drop_table('emma_trigger_executions')
    op.drop_table('emma_triggers')
