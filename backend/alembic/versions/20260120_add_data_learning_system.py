"""Add Data Learning System tables

Revision ID: 20260120_data_learning
Revises: 20260120_nexuslm
Create Date: 2026-01-20

This migration adds:
- connector_content_models: Discovered content model from connectors (types, aspects, properties)
- learned_folder_patterns: Folder hierarchy patterns (level → semantic meaning)
- learned_property_mappings: Property to semantic field mappings with search weights
- learned_relationship_types: Association types → Knowledge Graph edge mappings
- connector_indexing_strategies: Indexing strategies per connector and document type
- data_learning_jobs: Learning job tracking (status, progress, results)

The Data Learning System allows Emma to:
1. Discover the content model of external systems (Alfresco types/aspects)
2. Learn folder structure semantics (department/project/classification)
3. Map properties to normalized fields with importance weights
4. Extract relationships for Knowledge Graph expansion
5. Generate optimal indexing strategies per document type
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260120_data_learning'
down_revision = '20260120_nexuslm'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # connector_content_models - Discovered content model from connector
    # =========================================================================
    op.create_table(
        'connector_content_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Raw discovered model
        sa.Column('content_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        # Example: {
        #   "cm:content": {"title": "Content", "parent": "cm:cmobject", "properties": [...]},
        #   "gdapm:expediente": {"title": "Expediente", "parent": "cm:content", "properties": [...]}
        # }

        sa.Column('aspects', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        # Example: {
        #   "cm:titled": {"properties": ["cm:title", "cm:description"]},
        #   "cm:versionable": {"properties": ["cm:versionLabel"]}
        # }

        sa.Column('property_definitions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Example: {
        #   "cm:title": {"type": "d:text", "mandatory": false, "multiValued": false},
        #   "gdapm:numExpediente": {"type": "d:text", "mandatory": true, "constraints": [...]}
        # }

        sa.Column('association_types', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Example: {
        #   "cm:references": {"source": "cm:content", "target": "cm:content"},
        #   "gdapm:expedienteDocumento": {"source": "gdapm:expediente", "target": "cm:content"}
        # }

        # LLM-enriched semantics
        sa.Column('type_semantics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Example: {
        #   "gdapm:expediente": {
        #     "semantic_type": "administrative_file",
        #     "domain": "legal",
        #     "description": "Administrative proceeding file",
        #     "chunking_strategy": "legal_sections"
        #   }
        # }

        sa.Column('property_semantics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Example: {
        #   "cm:title": {"search_weight": 1.0, "include_in_embedding": true},
        #   "gdapm:numExpediente": {"search_weight": 2.0, "is_identifier": true}
        # }

        # Discovery metadata
        sa.Column('discovery_method', sa.String(50), nullable=False, server_default='api'),
        # api (Dictionary API), sampling (inferred from documents), manual

        sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_ccm_connector', 'connector_content_models', ['connector_id'], unique=True)
    op.create_index('idx_ccm_tenant', 'connector_content_models', ['tenant_id'])

    # =========================================================================
    # learned_folder_patterns - Folder hierarchy semantic patterns
    # =========================================================================
    op.create_table(
        'learned_folder_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Pattern definition
        sa.Column('path_pattern', sa.String(1000), nullable=False),
        # Example: "/Sites/{site}/documentLibrary/{department}/{year}/*"

        sa.Column('level_semantics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Example: {
        #   0: {"name": "sites_root", "type": "fixed"},
        #   1: {"name": "site", "type": "site_identifier"},
        #   2: {"name": "document_library", "type": "fixed"},
        #   3: {"name": "department", "type": "classification", "values": ["RRHH", "Legal", "Finance"]},
        #   4: {"name": "year", "type": "temporal", "format": "YYYY"}
        # }

        # Example paths that match this pattern
        sa.Column('example_paths', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # ["/Sites/gdapm/documentLibrary/RRHH/2024", "/Sites/gdapm/documentLibrary/Legal/2023"]

        # Statistics
        sa.Column('match_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.0'),

        # Learning metadata
        sa.Column('learned_from_sample_size', sa.Integer(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        # Verified = admin has confirmed this pattern

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_lfp_connector', 'learned_folder_patterns', ['connector_id'])
    op.create_index('idx_lfp_tenant', 'learned_folder_patterns', ['tenant_id'])
    op.create_index('idx_lfp_confidence', 'learned_folder_patterns', ['confidence'])

    # =========================================================================
    # learned_property_mappings - Property to semantic field mappings
    # =========================================================================
    op.create_table(
        'learned_property_mappings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Source property (connector-specific)
        sa.Column('source_property', sa.String(255), nullable=False),
        # Example: "gdapm:numExpediente", "cm:title", "cm:creator"

        sa.Column('source_type', sa.String(100), nullable=True),
        # Example: "gdapm:expediente" - Only applies to this type (null = all types)

        # Target normalized field
        sa.Column('target_field', sa.String(100), nullable=False),
        # Example: "identifier", "title", "author", "date", "department"

        # Mapping configuration
        sa.Column('search_weight', sa.Float(), nullable=False, server_default='1.0'),
        # Higher = more important for search ranking

        sa.Column('include_in_embedding', sa.Boolean(), nullable=False, server_default='true'),
        # Include this field's value in the document embedding

        sa.Column('is_filterable', sa.Boolean(), nullable=False, server_default='false'),
        # Can be used as a filter in queries

        sa.Column('is_facetable', sa.Boolean(), nullable=False, server_default='false'),
        # Can be used for faceted search

        # Value transformation
        sa.Column('transformation', sa.String(50), nullable=True),
        # none, lowercase, uppercase, date_normalize, numeric

        sa.Column('default_value', sa.String(500), nullable=True),
        # Default value if source is null

        # Learning metadata
        sa.Column('learned_from_usage', sa.Boolean(), nullable=False, server_default='false'),
        # True if weight was adjusted based on user search patterns

        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        # How many times this field was involved in successful searches

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_lpm_connector', 'learned_property_mappings', ['connector_id'])
    op.create_index('idx_lpm_tenant', 'learned_property_mappings', ['tenant_id'])
    op.create_index('idx_lpm_source', 'learned_property_mappings', ['source_property'])
    op.create_index('idx_lpm_target', 'learned_property_mappings', ['target_field'])
    op.create_unique_constraint(
        'uq_lpm_connector_source_type',
        'learned_property_mappings',
        ['connector_id', 'source_property', 'source_type']
    )

    # =========================================================================
    # learned_relationship_types - Association types to KG edge mappings
    # =========================================================================
    op.create_table(
        'learned_relationship_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Source relationship type (connector-specific)
        sa.Column('source_relationship', sa.String(255), nullable=False),
        # Example: "cm:references", "gdapm:expedienteDocumento", "peer:related"

        sa.Column('relationship_category', sa.String(50), nullable=False),
        # peer (bidirectional), child (hierarchical), reference (unidirectional)

        # Target Knowledge Graph edge type
        sa.Column('kg_edge_type', sa.String(100), nullable=False),
        # Example: "references", "version_of", "relates_to", "contains"

        # Semantic description
        sa.Column('description', sa.Text(), nullable=True),
        # Example: "Document A references Document B for additional context"

        # Graph expansion settings
        sa.Column('include_in_retrieval', sa.Boolean(), nullable=False, server_default='true'),
        # Include related documents when retrieving this document

        sa.Column('expansion_depth', sa.Integer(), nullable=False, server_default='1'),
        # How many hops to follow (1 = direct relations only)

        sa.Column('weight', sa.Float(), nullable=False, server_default='1.0'),
        # Importance weight for ranking related documents

        # Statistics
        sa.Column('instance_count', sa.Integer(), nullable=False, server_default='0'),
        # Number of times this relationship type was found

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_lrt_connector', 'learned_relationship_types', ['connector_id'])
    op.create_index('idx_lrt_tenant', 'learned_relationship_types', ['tenant_id'])
    op.create_index('idx_lrt_kg_edge', 'learned_relationship_types', ['kg_edge_type'])
    op.create_unique_constraint(
        'uq_lrt_connector_source',
        'learned_relationship_types',
        ['connector_id', 'source_relationship']
    )

    # =========================================================================
    # connector_indexing_strategies - Indexing strategies per connector/type
    # =========================================================================
    op.create_table(
        'connector_indexing_strategies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Scope - which documents this strategy applies to
        sa.Column('document_type', sa.String(255), nullable=True),
        # Example: "gdapm:expediente" - null = default for connector

        sa.Column('mime_type_pattern', sa.String(100), nullable=True),
        # Example: "application/pdf", "application/*" - null = all types

        # Chunking strategy
        sa.Column('chunking_type', sa.String(50), nullable=False, server_default='semantic'),
        # semantic, fixed_size, legal_sections, markdown_headers, page_based

        sa.Column('chunking_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        # Example for semantic: {"target_chunk_size": 512, "overlap": 50}
        # Example for legal_sections: {"section_markers": ["CLÁUSULA", "ARTÍCULO"]}

        # Embedding strategy
        sa.Column('embedding_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        # Fields to include in embedding: ["content", "title", "department"]

        sa.Column('embedding_weights', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Weights for each field: {"content": 1.0, "title": 1.5, "department": 0.5}

        # Metadata extraction
        sa.Column('extract_entities', sa.Boolean(), nullable=False, server_default='true'),
        # Extract named entities (persons, organizations, dates, amounts)

        sa.Column('entity_types', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Specific entity types to extract: ["PERSON", "ORG", "DATE", "MONEY"]

        sa.Column('extract_to_knowledge_graph', sa.Boolean(), nullable=False, server_default='true'),
        # Add extracted entities to Knowledge Graph

        # Priority and status
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        # Higher priority strategies are applied first (for overlapping scopes)

        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('idx_cis_connector', 'connector_indexing_strategies', ['connector_id'])
    op.create_index('idx_cis_tenant', 'connector_indexing_strategies', ['tenant_id'])
    op.create_index('idx_cis_doc_type', 'connector_indexing_strategies', ['document_type'])
    op.create_index('idx_cis_priority', 'connector_indexing_strategies', ['priority'])

    # =========================================================================
    # data_learning_jobs - Learning job tracking
    # =========================================================================
    op.create_table(
        'data_learning_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('connectors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),

        # Job type
        sa.Column('job_type', sa.String(50), nullable=False),
        # content_model_discovery, folder_analysis, property_mapping,
        # relationship_learning, strategy_optimization, full_learning

        # Status
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        # pending, running, completed, failed, cancelled

        sa.Column('status_message', sa.Text(), nullable=True),

        # Progress tracking
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_phase', sa.String(100), nullable=True),
        # Example: "Discovering content types", "Analyzing folder structure"

        # Results
        sa.Column('results_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Example: {
        #   "types_discovered": 15,
        #   "folder_patterns_learned": 3,
        #   "properties_mapped": 45,
        #   "relationships_found": 8
        # }

        sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # List of non-fatal errors encountered

        # Configuration
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Job-specific configuration

        # Trigger info
        sa.Column('triggered_by', sa.String(50), nullable=False, server_default='manual'),
        # manual, scheduled, connector_created, connector_updated

        sa.Column('triggered_by_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Timing
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index('idx_dlj_connector', 'data_learning_jobs', ['connector_id'])
    op.create_index('idx_dlj_tenant', 'data_learning_jobs', ['tenant_id'])
    op.create_index('idx_dlj_status', 'data_learning_jobs', ['status'])
    op.create_index('idx_dlj_job_type', 'data_learning_jobs', ['job_type'])
    op.create_index('idx_dlj_created', 'data_learning_jobs', ['created_at'])

    # =========================================================================
    # Add learned_context column to indexed_documents for normalized context
    # =========================================================================
    op.add_column('indexed_documents',
        sa.Column('learned_context', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    # Structure: {
    #   "semantic_type": "administrative_file",
    #   "domain": "hr",
    #   "folder_semantics": {"department": "RRHH", "year": "2024", "classification": "personnel"},
    #   "property_weights": {"identifier": 2.0, "title": 1.5},
    #   "relationships": [{"type": "references", "target_id": "...", "strength": 0.8}]
    # }

    op.add_column('indexed_documents',
        sa.Column('custom_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    # Connector-specific raw metadata (original Alfresco/SharePoint properties)


def downgrade() -> None:
    # Remove columns from indexed_documents
    op.drop_column('indexed_documents', 'custom_metadata')
    op.drop_column('indexed_documents', 'learned_context')

    # Drop tables in reverse order
    op.drop_table('data_learning_jobs')
    op.drop_table('connector_indexing_strategies')
    op.drop_table('learned_relationship_types')
    op.drop_table('learned_property_mappings')
    op.drop_table('learned_folder_patterns')
    op.drop_table('connector_content_models')
