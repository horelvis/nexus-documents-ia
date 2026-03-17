-- =============================================================================
-- pgvector Extension Initialization
-- =============================================================================
-- Runs BEFORE Apache AGE init (00 < 01 ordering).
-- Creates the pgvector extension for vector similarity search.
--
-- Used by:
--   - MemoRAG: Document memory embeddings (VECTOR(1024) column, IVFFlat index)
--   - Few-shot retriever: Semantic example matching for prompt management
--
-- The extension is compiled from source in Dockerfile.postgres since
-- Debian repos only package pgvector for PG16+ (this image is PG15).
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE NOTICE 'pgvector extension installed successfully (version: %)',
            (SELECT extversion FROM pg_extension WHERE extname = 'vector');
    ELSE
        RAISE WARNING 'pgvector extension NOT available — MemoRAG will use keyword fallback';
    END IF;
END $$;
