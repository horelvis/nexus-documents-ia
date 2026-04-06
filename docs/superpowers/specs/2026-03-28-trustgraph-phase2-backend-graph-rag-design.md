# TrustGraph Phase 2 Backend — Dual RAG Architecture

**Date**: 2026-03-28 (v2)
**Status**: Approved
**Scope**: Graph RAG pipeline (TrustGraph) + SmartSearch improvements + shared concept extraction
**Reference**: TrustGraph source `/tmp/trustgraph-source/trustgraph-flow/trustgraph/retrieval/`

## 1. Objective

Implement TrustGraph's Graph RAG as a new retrieval pipeline alongside an improved SmartSearch. The two pipelines are complementary — Graph RAG retrieves via knowledge graph relationships, SmartSearch retrieves via document chunks. Both share a concept extraction pre-step adopted from TrustGraph.

### Architecture overview

```
User Query
    ↓
[Shared] Concept Extraction (LLM)
    ↓ high_level_concepts, low_level_concepts
    ↓
ReAct Agent tool routing
    ├─── graph_rag tool ─────────────────────────────────────┐
    │    (when query needs entity relationships)             │
    │    Entity Embeddings → BFS Subgraph → Edge Scoring     │
    │    → Context: entities + relationships + references    │
    │                                                        │
    ├─── smart_search tool ──────────────────────────────────┐
    │    (when query needs document content)                  │
    │    Multi-concept Weaviate Hybrid → Reranking            │
    │    + Provenance Tracking (NEW)                         │
    │    → Context: ranked document chunks + sources         │
    │                                                        │
    └─── Both can feed into Verified Generation              │
         (claim-by-claim verification, unchanged)            │
```

### What changes vs Phase 1

| Component | Before | After |
|---|---|---|
| Graph retrieval | `graph_expander.py` — URI match, binary signal | `graph_rag.py` — TrustGraph full pipeline |
| Document retrieval | SmartSearch — raw query hybrid search | SmartSearch — concept-based multi-search + provenance |
| Query understanding | Regex entity extraction only | LLM concept extraction (shared) |
| Graph signal | Binary (0/1) in 5-signal reranking | Continuous edge score (0.0-1.0) |
| Provenance | None | PROV-O triples tracking retrieval chain |
| Tool routing | `smart_search` only (graph is a side signal) | Agent chooses `graph_rag` or `smart_search` |

### What stays unchanged

- LangGraph ReAct agent (8 nodes, 13 tools + 2 new)
- Verified Generation (claim-by-claim)
- User memory (AsyncPostgresStore)
- LLM: Qwen3.5-9B single model
- FalkorDB schema (`:Node`/`:Literal`/`:Rel` from Phase 1)
- Weaviate for document chunks (existing collections)
- Langfuse for prompt management

## 2. Component 1: Shared Concept Extraction

Adopted from TrustGraph `extract_concepts`. Runs once per query, results shared by both pipelines.

**Location**: `emma-agent-service/app/agents/langgraph/tools/concept_extractor.py` (NEW)

```python
async def extract_concepts(query: str) -> ConceptResult:
    """Decompose query into high-level themes and low-level entities.

    Returns ConceptResult with:
        high_level: ["derecho laboral", "fiscalidad"]
        low_level: ["LGT", "Juan García", "contrato temporal"]
        embeddings: {concept: vector}  # pre-computed for reuse

    Fallback: regex entity extraction on LLM failure.
    """
```

**LLM call**: Langfuse prompt `trustgraph_extract_concepts`
**Embedding**: batch embed all concepts via intelligence-docs-service (reused by both pipelines)
**Latency**: ~200ms (LLM) + ~20ms (embeddings)

### Why shared

TrustGraph extracts concepts independently for Graph RAG and Document RAG. We extract once and share:
- Graph RAG uses concept embeddings for entity similarity search
- SmartSearch uses concept embeddings for multi-concept hybrid search
- Saves one LLM call (~200ms) vs TrustGraph's approach

## 3. Component 2: Graph RAG Pipeline (NEW)

Full TrustGraph-validated retrieval via knowledge graph. Registered as ReAct tool `graph_rag`.

**Location**: `emma-agent-service/app/agents/langgraph/tools/graph_rag.py` (NEW, replaces `graph_expander.py`)

### Pipeline (6 stages)

#### Stage 1: Entity Retrieval (from shared concepts)

```python
async def get_entities(concept_embeddings: dict, tenant_id: str,
                       collection: str, limit: int = 50) -> list[EntityMatch]:
```

- Vector similarity search on Weaviate `TrustGraphEntities` collection
- Per-concept limit: `max(1, entity_limit // len(concepts))`
- Deduplication by `entity_uri`, keep highest score
- Returns: `[{entity_uri, label, definition, type, score}]`
- Latency: ~10ms

#### Stage 2: BFS Subgraph Traversal

```python
async def get_subgraph(seed_entities: list[str], tenant_id: str,
                       max_hops: int = 2, max_edges: int = 150,
                       triples_per_entity: int = 30) -> set[Triple]:
```

- Iterative BFS via KTS `/triples/neighbors` (batch endpoint)
- Filters: skip `prov/*` predicates, skip `core/label` (resolved separately)
- Bounds: `max_hops=2`, `max_edges=150`
- Latency: ~30ms

#### Stage 3: Label Resolution

```python
async def resolve_labels(subgraph: set, tenant_id: str) -> LabeledGraph:
```

- LRU cache: `TTLCache(maxsize=2000, ttl=300)`, key `{tenant_id}:{uri}`
- Batch query `by_spo(uri, core/label)` for all unique URIs
- Fallback: URI last segment humanized
- Latency: ~5ms (cache hits)

#### Stage 4: Semantic Pre-filter

```python
async def prefilter_edges(labeled_edges: list, concept_embeddings: dict,
                          limit: int = 30) -> list:
```

- Embed edge descriptions: `"{subject}, {predicate}, {object}"`
- Cosine similarity against concept vectors
- Keep top 30 by max similarity
- Latency: ~20ms

#### Stage 5: LLM Edge Scoring

```python
async def score_edges(query: str, edges: list, limit: int = 25) -> list:
```

- Langfuse prompt `trustgraph_edge_scoring`
- Input: query + 30 edges as JSON
- Output: `[{id, score}]` — keep top 25
- Latency: ~200ms

#### Stage 6: Context Formatting (TrustGraph-style)

```python
def format_graph_context(scored_edges: list, uri_map: dict) -> GraphRAGResult:
```

Output format (injected into ReAct system prompt):

```markdown
## Knowledge Graph Context

### Entities
[{"name": "LGT", "type": "law", "definition": "Ley General Tributaria..."}]

### Relationships
[{"subject": "Art. 6 RF", "predicate": "regulado-por", "object": "LGT", "score": 0.92}]

### Source Documents
[R1] MM1VMAJ015XXXX.pdf
[R2] 09_impugnacion_testamento.md
```

Returns: `GraphRAGResult(context_text, expanded_doc_ids, avg_score)`

### Provenance (NEW — adopted from TrustGraph)

Each Graph RAG execution emits PROV-O triples to FalkorDB:
- `prov/question` → original query
- `prov/grounding` → extracted concepts
- `prov/exploration` → retrieved entity URIs + subgraph size
- `prov/synthesis` → selected edge IDs + scores

Stored under `user=tenant_id`, `collection="_provenance"`.

## 4. Component 3: SmartSearch Improvements

SmartSearch stays as the document retrieval pipeline. Two improvements adopted from TrustGraph:

### 4.1 Multi-concept search (replaces single-query hybrid)

**Current**: `weaviate_client.hybrid_search(query=raw_query, ...)`

**New**: For each low-level concept from shared extraction, run independent hybrid search:

```python
async def _multi_concept_search(concepts: list[str],
                                concept_embeddings: dict,
                                tenant_id: str, ...) -> list:
    """Run independent hybrid search per concept, merge + dedup."""
    per_concept_limit = max(3, total_limit // len(concepts))
    tasks = [
        weaviate_client.hybrid_search(
            query=concept,
            query_embedding=concept_embeddings[concept],
            limit=per_concept_limit, ...
        )
        for concept in concepts
    ]
    results = await asyncio.gather(*tasks)
    return _merge_and_dedup(results)
```

**Why**: TrustGraph's multi-concept search reduces hallucination from poor single-query embedding. If one concept embedding is weak, others still retrieve relevant chunks.

**Fallback**: If concept extraction fails, falls back to current single-query hybrid search.

### 4.2 Retrieval provenance tracking

Same PROV-O pattern as Graph RAG:
- Track which concepts → which chunks → which synthesis
- Stored in FalkorDB under `collection="_provenance"`
- Enables post-hoc audit: "why did Emma say X?" → trace to specific chunks

### 4.3 Graph signal upgrade

The reranking `graph` signal changes from binary to continuous:
- **Before**: `1.0 if doc_id in graph_doc_ids else 0.0`
- **After**: If Graph RAG ran, use `avg_edge_score` for docs found via subgraph provenance. If not, use binary from entity URI match (backward compat).

### What stays in SmartSearch

- Weaviate hybrid search (BM25 + vector)
- 5-signal reranking (similarity, quality, graph, recency, entity)
- Enrichment filters (domain, semantic_type, person, date)
- Progressive filter fallback
- ACL/tenant isolation
- PublicKnowledge legislation search (if applicable)

## 5. Component 4: Weaviate Collection `TrustGraphEntities`

New collection for entity embeddings.

| Property | Type | Description |
|----------|------|-------------|
| `entity_uri` | TEXT | Canonical URI |
| `label` | TEXT | Human-readable name |
| `definition` | TEXT | Entity definition (may be empty) |
| `entity_type` | TEXT | Semantic type (person, law, org, etc.) |
| `tenant_id` | TEXT | Tenant isolation |
| `collection` | TEXT | Collection scope |
| `embed_text` | TEXT | Text embedded: `"{label} ({type}). {definition}"` |

**Vector**: BGE-M3, 1024 dims, HNSW cosine. External embeddings via intelligence-docs-service.

**Population**: New step in `reindex_trustgraph.py` after triple extraction:
1. Query all `:Node` entities with `core/label` + `core/type` + `core/definition`
2. Build embed text: `"{label} ({type}). {definition}"`
3. Batch embed via intelligence-docs-service
4. Upsert to Weaviate `TrustGraphEntities`

## 6. Component 5: New Langfuse Prompts (3)

### `trustgraph_extract_concepts`

```
You are a query analysis expert. Extract key concepts from the user query
for knowledge graph and document retrieval.

Return TWO types:
1. high_level_keywords: overarching themes, subject areas, legal domains
2. low_level_keywords: specific entities, proper nouns, legal references, dates, amounts

Query: {query}

Respond ONLY with valid JSON:
{"high_level_keywords": ["..."], "low_level_keywords": ["..."]}
```

### `trustgraph_edge_scoring`

```
Score the relevance of each knowledge graph edge to the user query.
Score 0 (irrelevant) to 10 (highly relevant).
Only consider edges that directly help answer the question.

Query: {query}

Edges:
{edges_json}

Respond with a JSON array: [{"id": "edge_id", "score": N}]
Only include edges with score > 0.
```

### `trustgraph_provenance_seed` (for seeding provenance prompt names)

Minimal — just registers the prompt names in the registry for consistency.

## 7. Component 6: New KTS Endpoint

### `POST /triples/neighbors`

Batch BFS traversal endpoint. More efficient than N individual `/triples/query` calls.

```python
# Request
{
    "tenant_id": "...",
    "seed_uris": ["nouxcube://entity/default/lgt", ...],
    "max_hops": 2,
    "max_edges": 150,
    "triples_per_entity": 30,
    "exclude_predicates": ["prov/.*"]
}

# Response
{
    "edges": [{"subject": "...", "predicate": "...", "object": "...", "object_type": "node|literal"}],
    "entities_visited": 42,
    "hops_used": 2
}
```

## 8. Tool Registration

Two new ReAct tools in `tools/registry.py`:

| Tool | When used | Description |
|------|-----------|-------------|
| `graph_rag` | Query needs entity relationships, cross-document patterns, legal references | Full Graph RAG: entity similarity → subgraph → edge scoring → context |
| `smart_search` | Query needs document content, specific text passages, data lookups | Multi-concept hybrid search with provenance |

Both tools can be called in the same ReAct turn. The agent can call `graph_rag` first for relationship context, then `smart_search` for specific document details.

## 9. Deprecations

| Component | Status | Replacement |
|-----------|--------|-------------|
| `graph_expander.py` | **DEPRECATED** | `graph_rag.py` |
| `_get_documents_by_person()` | **REMOVED** | BFS subgraph covers this |
| Single-query hybrid search in SmartSearch | **REPLACED** | Multi-concept search (with fallback) |
| `SMART_SEARCH_GRAPH_ENABLED` flag | **REPLACED** | `GRAPH_RAG_ENABLED` |

## 10. Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPH_RAG_ENABLED` | `true` | Enable Graph RAG tool |
| `GRAPH_RAG_ENTITY_LIMIT` | `50` | Max entities from vector search |
| `GRAPH_RAG_MAX_HOPS` | `2` | BFS depth |
| `GRAPH_RAG_MAX_EDGES` | `150` | Max edges in subgraph |
| `GRAPH_RAG_EDGE_LIMIT` | `25` | Max edges after LLM scoring |
| `GRAPH_RAG_PREFILTER_LIMIT` | `30` | Semantic pre-filter limit |
| `GRAPH_RAG_LABEL_CACHE_TTL` | `300` | Label cache TTL (seconds) |
| `SMART_SEARCH_MULTI_CONCEPT` | `true` | Enable multi-concept search |
| `RETRIEVAL_PROVENANCE_ENABLED` | `true` | Track retrieval provenance |

## 11. Latency Budget

### Graph RAG tool call

| Step | Time | Notes |
|------|------|-------|
| Concept extraction (shared, LLM) | ~200ms | Once per query |
| Entity similarity (Weaviate) | ~10ms | |
| BFS traversal (FalkorDB) | ~30ms | Batch async |
| Label resolution | ~5ms | Cached |
| Semantic pre-filter (embeddings) | ~20ms | Reuses concept embeddings |
| Edge scoring (LLM) | ~200ms | |
| **Total** | **~465ms** | |

### SmartSearch tool call (improved)

| Step | Time | Notes |
|------|------|-------|
| Concept extraction (shared, already done) | 0ms | Reused |
| Multi-concept hybrid search | ~150ms | N parallel searches |
| Reranking | ~5ms | |
| Provenance emission | ~5ms | Async, non-blocking |
| **Total** | **~160ms** | (vs ~200ms current) |

## 12. Testing Strategy

1. **Unit tests**: Each stage mocked independently
2. **Integration test**: Graph RAG with real FalkorDB + mocked LLM
3. **Sanity checks**: Add to `/diagnostics/sanity`:
   - `graph_rag_concept_extraction` — verify LLM returns valid concepts
   - `graph_rag_entity_retrieval` — verify Weaviate returns entities
   - `graph_rag_subgraph_traversal` — verify BFS returns edges
   - `smart_search_multi_concept` — verify multi-search returns results
4. **Provenance audit**: `/diagnostics/provenance/{query_id}` — trace retrieval chain

## 13. File Impact Summary

| File | Change | Lines est. |
|------|--------|-----------|
| `emma/tools/graph_rag.py` | **NEW** | ~400 |
| `emma/tools/concept_extractor.py` | **NEW** | ~80 |
| `emma/tools/smart_search.py` | **MODIFY** — multi-concept + provenance | ~100 |
| `emma/tools/registry.py` | **MODIFY** — register graph_rag tool | ~10 |
| `emma/sectors/graph_expander.py` | **DEPRECATE** | — |
| `emma/nodes/memory_recall.py` | **MODIFY** — graph_context injection | ~20 |
| `kts/api/triples.py` | **MODIFY** — add /neighbors | ~40 |
| `kts/services/triple_query.py` | **MODIFY** — batch_neighbors() | ~60 |
| `kts/scripts/reindex_trustgraph.py` | **MODIFY** — entity embedding step | ~80 |
| `kts/scripts/seed_langfuse_extraction_prompts.py` | **MODIFY** — 3 new prompts | ~30 |
| `weaviate-service/services/weaviate_service.py` | **MODIFY** — TrustGraphEntities | ~50 |
| `weaviate-service/api/weaviate.py` | **MODIFY** — entity search endpoint | ~30 |
| **Total new/modified** | | **~900 lines** |
