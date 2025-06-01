"""Add agents and digital signature system

Revision ID: add_agents_system
Revises: [previous_revision]
Create Date: 2024-01-06 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


# revision identifiers, used by Alembic.
revision = 'add_agents_system'
down_revision = None  # Update this with the actual previous revision
branch_labels = None
depends_on = None


def upgrade():
    """Create agents and digital signature tables"""
    
    # Agent Tools table
    op.create_table('agent_tools',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('tool_type', sa.String(50), nullable=False),
        sa.Column('configuration_schema', JSONB, nullable=False),
        sa.Column('requires_admin', sa.Boolean, default=False),
        sa.Column('is_tenant_specific', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # Agents table
    op.create_table('agents',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('configuration', JSONB, nullable=False, default={}),
        sa.Column('tools', ARRAY(sa.String), nullable=False, default=[]),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_public', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # Agent unique constraint
    op.create_unique_constraint('uq_agent_name_tenant', 'agents', ['name', 'tenant_id'])
    
    # Agent Conversations table
    op.create_table('agent_conversations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('context', JSONB, nullable=False, default={}),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # Agent Messages table
    op.create_table('agent_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', UUID(as_uuid=True), sa.ForeignKey('agent_conversations.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('metadata', JSONB, nullable=False, default={}),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False)
    )
    
    # Agent Executions table
    op.create_table('agent_executions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', UUID(as_uuid=True), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('task_type', sa.String(100), nullable=False),
        sa.Column('input_data', JSONB, nullable=False),
        sa.Column('output_data', JSONB, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('execution_time_ms', sa.Integer, nullable=True),
        sa.Column('started_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime, nullable=True)
    )
    
    # Signature Providers table
    op.create_table('signature_providers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('provider_name', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('encrypted_credentials', sa.LargeBinary, nullable=False),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('is_default', sa.Boolean, default=False),
        sa.Column('configuration', JSONB, nullable=False, default={}),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # Signature provider unique constraint
    op.create_unique_constraint('uq_tenant_provider', 'signature_providers', ['tenant_id', 'provider_name'])
    
    # Signature Requests table
    op.create_table('signature_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('provider_id', UUID(as_uuid=True), sa.ForeignKey('signature_providers.id'), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('document_name', sa.String(255), nullable=False),
        sa.Column('document_content', sa.LargeBinary, nullable=True),
        sa.Column('document_url', sa.String(500), nullable=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text, nullable=True),
        sa.Column('signature_type', sa.String(20), default='sequential'),
        sa.Column('status', sa.String(30), default='draft'),
        sa.Column('callback_url', sa.String(500), nullable=True),
        sa.Column('success_url', sa.String(500), nullable=True),
        sa.Column('error_url', sa.String(500), nullable=True),
        sa.Column('metadata', JSONB, nullable=False, default={}),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('sent_at', sa.DateTime, nullable=True),
        sa.Column('completed_at', sa.DateTime, nullable=True),
        sa.Column('expires_at', sa.DateTime, nullable=True)
    )
    
    # Signature Request Signers table
    op.create_table('signature_request_signers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', UUID(as_uuid=True), sa.ForeignKey('signature_requests.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('order', sa.Integer, nullable=False, default=1),
        sa.Column('authentication_method', sa.String(20), default='email'),
        sa.Column('success_url', sa.String(500), nullable=True),
        sa.Column('error_url', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('signing_url', sa.String(500), nullable=True),
        sa.Column('signed_at', sa.DateTime, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True)
    )
    
    # Signature Events table
    op.create_table('signature_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('request_id', UUID(as_uuid=True), sa.ForeignKey('signature_requests.id'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('event_data', JSONB, nullable=False, default={}),
        sa.Column('created_at', sa.DateTime, default=sa.func.now(), nullable=False)
    )
    
    # Create indexes for better performance
    op.create_index('ix_agents_tenant_id', 'agents', ['tenant_id'])
    op.create_index('ix_agents_type', 'agents', ['type'])
    op.create_index('ix_agent_conversations_agent_id', 'agent_conversations', ['agent_id'])
    op.create_index('ix_agent_conversations_user_id', 'agent_conversations', ['user_id'])
    op.create_index('ix_agent_messages_conversation_id', 'agent_messages', ['conversation_id'])
    op.create_index('ix_agent_executions_agent_id', 'agent_executions', ['agent_id'])
    op.create_index('ix_agent_executions_user_id', 'agent_executions', ['user_id'])
    op.create_index('ix_agent_executions_status', 'agent_executions', ['status'])
    op.create_index('ix_signature_providers_tenant_id', 'signature_providers', ['tenant_id'])
    op.create_index('ix_signature_requests_tenant_id', 'signature_requests', ['tenant_id'])
    op.create_index('ix_signature_requests_status', 'signature_requests', ['status'])
    op.create_index('ix_signature_request_signers_request_id', 'signature_request_signers', ['request_id'])
    op.create_index('ix_signature_events_request_id', 'signature_events', ['request_id'])


def downgrade():
    """Drop agents and digital signature tables"""
    
    # Drop indexes
    op.drop_index('ix_signature_events_request_id')
    op.drop_index('ix_signature_request_signers_request_id')
    op.drop_index('ix_signature_requests_status')
    op.drop_index('ix_signature_requests_tenant_id')
    op.drop_index('ix_signature_providers_tenant_id')
    op.drop_index('ix_agent_executions_status')
    op.drop_index('ix_agent_executions_user_id')
    op.drop_index('ix_agent_executions_agent_id')
    op.drop_index('ix_agent_messages_conversation_id')
    op.drop_index('ix_agent_conversations_user_id')
    op.drop_index('ix_agent_conversations_agent_id')
    op.drop_index('ix_agents_type')
    op.drop_index('ix_agents_tenant_id')
    
    # Drop tables in reverse order
    op.drop_table('signature_events')
    op.drop_table('signature_request_signers')
    op.drop_table('signature_requests')
    op.drop_table('signature_providers')
    op.drop_table('agent_executions')
    op.drop_table('agent_messages')
    op.drop_table('agent_conversations')
    op.drop_table('agents')
    op.drop_table('agent_tools')