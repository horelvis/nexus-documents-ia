# TrustGraph Phase 2 Backend — Graph RAG Pipeline

**Date**: 2026-03-28
**Status**: Approved
**Scope**: Replace current graph_expander with TrustGraph-validated Graph RAG pipeline
**Reference**: TrustGraph source at `/tmp/trustgraph-source/trustgraph-flow/trustgraph/retrieval/graph_rag/`

## 1. Objective

Adopt TrustGraph's Graph RAG retrieval pipeline to replace the current binary graph signal in SmartSearch. The LLM will receive semantically relevant subgraphs with provenance as structured context, enabling verified, enterprise-grade answers grounded in knowledge graph triples.

### What changes

| Before (Phase 1) | After (Phase 2) |
|---|---|
| Entity lookup by exact URI match | Entity retrieval by semantic embedding similarity |
| Binary graph signal (0/1 in reranking) | Continuous relevance score (0.0-1.0) from LLM edge scoring |
| No subgraph context to LLM | Full subgraph (entities + relationships + references) in system prompt |
| Regex-only entity extraction from query | LLM concept extraction + regex fallback |
| `graph_expander.py` (flat lookup) | `graph_rag.py` (6-stage pipeline) |

### What stays the same

- LangGraph ReAct agent (8 nodes, 13 tools)
- SmartSearch as orchestrator (Weaviate hybrid + Graph RAG in parallel)
- FalkorDB as graph store (`:Node`/`:Literal`/`:Rel` model from Phase 1)
- Weaviate for vector search (documents + new entity collection)
- intelligence-docs-service for embeddings (BGE-M3, 1024 dims)
- Langfuse for prompt management
- LLM: Qwen3.5-9B single model

## 2. Pipeline Architecture

```
User Query
    ↓
SmartSearch._execute()
    ↓
┌──────────────────────────────────────────────────────┐
│  asyncio.gather() — Parallel retrieval               │
│                                                      │
│  ┌──────────────────┐  ┌───────────────────────────┐ │
│  │ Weaviate Hybrid   │  │ Graph RAG Pipeline        │ │
│  │ (unchanged)       │  │                           │ │
│  │                   │  │ [1] Concept Extraction    │ │
│  │ tenant docs       │  │     LLM → concepts list   │ │
│  │                   │  │ [2] Entity Retrieval      │ │
│  │                   │  │     embed → Weaviate sim   │ │
│  │                   │  │ [3] BFS Subgraph          │ │
│  │                   │  │     FalkorDB 2-hop         │ │
│  │                   │  │ [4] Label Resolution      │ │
│  │                   │  │     URI → names (cached)   │ │
│  └────────┬─────────┘  └────────────┬──────────────┘ │
│           │                         │                 │
└───────────┼─────────────────────────┼─────────────────┘
            ▼                         ▼
      doc_results              labeled_subgraph
            │                         │
            │              ┌──────────▼──────────┐
            │              │ [5] Edge Scoring     │
            │              │     LLM → top 25     │
            │              └──────────┬──────────┘
            │                         │
            ▼                         ▼
     ┌──────────────────────────────────────┐
     │ [6] Merge + Rerank + Format Context  │
     │     scored edges → graph_context     │
     │     doc_ids → expanded_doc_ids       │
     │     continuous score → rerank signal │
     └──────────────┬───────────────────────┘
                    ▼
          ReAct system prompt injection
```

## 3. Components

### 3.1 `graph_rag.py` — New module (replaces `graph_expander.py`)

**Location**: `emma-agent-service/app/agents/langgraph/tools/graph_rag.py`

Six-stage pipeline:

#### Stage 1: Concept Extraction

```python
async def extract_concepts(query: str, tenant_id: str) -> tuple[list[str], list[str]]:
    """Extract high-level themes and low-level entities from query via LLM.

    Returns (high_level_concepts, low_level_concepts).
    Falls back to regex entity extraction on LLM failure.
    """
```

- **LLM call**: Langfuse prompt `trustgraph_extract_concepts`
- **Input**: user query string
- **Output**: `{"high_level_keywords": [...], "low_level_keywords": [...]}`
- **Fallback**: existing `entity_extractor.py` regex patterns
- **Model role**: CHAT (Qwen3.5-9B)
- **Latency**: ~200ms

#### Stage 2: Entity Retrieval

```python
async def get_entities(
    concepts: list[str], tenant_id: str, collection: str, limit: int = 50
) -> list[dict]:
    """Embed concepts and retrieve matching entities by vector similarity.

    Returns list of {entity_uri, label, definition, type, score}.
    """
```

- **Embedding**: POST to intelligence-docs-service `/embeddings/generate` (BGE-M3)
- **Vector search**: weaviate-service search on `TrustGraphEntities` collection
- **Per-concept limit**: `max(1, entity_limit // len(concepts))`
- **Deduplication**: by entity_uri, keep highest score
- **Latency**: ~20ms (embedding) + ~10ms (Weaviate)

#### Stage 3: BFS Subgraph Traversal

```python
async def get_subgraph(
    seed_entities: list[str], tenant_id: str, max_hops: int = 2,
    max_edges: int = 150, triple_limit_per_entity: int = 30
) -> set[tuple[str, str, str]]:
    """BFS expansion from seed entities via KTS /triples/query.

    Returns set of (subject_uri, predicate_uri, object_uri_or_value) triples.
    """
```

- **Traversal**: iterative BFS, batch all entities at current level with `asyncio.gather`
- **Query patterns**: `by_subject(entity)` for each seed → collect objects → expand
- **Bounds**: `max_hops=2`, `max_edges=150`, `triple_limit_per_entity=30`
- **Filters**: skip `prov/*` predicates (provenance noise), skip `core/label` (resolved separately)
- **Latency**: ~30ms (2 hops, batch queries)

#### Stage 4: Label Resolution

```python
async def resolve_labels(
    subgraph: set, tenant_id: str, collection: str
) -> tuple[list[dict], dict[str, str]]:
    """Resolve entity URIs to human-readable labels.

    Returns (labeled_edges, uri_to_label_map).
    Uses LRU cache with TTL 300s, keyed by {tenant_id}:{uri}.
    """
```

- **Cache**: `cachetools.TTLCache(maxsize=2000, ttl=300)` keyed `{tenant_id}:{uri}`
- **Batch**: collect all unique URIs, query `by_spo(uri, core/label)` in batch
- **Fallback**: URI last segment humanized (`nouxcube://entity/default/lgt` → `lgt`)
- **Latency**: ~5ms (mostly cache hits after first query)

#### Stage 5: Edge Scoring

```python
async def score_edges(
    query: str, labeled_edges: list[dict], concepts: list[str],
    edge_limit: int = 25
) -> list[dict]:
    """Two-phase edge filtering: semantic pre-filter + LLM scoring.

    Phase A: cosine similarity on edge descriptions → top 30
    Phase B: LLM scores relevance → top 25

    Returns scored edges sorted by relevance.
    """
```

- **Phase A (semantic)**: embed edge descriptions (`"{s}, {p}, {o}"`) + concept vectors → cosine similarity → keep top 30
- **Phase B (LLM)**: Langfuse prompt `trustgraph_edge_scoring` with query + 30 edges → JSON response `[{id, score}]` → keep top 25
- **Model role**: CHAT (Qwen3.5-9B)
- **Latency**: ~20ms (embeddings) + ~200ms (LLM scoring)

#### Stage 6: Context Formatting

```python
def format_graph_context(
    scored_edges: list[dict], uri_map: dict[str, str]
) -> tuple[str, set[str], float]:
    """Format subgraph as structured context for LLM system prompt.

    Returns (context_text, expanded_doc_ids, avg_edge_score).
    TrustGraph-style: entities JSON + relationships JSON + references.
    """
```

- **Output format** (following TrustGraph convention):

```
## Knowledge Graph Context

### Entities
```json
[{"name": "LGT", "type": "law", "definition": "Ley General Tributaria..."}]
```

### Relationships
```json
[{"subject": "Art. 6 RF", "predicate": "regulado-por", "object": "LGT", "score": 0.92}]
```

### Source Documents
[R1] MM1VMAJ015XXXX.pdf
[R2] 09_impugnacion_testamento.md
```

- **Document ID extraction**: from `source_chunk` field of top edges (provenance link)
- **Average score**: used as continuous graph signal in reranking (replaces binary 0/1)

### 3.2 Weaviate Collection `TrustGraphEntities`

**Location**: weaviate-service

New collection for entity embeddings:

| Property | Type | Description |
|----------|------|-------------|
| `entity_uri` | TEXT | Canonical URI (`nouxcube://entity/...`) |
| `label` | TEXT | Human-readable name |
| `definition` | TEXT | Entity definition (may be empty) |
| `entity_type` | TEXT | Semantic type (person, law, organization, etc.) |
| `tenant_id` | TEXT | Tenant isolation |
| `collection` | TEXT | Collection scope |
| `embed_text` | TEXT | Text that was embedded: `"{label} ({type}). {definition}"` |

**Vector**: BGE-M3 1024 dims, HNSW cosine distance. External embeddings via intelligence-docs-service (same as document chunks).

**Population**: during reindex, after triple extraction. New step in `reindex_trustgraph.py`:
1. Query all `:Node` entities with `core/label` + `core/type` + `core/definition`
2. Build embed text per entity
3. POST to intelligence-docs-service for batch embedding
4. Upsert to Weaviate `TrustGraphEntities`

### 3.3 New Langfuse Prompts (2)

#### `trustgraph_extract_concepts`

```
Extract key concepts from the user query for knowledge graph retrieval.

Return TWO types:
1. high_level_keywords: overarching themes, subject areas, domains
2. low_level_keywords: specific entities, proper nouns, legal references

Query: {query}

Respond ONLY with valid JSON:
{"high_level_keywords": ["..."], "low_level_keywords": ["..."]}
```

#### `trustgraph_edge_scoring`

```
Score the relevance of each knowledge graph edge to the user query.
Score 0 (irrelevant) to 10 (highly relevant).

Query: {query}

Edges:
{edges_json}

Respond with a JSON array. Each element: {"id": "edge_id", "score": N}
Only include edges with score > 0.
```

### 3.4 SmartSearch Changes

**File**: `emma-agent-service/app/agents/langgraph/tools/smart_search.py`

- Replace `expand_with_sector_graph()` call with `graph_rag.execute()`
- Graph RAG runs in `asyncio.gather()` alongside Weaviate hybrid search
- Reranking `graph` signal: `avg_edge_score` (continuous 0.0-1.0) instead of binary
- `expanded_doc_ids`: extracted from scored edges' `source_chunk` provenance
- `graph_context`: injected into state for ReAct system prompt (via `memory_recall_node`)

### 3.5 Reindex Script Changes

**File**: `knowledge-tree-service/scripts/reindex_trustgraph.py`

New Step 7 (after entity resolution, before summary):
1. Query all entity `:Node` URIs for tenant
2. Batch fetch `core/label`, `core/type`, `core/definition` for each
3. Build embed texts
4. POST to intelligence-docs-service `/embeddings/batch`
5. Upsert to Weaviate `TrustGraphEntities` collection

### 3.6 New KTS Endpoint

**File**: `knowledge-tree-service/app/api/triples.py`

```
POST /triples/neighbors
```

Batch BFS traversal endpoint for graph_rag. Accepts list of seed entity URIs, returns subgraph edges up to max_hops. More efficient than N individual `/triples/query` calls.

## 4. Deprecations

| Component | Status | Replacement |
|-----------|--------|-------------|
| `graph_expander.py` | **DEPRECATED** | `graph_rag.py` |
| `_get_documents_by_person()` in smart_search | **REMOVED** | BFS covers person→document traversal |
| Binary graph signal (0/1) in reranking | **REPLACED** | Continuous edge score (0.0-1.0) |
| `SMART_SEARCH_GRAPH_ENABLED` flag | **REPLACED** | `GRAPH_RAG_ENABLED` (default: true) |

## 5. Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPH_RAG_ENABLED` | `true` | Master switch for Graph RAG pipeline |
| `GRAPH_RAG_ENTITY_LIMIT` | `50` | Max entities from vector search |
| `GRAPH_RAG_MAX_HOPS` | `2` | BFS traversal depth |
| `GRAPH_RAG_MAX_EDGES` | `150` | Max edges in subgraph |
| `GRAPH_RAG_EDGE_LIMIT` | `25` | Max edges after LLM scoring |
| `GRAPH_RAG_LABEL_CACHE_TTL` | `300` | Label cache TTL (seconds) |
| `GRAPH_RAG_EDGE_SCORE_LIMIT` | `30` | Semantic pre-filter limit before LLM |

## 6. Latency Budget

| Step | Time | Notes |
|------|------|-------|
| Concept extraction (LLM) | ~200ms | Parallel with Weaviate hybrid |
| Entity embedding (BGE-M3) | ~20ms | Sequential |
| Entity similarity (Weaviate) | ~10ms | Sequential |
| BFS traversal (FalkorDB) | ~30ms | Batch async |
| Label resolution | ~5ms | Cache hits |
| Edge embedding (pre-filter) | ~20ms | Batch |
| Edge scoring (LLM) | ~200ms | Sequential |
| **Total Graph RAG** | **~485ms** | |
| **Total SmartSearch** | **~585ms** | Weaviate parallel (~100ms absorbed) |
| **Delta vs current** | **+385ms** | Current: ~200ms |

## 7. Testing Strategy

1. **Unit tests**: Each stage independently with mocked LLM/Weaviate/FalkorDB
2. **Integration test**: Full pipeline with real FalkorDB + mocked LLM
3. **Sanity check**: Add to diagnostics endpoint (`/diagnostics/sanity`) — verify concept extraction + entity retrieval + subgraph + scoring produces non-empty context for a test query
4. **A/B comparison**: Log both old (binary) and new (scored) graph signals for first 100 queries to validate improvement

## 8. File Impact

| File | Change |
|------|--------|
| `emma-agent-service/app/agents/langgraph/tools/graph_rag.py` | **NEW** — 6-stage pipeline |
| `emma-agent-service/app/agents/langgraph/tools/smart_search.py` | **MODIFY** — integrate graph_rag |
| `emma-agent-service/app/agents/langgraph/sectors/graph_expander.py` | **DEPRECATE** |
| `emma-agent-service/app/agents/langgraph/nodes/memory_recall.py` | **MODIFY** — inject graph_context |
| `knowledge-tree-service/app/api/triples.py` | **MODIFY** — add `/triples/neighbors` |
| `knowledge-tree-service/app/services/triple_query.py` | **MODIFY** — add `batch_neighbors()` |
| `knowledge-tree-service/scripts/reindex_trustgraph.py` | **MODIFY** — add entity embedding step |
| `weaviate-service/app/services/weaviate_service.py` | **MODIFY** — TrustGraphEntities collection |
| `weaviate-service/app/api/weaviate.py` | **MODIFY** — entity search endpoint |
| `scripts/seed_langfuse_extraction_prompts.py` | **MODIFY** — add 2 prompts |
