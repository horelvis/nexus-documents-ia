"""Add Emma AI Learning System tables

Revision ID: 20260112_add_emma_learning_system
Revises: 20251215_add_site_guest_shares
Create Date: 2026-01-12

Adds tables for Emma AI real learning capabilities:
- user_learning_profiles: Persistent user preferences and learned patterns
- user_interaction_history: User interaction tracking for preference learning
- knowledge_entities: Extracted knowledge entities from documents
- knowledge_relationships: Relationships between knowledge entities
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '20260112_add_emma_learning_system'
down_revision = '20251215_add_site_guest_shares'
branch_labels = None
depends_on = None


def upgrade():
    # =============================================
    # USER LEARNING PROFILES
    # =============================================
    op.create_table(
        'user_learning_profiles',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),

        # Explicit preferences
        sa.Column('response_style', sa.String(50), nullable=False, server_default='balanced'),
        sa.Column('expertise_level', sa.String(50), nullable=False, server_default='general'),
        sa.Column('preferred_language', sa.String(10), nullable=False, server_default='es'),

        # Learned preferences
        sa.Column('preferred_document_types', JSONB, nullable=False, server_default='[]'),
        sa.Column('preferred_topics', JSONB, nullable=False, server_default='[]'),
        sa.Column('search_patterns', JSONB, nullable=False, server_default='{}'),

        # Engagement metrics
        sa.Column('total_queries', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_document_views', sa.Integer, nullable=False, server_default='0'),
        sa.Column('avg_session_duration_seconds', sa.Integer, nullable=False, server_default='0'),

        # Personalized ranking weights
        sa.Column('ranking_weights', JSONB, nullable=False,
                  server_default='{"recency": 0.3, "frequency": 0.3, "relevance": 0.4}'),

        # Quick access data
        sa.Column('frequent_document_ids', JSONB, nullable=False, server_default='[]'),
        sa.Column('frequent_queries', JSONB, nullable=False, server_default='[]'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'tenant_id', name='uq_user_learning_profile'),
    )

    op.create_index('idx_user_learning_profiles_user', 'user_learning_profiles', ['user_id'])
    op.create_index('idx_user_learning_profiles_tenant', 'user_learning_profiles', ['tenant_id'])

    # =============================================
    # USER INTERACTION HISTORY
    # =============================================
    op.create_table(
        'user_interaction_history',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),

        # Interaction type
        sa.Column('interaction_type', sa.String(50), nullable=False),
        sa.Column('document_id', UUID(as_uuid=True), nullable=True),

        # Context
        sa.Column('query_text', sa.Text, nullable=True),
        sa.Column('intent_detected', sa.String(50), nullable=True),

        # Implicit feedback
        sa.Column('dwell_time_seconds', sa.Integer, nullable=True),
        sa.Column('scroll_depth_percentage', sa.Float, nullable=True),
        sa.Column('actions_taken', JSONB, nullable=False, server_default='[]'),

        # Query result metrics
        sa.Column('results_shown', sa.Integer, nullable=True),
        sa.Column('results_clicked', sa.Integer, nullable=True),
        sa.Column('selected_document_ids', JSONB, nullable=False, server_default='[]'),

        # Explicit feedback
        sa.Column('feedback_rating', sa.Integer, nullable=True),
        sa.Column('feedback_text', sa.Text, nullable=True),

        # Session
        sa.Column('session_id', sa.String(255), nullable=True),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='SET NULL'),
    )

    op.create_index('idx_user_interactions_user_type', 'user_interaction_history', ['user_id', 'interaction_type'])
    op.create_index('idx_user_interactions_tenant_date', 'user_interaction_history', ['tenant_id', 'created_at'])
    op.create_index('idx_user_interactions_session', 'user_interaction_history', ['session_id'])
    op.create_index('idx_user_interactions_type', 'user_interaction_history', ['interaction_type'])

    # =============================================
    # KNOWLEDGE ENTITIES
    # =============================================
    op.create_table(
        'knowledge_entities',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),

        # Entity identification
        sa.Column('entity_type', sa.String(100), nullable=False),
        sa.Column('entity_value', sa.Text, nullable=False),
        sa.Column('entity_label', sa.String(500), nullable=True),

        # Source
        sa.Column('source_document_id', UUID(as_uuid=True), nullable=True),
        sa.Column('extraction_confidence', sa.Float, nullable=False, server_default='0.0'),

        # Weaviate embedding reference
        sa.Column('embedding_id', sa.String(100), nullable=True),

        # Metadata
        sa.Column('attributes', JSONB, nullable=False, server_default='{}'),
        sa.Column('domain', sa.String(100), nullable=True),

        # ACL (inherited from source document)
        sa.Column('acl_user_ids', JSONB, nullable=False, server_default='[]'),
        sa.Column('acl_role_ids', JSONB, nullable=False, server_default='[]'),
        sa.Column('acl_everyone', sa.Boolean, nullable=False, server_default='false'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_document_id'], ['documents.id'], ondelete='SET NULL'),
    )

    op.create_index('idx_knowledge_entities_tenant_type', 'knowledge_entities', ['tenant_id', 'entity_type'])
    op.create_index('idx_knowledge_entities_tenant_domain', 'knowledge_entities', ['tenant_id', 'domain'])
    op.create_index('idx_knowledge_entities_source_doc', 'knowledge_entities', ['source_document_id'])
    op.create_index('idx_knowledge_entities_type', 'knowledge_entities', ['entity_type'])

    # =============================================
    # KNOWLEDGE RELATIONSHIPS
    # =============================================
    op.create_table(
        'knowledge_relationships',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=False),

        # Connected entities
        sa.Column('source_entity_id', UUID(as_uuid=True), nullable=False),
        sa.Column('target_entity_id', UUID(as_uuid=True), nullable=False),

        # Relationship details
        sa.Column('relationship_type', sa.String(100), nullable=False),
        sa.Column('relationship_strength', sa.Float, nullable=False, server_default='0.5'),

        # Context
        sa.Column('context_snippet', sa.Text, nullable=True),
        sa.Column('source_document_id', UUID(as_uuid=True), nullable=True),

        # Extra data (renamed from 'metadata' which is reserved in SQLAlchemy)
        sa.Column('extra_data', JSONB, nullable=False, server_default='{}'),

        # Timestamp
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_entity_id'], ['knowledge_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_entity_id'], ['knowledge_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_document_id'], ['documents.id'], ondelete='SET NULL'),
    )

    op.create_index('idx_knowledge_rels_source', 'knowledge_relationships', ['source_entity_id'])
    op.create_index('idx_knowledge_rels_target', 'knowledge_relationships', ['target_entity_id'])
    op.create_index('idx_knowledge_rels_type', 'knowledge_relationships', ['relationship_type'])
    op.create_index('idx_knowledge_rels_tenant', 'knowledge_relationships', ['tenant_id'])


def downgrade():
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('knowledge_relationships')
    op.drop_table('knowledge_entities')
    op.drop_table('user_interaction_history')
    op.drop_table('user_learning_profiles')
