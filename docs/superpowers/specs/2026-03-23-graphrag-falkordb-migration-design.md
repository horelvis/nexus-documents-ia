# GraphRAG Migration: Apache AGE to FalkorDB

**Date**: 2026-03-23
**Status**: Approved
**Branch**: `feature/graphrag-falkordb-migration`
**Service**: `backend/microservices/knowledge-tree-service/`

---

## Objectives

1. **Less hallucinations** -- Ground LLM responses in structured, connected facts with full provenance
2. **Deep context** -- Enable multi-hop reasoning across complex entity relationships
3. **Improved reasoning** -- "Connect the dots" across large datasets with evidence trails

## Decision: FalkorDB over Neo4j

Based on real-world benchmarks and production GitHub projects:

| Metric | Neo4j Community 5.x | FalkorDB | Apache AGE (current) |
|--------|---------------------|----------|---------------------|
| Latency p99 | ~46.9s (graph expansion) | <140ms | ~200-500ms |
| Latency p50 | ~200ms | <20ms | ~50-100ms |
| Writes | Moderate | 3-8x faster than Neo4j | Via PG transactions |
| Cypher | Native | openCypher (compatible) | openCypher (partial) |
| Async Python | `neo4j` driver | `falkordb[asyncio]` | `asyncpg` |
| License | GPLv3 (copyleft) | Apache 2.0 (permissive) | Apache 2.0 |
| Multi-tenancy | Manual | Native (multi-graph) | Manual |
| GraphRAG SDK | LangChain Neo4jGraph | Dedicated GraphRAG-SDK | None |

**Key factor**: FalkorDB achieves 500x lower p99 latency than Neo4j in aggregate expansion -- exactly the operation used by `subgraph_extractor.py` for multi-hop GraphRAG.

Sources:
- https://www.falkordb.com/blog/graph-database-performance-benchmarks-falkordb-vs-neo4j/
- https://github.com/FalkorDB/GraphRAG-SDK
- https://github.com/neo4j-contrib/ms-graphrag-neo4j

---

## Architecture

### Before (current)

```
knowledge-tree-service (port 8011)
  -- asyncpg --> PostgreSQL + Apache AGE extension
       |-- legal_graph (sector)
       |-- medical_graph (sector)
       |-- documental_graph (sector)
       |-- knowledge_graph_public (shared)
       --- business_ontology (shared)
```

### After (proposed)

```
knowledge-tree-service (port 8011)
  -- falkordb[asyncio] --> FalkorDB (port 6379, mapped to host 6380)
       --- knowledge_graph (single unified graph)
            |-- Structural: :Document, :Folder (tenant-scoped)
            |-- Entities: :Entity (universal, typed via entity_type property)
            |-- Claims: :Claim (evidence-bearing facts with provenance)
            |-- Ontology: :EntityType, :RelationType (shared)
            --- Sector-specific labels created at bootstrap time
```

### What does NOT change

- **~58 HTTP API endpoints** -- Same paths, same request/response schemas
- **Callers** -- emma-agent-service, weaviate-service, background-worker call via HTTP (transparent)
- **Weaviate** -- Continues handling vector search / hybrid search / embeddings
- **PostgreSQL** -- Returns to pure relational role (tenants, users, documents, prompts)

**Note on callers**: The weaviate-service `knowledge_tree_client.py` includes a `graph_query` endpoint that accepts raw Cypher. AGE SQL-wrapped Cypher syntax (`SELECT * FROM cypher('graph', $$ ... $$)`) differs from FalkorDB native Cypher. This endpoint must be updated to accept native openCypher and callers reviewed.

### Docker Compose addition

```yaml
# docker-compose.onpremise.yml
falkordb:
  image: falkordb/falkordb:v4.2.0
  ports:
    - "6380:6379"    # Avoids conflict with existing Redis (Celery/cache)
    - "3003:3000"    # FalkorDB browser UI (3001=frontend, 3002=Langfuse)
  volumes:
    - falkordb_data:/var/lib/falkordb/data
  healthcheck:
    test: ["CMD", "redis-cli", "-p", "6379", "ping"]
    interval: 5s
    retries: 10
  restart: unless-stopped
```

**Important**: FalkorDB uses Redis protocol internally on port 6379. Services connect via hostname `falkordb:6379` (not `redis:6379`). The `FALKORDB_HOST` env var distinguishes it from the existing Redis service.

---

## Data Model: Evidence-Oriented Graph

Design principle: every node and relationship must answer "where does this come from and how reliable is it?"

### Node Labels

```
-- Entities (universal, typed via property) ---------
:Entity {
    tenant_id: string,
    name: string,
    normalized_name: string,
    entity_type: string,       -- "person", "organization", "law", "contract", "medication"...
    sector: string,            -- "legal", "medical", "documental"
    confidence: float,         -- 0.0-1.0 extraction confidence
    source_count: int,         -- number of documents mentioning this entity
    shared: bool,              -- true = public data (laws)
    created_at: datetime,
    updated_at: datetime
}

-- Documents (evidence source) ----------------------
:Document {
    tenant_id: string,
    document_id: string,
    title: string,
    semantic_type: string,
    domain: string,
    quality_score: float,
    chunk_count: int,
    indexed_at: datetime
}

-- Claims (extracted facts -- KEY for anti-hallucination) --
:Claim {
    tenant_id: string,
    statement: string,         -- "Juan Perez signed the contract on 15/03/2024"
    claim_type: string,        -- "factual", "temporal", "legal_reference", "numeric"
    confidence: float,
    source_chunk: string,      -- original text from which it was extracted
    verified: bool,            -- true if verified by Verified Generation
    created_at: datetime
}

-- Folders (structural) ----------------------------
:Folder {
    tenant_id: string,
    path: string,
    folder_type: string,
    name: string
}

-- Ontology (shared, no tenant_id) -----------------
-- Note: EntityType and RelationType are inherently shared (no tenant_id)
-- and do not need the `shared` property. They exist in a separate label
-- space from tenant-scoped :Entity nodes.
:EntityType {
    name: string,
    display_name: string,
    category: string,          -- "document", "entity", "process"
    parent: string,
    sector: string
}

:RelationType {
    name: string,
    source_type: string,
    target_type: string
}

-- Document Memory ---------------------------------
:DocumentMemory {
    document_id: string,
    summary: string,
    entities: string,          -- JSON list
    topics: string             -- JSON list
}
```

### Label migration mapping (current AGE -> new FalkorDB)

The current codebase uses 19+ specific vlabels. All merge into `:Entity` with `entity_type`:

| Current AGE vlabel | New FalkorDB | entity_type value |
|--------------------|--------------|-------------------|
| `structural_document` | `:Document` | (separate label) |
| `structural_folder` | `:Folder` | (separate label) |
| `Persona` | `:Entity` | `"person"` |
| `Organizacion` | `:Entity` | `"organization"` |
| `LegalLaw` | `:Entity` | `"law"` |
| `Articulo` | `:Entity` | `"article"` |
| `Sentencia` | `:Entity` | `"ruling"` |
| `Contrato` | `:Entity` | `"contract"` |
| `Clausula` | `:Entity` | `"clause"` |
| `Paciente` | `:Entity` | `"patient"` |
| `Diagnostico` | `:Entity` | `"diagnosis"` |
| `Procedimiento` | `:Entity` | `"procedure"` |
| `Farmaco` | `:Entity` | `"medication"` |
| `Expediente` | `:Entity` | `"dossier"` |
| `Flujo` | `:Entity` | `"workflow"` |
| `Categoria` | `:Entity` | `"category"` |
| `EntityType` | `:EntityType` | (separate label) |
| `RelationType` | `:RelationType` | (separate label) |
| `DocumentMemory` | `:DocumentMemory` | (separate label) |

This is a **substantial rewrite** of all Cypher queries -- every `MATCH (p:Persona ...)` becomes `MATCH (e:Entity {entity_type: "person"} ...)`. The `_TYPE_TO_VLABEL` mapping in `entity_graph_bridge.py` (19 entries) is replaced by a simpler `entity_type` property assignment.

### Relationship Types (with provenance)

```
-- Evidence relationships --------------------------
(:Entity)-[:MENTIONED_IN {
    chunk_index: int,
    extraction_method: string,  -- "ner", "regex", "llm", "manual"
    confidence: float,
    context_snippet: string     -- surrounding phrase (~50 chars)
}]->(:Document)

(:Entity)-[:RELATED_TO {
    relation_type: string,      -- "firmado_por", "emplea", "diagnosticado"
    confidence: float,
    evidence_doc: string,       -- source document_id
    evidence_chunk: string      -- supporting text
}]->(:Entity)

(:Claim)-[:EXTRACTED_FROM {
    chunk_index: int,
    extraction_method: string
}]->(:Document)

(:Claim)-[:ABOUT]->(:Entity)

(:Claim)-[:CONTRADICTS {
    contradiction_type: string  -- "temporal", "factual", "numeric"
}]->(:Claim)

(:Claim)-[:SUPPORTS]->(:Claim)

-- Structural relationships ------------------------
(:Document)-[:CONTAINED_IN]->(:Folder)
(:Folder)-[:CHILD_OF]->(:Folder)

-- Ontology relationships --------------------------
(:Document)-[:INSTANCE_OF]->(:EntityType)
(:Entity)-[:INSTANCE_OF]->(:EntityType)

-- Cross-references --------------------------------
(:Document)-[:REFERENCES_LAW]->(:Entity {entity_type: "law"})
(:Entity)-[:HAS_MEMORY]->(:DocumentMemory)
```

**Note on relationship naming**: Current AGE uses Spanish names (`ASOCIADO_A`, `FIRMADO_POR`, `PERTENECE_A`). The new model uses English names for consistency. The `relation_type` property on `:RELATED_TO` edges preserves the semantic name in Spanish (e.g., `relation_type: "firmado_por"`).

### How each objective maps to the graph

| Objective | Graph mechanism | Example |
|-----------|----------------|---------|
| Less hallucinations | `:Claim` with `source_chunk` + `confidence` | LLM receives: "Juan signed (source: doc X, chunk 3, confidence 0.95)" |
| Deep context | `:RELATED_TO` with `evidence_chunk` | Traversal: Person->documents->claims->related entities, each hop carries evidence |
| Improved reasoning | `:CONTRADICTS` / `:SUPPORTS` | LLM sees: "Claim A says date 15/03, Claim B says 22/03 (CONTRADICTS)" |

### FalkorDB Indexes

```cypher
-- Tenant isolation
CREATE INDEX FOR (d:Document) ON (d.tenant_id)
CREATE INDEX FOR (d:Document) ON (d.document_id)
CREATE INDEX FOR (f:Folder) ON (f.tenant_id)
CREATE INDEX FOR (e:Entity) ON (e.tenant_id, e.normalized_name)
CREATE INDEX FOR (e:Entity) ON (e.entity_type)
CREATE INDEX FOR (c:Claim) ON (c.tenant_id)
CREATE INDEX FOR (et:EntityType) ON (et.name)

-- Full-text indexes for entity resolution (use instead of regex MATCH)
CALL db.idx.fulltext.createNodeIndex('Document', 'title')
CALL db.idx.fulltext.createNodeIndex('Entity', 'name')
```

**Note**: Entity resolution in `subgraph_extractor` should use full-text index queries (`CALL db.idx.fulltext.queryNodes(...)`) instead of regex matching for better performance.

---

## GraphRAG Evidence Assembly (new subgraph_extractor)

```
Query: "Who signed the Empresa X contract?"
                    |
    1. Entity Resolution --> Full-text index: find :Entity {name ~ "Empresa X"}
                    |
    2. 2-hop traversal ---> Empresa X -MENTIONED_IN-> Documents
                            Documents <-EXTRACTED_FROM- Claims
                            Claims -ABOUT-> Entities (persons)
                            Entities -RELATED_TO{type:firmado_por}-> Empresa X
                    |
    3. Evidence Assembly -> For each Claim:
                              - statement + source_chunk + confidence
                              - CONTRADICTS/SUPPORTS other Claims
                    |
    4. Context to LLM ---> "According to doc X (quality 0.92):
                              - Juan Perez signed the contract [confidence: 0.95]
                              - Source: 'El Sr. Juan Perez, en calidad de...'
                              Warning: doc Y indicates different date"
```

---

## Components

### To rewrite (substantial Cypher changes)

| Current component | Change | Impact |
|-------------------|--------|--------|
| `age_client.py` | **Replace** -> `falkordb_client.py` (asyncio, retry, healthcheck) | Foundation for everything |
| `graph_bootstrap.py` | **Rewrite** -> unified graph bootstrap + FalkorDB indexes | Service startup |
| `subgraph_extractor.py` | **Rewrite** -> GraphRAG evidence assembly with Claims | Core value delivery |
| `structural_indexer.py` | **Rewrite** -> all vlabel refs change (:structural_document -> :Document, etc.) + add :Claim creation | Indexing pipeline |
| `entity_graph_bridge.py` | **Rewrite** -> 19 vlabel mappings collapse to :Entity with entity_type property | Entity storage |
| `tenant_knowledge_service.py` | **Rewrite** -> substantial Cypher (structural queries, counting, filtering) | Query layer |
| `legal_graph_service.py` | **Rewrite** -> LegalLaw/Articulo -> :Entity {entity_type:"law"/"article"} | Legal domain |
| `config/graphs/*.cypher` | **Replace** -> single `knowledge_graph_schema.cypher` | Schema |

### To adapt (moderate changes)

| Component | Change |
|-----------|--------|
| `ontology_service.py` | :EntityType queries switch from AGE SQL-wrapped to native Cypher |
| `memory_bank_service.py` | :DocumentMemory CRUD switch to FalkorDB |
| `legal_reference_bridge.py` | :REFERENCES_LAW edges in unified graph |
| `api/*.py` (all 7 routers) | Internal service calls update, HTTP contract unchanged |

### To create

| Component | Purpose |
|-----------|---------|
| `falkordb_client.py` | Async FalkorDB client with connection pool, retry, healthcheck |
| `claim_extractor.py` | Extract Claims from indexed documents (regex fast-path + optional LLM) |
| `knowledge_graph_schema.cypher` | Unified graph schema for all sectors |
| `scripts/migrate_age_to_falkordb.py` | ETL script: read existing AGE data, write to FalkorDB |

### To eliminate

| Component | Reason |
|-----------|--------|
| `legal_proxy_sync.py` | No separate graphs to sync -- unified graph |
| `sil/legal_graph_service.py` | Already deprecated stub |
| `config/graphs/legal_graph_schema.cypher` | Replaced by unified schema |
| `config/graphs/medical_graph_schema.cypher` | Replaced by unified schema |
| `config/graphs/documental_graph_schema.cypher` | Replaced by unified schema |
| `config/graphs/business_ontology.cypher` | Merged into unified schema |

### To deprecate (outside knowledge-tree-service)

| Component | Service | Action |
|-----------|---------|--------|
| `memorag/memory_store.py` | emma-agent-service | Redirect memory_recall -> Weaviate hybrid search |
| `memorag/service.py` | emma-agent-service | Deprecate, use Weaviate search |
| pgvector extension | Dockerfile.postgres | Remove pgvector compilation |
| `few_shot_retriever.py` (pgvector) | backend | Migrate to Weaviate collection (functional change, needs quality validation) |

---

## Environment Variables

### New

```bash
FALKORDB_HOST=falkordb           # Docker service name (NOT redis)
FALKORDB_PORT=6379               # Container-internal port
FALKORDB_GRAPH_NAME=knowledge_graph
FALKORDB_PASSWORD=               # Optional, empty for dev
```

### Removed (Phase 4)

```bash
# AGE_DATABASE_URL    -- no longer needed
# AGE_GRAPH_NAME      -- no longer needed
```

---

## Migration Phases

### Phase 1 -- Infrastructure (no breaking changes)

- Add FalkorDB service to `docker-compose.onpremise.yml` (pinned v4.2.0)
- Create `falkordb_client.py` with retry logic, connection pool, and healthcheck
- Create `knowledge_graph_schema.cypher` (unified schema with indexes)
- Update `requirements.txt` (add `falkordb[asyncio]`, keep `asyncpg` temporarily)
- Add env vars to `.env` and `.env.example`
- Tests: connection, bootstrap, basic Cypher queries on FalkorDB

### Phase 2a -- Core graph migration

- Rewrite `graph_bootstrap.py` -> FalkorDB bootstrap with unified schema
- Rewrite `structural_indexer.py` -> :Document, :Folder nodes in FalkorDB
- Rewrite `entity_graph_bridge.py` -> :Entity with entity_type + confidence + :MENTIONED_IN
- Create `scripts/migrate_age_to_falkordb.py` -> ETL for existing data
- Feature flag: `GRAPH_BACKEND=falkordb` (default) / `GRAPH_BACKEND=age` (rollback)
- Tests: indexing pipeline writes correctly to FalkorDB

### Phase 2b -- Domain services migration

- Rewrite `legal_graph_service.py` -> :Entity {entity_type:"law"/"article"} in unified graph
- Adapt `ontology_service.py` -> :EntityType in unified graph (native Cypher)
- Adapt `memory_bank_service.py` -> :DocumentMemory in FalkorDB
- Adapt `legal_reference_bridge.py` -> :REFERENCES_LAW edges
- Eliminate `legal_proxy_sync.py` (no longer needed)
- Tests: legal graph, ontology, memory bank endpoints pass

### Phase 2c -- Query services + API verification

- Rewrite `tenant_knowledge_service.py` -> FalkorDB queries
- Rewrite `subgraph_extractor.py` -> FalkorDB traversals (without Claims yet, same behavior as AGE)
- Update `graph_query` endpoint for native openCypher (no SQL wrapping)
- Verify all ~58 API endpoints pass
- Tests: full API regression, compare outputs AGE vs FalkorDB

### Phase 3 -- GraphRAG enhancement (new feature, not migration)

This phase introduces new capabilities that do not exist in the current system.
It can be developed in parallel with Phase 2 or as a follow-up.

- Create `claim_extractor.py`:
  - Regex fast-path (~3ms) for dates, amounts, BOE references
  - Optional LLM extraction (~200ms) for complex factual claims
  - Integration point: invoked by structural_indexer after :Document creation
  - Retroactive extraction for existing documents via background task
- Enhance `subgraph_extractor.py` -> evidence assembly with Claims
- Add :CONTRADICTS / :SUPPORTS detection logic
- Update emma-agent-service synthesize prompts to use evidence context
- Define claim extraction patterns per sector
- Tests: response quality comparison with/without claims

### Phase 4 -- Cleanup and pgvector deprecation

- Deprecate MemoRAG pgvector -> redirect memory_recall to Weaviate hybrid search
- Migrate few-shot retriever to Weaviate collection (requires quality validation)
- Remove pgvector from Dockerfile.postgres
- Remove asyncpg dependency from knowledge-tree-service
- Remove Apache AGE extension from PostgreSQL init scripts
- Remove old graph schema files from config/graphs/
- Remove `GRAPH_BACKEND` feature flag (FalkorDB only)
- Full regression tests across all services

---

## Rollback Strategy

### Phase 1
No risk -- FalkorDB is additive, nothing changes in AGE.

### Phase 2
Feature flag `GRAPH_BACKEND=age|falkordb` controls which backend is used for reads and writes.
- If FalkorDB proves problematic: set `GRAPH_BACKEND=age` and restart.
- Dual-write period: both backends receive writes during Phase 2a-2b validation.
- Cutover: once Phase 2c passes all ~58 endpoint tests, set `GRAPH_BACKEND=falkordb` as default.
- The AGE extension and asyncpg dependency remain until Phase 4 cleanup.

### Phase 3
Claims are additive -- existing graph works without them. Disable via `CLAIM_EXTRACTION_ENABLED=false`.

### Phase 4
Point of no return. Execute only after Phase 2 has been stable in production for at least 2 weeks.

---

## Backup Strategy for FalkorDB

- **Volume**: `falkordb_data` persists graph data across container restarts
- **Snapshot**: FalkorDB supports `GRAPH.RO_QUERY` for consistent reads during backup
- **Backup script**: Add to existing backup cron -- `docker exec falkordb redis-cli BGSAVE` + copy RDB file
- **Recovery**: Restore RDB file to volume, restart container
- **Frequency**: Same schedule as PostgreSQL backups (daily, with weekly full)

---

## Final Architecture (post-migration)

```
PostgreSQL  -> Relational data (tenants, users, documents, prompts, Langfuse)
Weaviate    -> Vector search + hybrid search (chunks, embeddings, BGE-M3)
FalkorDB   -> Knowledge graph (entities, claims, relationships, GraphRAG)
Redis       -> Cache, event bus, Celery broker (unchanged)
```

Each engine does exactly one thing. No duplication.
