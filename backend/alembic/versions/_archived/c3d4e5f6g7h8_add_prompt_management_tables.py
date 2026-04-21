"""add prompt management tables

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-02-04 10:00:00.000000

Adds tables for the Prompt Management System:
- emma_prompt_rules: Dynamic prompt injection rules (Rule Engine)
- emma_few_shot_examples: Q&A examples with pgvector embeddings (Few-Shot Learning)
- emma_guardrails: Post-processing validation rules (Guardrail Service)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade():
    # ── Prompt Rules (Rule Engine) ────────────────────────────────────
    # Dynamic prompt injection based on context conditions
    op.create_table(
        'emma_prompt_rules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=True),  # NULL = global rule
        sa.Column('rule_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        # Conditions to match (e.g., {"document_type": "contrato", "action": "analyze"})
        sa.Column('conditions', JSONB, nullable=False),
        # Action: inject_block, skip_block, modify_context, set_variable
        sa.Column('action_type', sa.String(50), nullable=False),
        # Action configuration (e.g., {"block_key": "custom_instruction", "content": "..."})
        sa.Column('action_config', JSONB, nullable=False),
        # Priority for rule ordering (lower = higher priority)
        sa.Column('priority', sa.Integer(), server_default='100'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_prompt_rules_tenant_active', 'emma_prompt_rules', ['tenant_id', 'is_active'])
    op.create_index('idx_prompt_rules_priority', 'emma_prompt_rules', ['priority'])

    # ── Few-Shot Examples (pgvector) ──────────────────────────────────
    # Q&A examples for few-shot learning with semantic similarity search
    op.create_table(
        'emma_few_shot_examples',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=True),  # NULL = global example
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        # Optional categorization
        sa.Column('category', sa.String(100), nullable=True),  # e.g., "labor_law", "contract_analysis"
        sa.Column('domain', sa.String(50), nullable=True),  # e.g., "legal", "medical", "documental"
        sa.Column('tags', ARRAY(sa.String(50)), nullable=True),  # e.g., ["despido", "indemnizacion"]
        # BGE-M3 embedding (1024 dimensions)
        # NOTE: pgvector extension must be enabled: CREATE EXTENSION IF NOT EXISTS vector;
        sa.Column('embedding', sa.LargeBinary(), nullable=True),  # Will store as vector(1024) if pgvector is available
        # Quality and usage metrics
        sa.Column('quality_score', sa.Float(), server_default='1.0'),  # 0.0 - 1.0
        sa.Column('usage_count', sa.Integer(), server_default='0'),
        sa.Column('positive_feedback', sa.Integer(), server_default='0'),
        sa.Column('negative_feedback', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_few_shot_tenant_active', 'emma_few_shot_examples', ['tenant_id', 'is_active'])
    op.create_index('idx_few_shot_category', 'emma_few_shot_examples', ['category'])
    op.create_index('idx_few_shot_domain', 'emma_few_shot_examples', ['domain'])

    # Enable pgvector extension and create vector column if available
    # This is done in a separate try block to gracefully handle missing extension
    op.execute("""
        DO $$
        BEGIN
            -- Enable pgvector extension if not exists
            CREATE EXTENSION IF NOT EXISTS vector;

            -- Add vector column for embeddings (1024 dimensions for BGE-M3)
            ALTER TABLE emma_few_shot_examples
                ADD COLUMN IF NOT EXISTS embedding_vector vector(1024);

            -- Create IVFFlat index for fast similarity search
            CREATE INDEX IF NOT EXISTS idx_few_shot_embedding_vector
                ON emma_few_shot_examples
                USING ivfflat (embedding_vector vector_cosine_ops)
                WITH (lists = 100);

        EXCEPTION WHEN OTHERS THEN
            -- pgvector not available, fall back to binary storage
            RAISE NOTICE 'pgvector extension not available, using binary storage for embeddings';
        END $$;
    """)

    # ── Guardrails ────────────────────────────────────────────────────
    # Post-processing validation rules for LLM outputs
    op.create_table(
        'emma_guardrails',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=True),  # NULL = global guardrail
        sa.Column('guardrail_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        # Type: regex, keyword, semantic, llm_validator, length, format
        sa.Column('guardrail_type', sa.String(50), nullable=False),
        # Configuration based on type:
        # - regex: {"pattern": "...", "flags": "i"}
        # - keyword: {"blocked_words": [...], "required_words": [...]}
        # - semantic: {"forbidden_topics": [...], "similarity_threshold": 0.8}
        # - llm_validator: {"prompt": "...", "model": "...", "threshold": 0.9}
        # - length: {"min_chars": 10, "max_chars": 5000}
        # - format: {"must_contain_sources": true, "require_spanish": true}
        sa.Column('config', JSONB, nullable=False),
        # Action: block (reject response), warn (log but allow), redact (remove matched content)
        sa.Column('action_on_match', sa.String(50), nullable=False),
        # Which agents/prompts this applies to (empty = all)
        sa.Column('applies_to', ARRAY(sa.String(100)), nullable=True),  # e.g., ["LaborAgent", "synthesis"]
        # Priority for guardrail ordering
        sa.Column('priority', sa.Integer(), server_default='100'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_guardrails_tenant_active', 'emma_guardrails', ['tenant_id', 'is_active'])
    op.create_index('idx_guardrails_type', 'emma_guardrails', ['guardrail_type'])


def downgrade():
    # Drop vector index and column first
    op.execute("""
        DO $$
        BEGIN
            DROP INDEX IF EXISTS idx_few_shot_embedding_vector;
            ALTER TABLE emma_few_shot_examples DROP COLUMN IF EXISTS embedding_vector;
        EXCEPTION WHEN OTHERS THEN
            NULL;  -- Ignore errors
        END $$;
    """)

    op.drop_table('emma_guardrails')
    op.drop_table('emma_few_shot_examples')
    op.drop_table('emma_prompt_rules')
