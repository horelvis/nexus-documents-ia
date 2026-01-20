-- =============================================================================
-- Apache AGE Initialization Script
-- =============================================================================
-- This script runs on first PostgreSQL container startup
-- It creates the AGE extension and initializes the base knowledge graph
--
-- Architecture:
-- ┌─────────────────────────────────────────────────────────────────────────┐
-- │                        KNOWLEDGE GRAPH SCHEMA                           │
-- ├─────────────────────────────────────────────────────────────────────────┤
-- │  Nodes (Vertices):                                                       │
-- │  ├─ Entity: {id, type, value, normalized_value, tenant_id}              │
-- │  ├─ Document: {id, title, type, tenant_id}                              │
-- │  └─ Chunk: {id, document_id, sequence, tenant_id}                       │
-- │                                                                         │
-- │  Edges (Relationships):                                                  │
-- │  ├─ APPEARS_IN: Entity → Document (strength, context)                   │
-- │  ├─ RELATED_TO: Entity → Entity (type, strength)                        │
-- │  ├─ REFERENCES: Document → Document (type, strength)                    │
-- │  ├─ CONTAINS: Document → Chunk (sequence)                               │
-- │  └─ DEPENDS_ON: Chunk → Chunk (type: semantic|structural)               │
-- └─────────────────────────────────────────────────────────────────────────┘
--
-- Cypher Query Examples:
--
-- Find related entities (for query expansion):
--   SELECT * FROM cypher('knowledge_graph', $$
--     MATCH (e:Entity {value: 'Juan García'})-[:RELATED_TO*1..2]-(related)
--     RETURN related.value, related.type
--   $$) AS (value agtype, type agtype);
--
-- Find documents with dependencies:
--   SELECT * FROM cypher('knowledge_graph', $$
--     MATCH (d:Document)-[:REFERENCES]->(ref:Document)
--     WHERE d.tenant_id = 'tenant-123'
--     RETURN d.title, ref.title
--   $$) AS (doc_title agtype, ref_title agtype);
-- =============================================================================

-- Create the AGE extension
CREATE EXTENSION IF NOT EXISTS age;

-- Load AGE into the search path
LOAD 'age';

-- Set the search path to include ag_catalog for Cypher functions
SET search_path = ag_catalog, "$user", public;

-- Create the main knowledge graph
-- This is the default graph used by all tenants (tenant isolation via properties)
SELECT create_graph('knowledge_graph');

-- =============================================================================
-- HELPER FUNCTIONS FOR MULTI-TENANT GRAPH OPERATIONS
-- =============================================================================

-- Function to create a tenant-specific graph (optional, for strict isolation)
CREATE OR REPLACE FUNCTION create_tenant_graph(tenant_id TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    graph_name TEXT;
BEGIN
    graph_name := 'kg_' || replace(tenant_id, '-', '_');

    -- Check if graph exists
    IF NOT EXISTS (
        SELECT 1 FROM ag_catalog.ag_graph
        WHERE name = graph_name
    ) THEN
        PERFORM ag_catalog.create_graph(graph_name);
        RETURN TRUE;
    END IF;

    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Function to drop a tenant graph (for tenant deletion)
CREATE OR REPLACE FUNCTION drop_tenant_graph(tenant_id TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    graph_name TEXT;
BEGIN
    graph_name := 'kg_' || replace(tenant_id, '-', '_');

    IF EXISTS (
        SELECT 1 FROM ag_catalog.ag_graph
        WHERE name = graph_name
    ) THEN
        PERFORM ag_catalog.drop_graph(graph_name, TRUE);
        RETURN TRUE;
    END IF;

    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================
-- Note: AGE creates internal indexes, but we add metadata table for fast lookups

-- Metadata table for entity deduplication (normalized values)
CREATE TABLE IF NOT EXISTS kg_entity_index (
    id SERIAL PRIMARY KEY,
    normalized_value TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    vertex_id BIGINT,  -- AGE vertex ID for fast graph access
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(normalized_value, entity_type, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_entity_normalized
ON kg_entity_index(normalized_value, tenant_id);

CREATE INDEX IF NOT EXISTS idx_kg_entity_type
ON kg_entity_index(entity_type, tenant_id);

-- Document-to-vertex mapping for fast lookups
CREATE TABLE IF NOT EXISTS kg_document_index (
    id SERIAL PRIMARY KEY,
    document_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    vertex_id BIGINT,  -- AGE vertex ID
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(document_id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_document_id
ON kg_document_index(document_id, tenant_id);

-- =============================================================================
-- VERIFICATION
-- =============================================================================

-- Verify AGE is properly installed
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'age') THEN
        RAISE NOTICE '✅ Apache AGE extension installed successfully';
    ELSE
        RAISE EXCEPTION '❌ Apache AGE extension installation failed';
    END IF;

    IF EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'knowledge_graph') THEN
        RAISE NOTICE '✅ Knowledge graph created successfully';
    ELSE
        RAISE EXCEPTION '❌ Knowledge graph creation failed';
    END IF;
END $$;

-- Log completion
SELECT 'Apache AGE initialization complete. Knowledge graph ready for use.' AS status;
