# LangGraph Layer Audit: FalkorDB Migration Readiness

**Date**: 2026-03-23
**Status**: Reference document for Phase 2-3
**Service**: `backend/microservices/emma-agent-service/`
**Related spec**: `2026-03-23-graphrag-falkordb-migration-design.md`

---

## Critical Issues (must fix before Phase 2)

### 1. AGE SQL-wrapped Cypher constructed in agent layer
**File**: `app/agents/langgraph/sectors/graph_expander.py:124-130`

```python
return (
    f"SELECT * FROM cypher('{graph_name}', $$ "
    f"MATCH (n)-[r]-(m) "
    f"WHERE {where_str} "
    f"RETURN n, type(r) as rel, m LIMIT 10 "
    f"$$) AS (n agtype, rel agtype, m agtype)"
)
```

**Impact**: Breaks immediately with FalkorDB. AGE-specific SQL wrapping and `agtype` references.
**Fix**: Create semantic endpoint `POST /tree/graph/expand-entities` on knowledge-tree-service. Agent sends entity names/types, receives structured results.

### 2. Cypher injection vulnerability
**File**: `app/agents/langgraph/sectors/graph_expander.py:121`

```python
where_clauses = [f"n.{prop} =~ '(?i).*{safe_value}.*'" for prop in props]
```

Only escapes single quotes. Regex metacharacters (`.`, `*`, `|`, `(`, `)`) not escaped.
**Fix**: Use FalkorDB full-text index instead of regex, or properly escape regex metacharacters.

### 3. Hardcoded AGE vlabel as default parameter
**File**: `app/clients/knowledge_tree_client.py:141`

```python
async def get_documents_by_person(
    self, tenant_id: str, person_name: str, entity_type: str = "Persona"
) -> List[str]:
```

**Fix**: Change default to `entity_type: str = "person"` (FalkorDB convention).

### 4. N+1 query pattern
**File**: `app/agents/langgraph/sectors/graph_expander.py:62-81`

Serial HTTP calls in a loop (up to 15+ per request).
**Fix**: Batch into single request or use `asyncio.gather()`.

---

## Hardcoded Values (should configure)

| # | File | Line | Hardcoded Value | Should Be |
|---|------|------|----------------|-----------|
| 5 | `sectors/registry.py` | 66 | `graph_name="knowledge_graph_public"` | `settings.falkordb_graph_name` |
| 6 | `sectors/registry.py` | 115 | `graph_name="medical_graph"` | `settings.falkordb_graph_name` |
| 7 | `sectors/registry.py` | 174 | `graph_name="documental_graph"` | `settings.falkordb_graph_name` |
| 8 | `sectors/registry.py` | 67 | `graph_schema="config/graphs/legal_graph_schema.cypher"` | Remove (schema lives in knowledge-tree-service) |
| 9 | `subgraph_formatter.py` | 150 | `"INSTANCE_OF"`, `"HAS_MEMORY"` | Configurable skip list |
| 10 | `subgraph_formatter.py` | 159 | `"APLICA"` | `"REFERENCES_LAW"` (new naming) |
| 11 | `subgraph_formatter.py` | 174 | `"structural_document"` | `"Document"` (new label) |
| 12 | `subgraph_formatter.py` | 194 | `("unknown", "structural_document", "structural_folder")` | `("unknown", "Document", "Folder")` |
| 13 | `graph_expander.py` | 63 | `values[:5]` | Configurable limit |
| 14 | `graph_expander.py` | 128 | `LIMIT 10` | Configurable limit |
| 15 | `smart_search.py` | 957 | `quality_score: 0.8` | Configurable per sector |
| 16 | `memory_recall.py` | 34 | `_TOPIC_PATTERNS` regex list | Configurable per sector |
| 17 | `react_loop.py` | 57-60 | Email regex patterns | Configurable |
| 18 | `sectors/config.py` | 71 | `graph_name: str` (required) | `Optional[str]` (deprecated with unified graph) |

---

## Bad Patterns (should refactor)

| # | File | Pattern | Fix |
|---|------|---------|-----|
| 19 | `graph_expander.py` (entire module) | Constructs Cypher in agent layer | Move to semantic HTTP endpoint on knowledge-tree-service |
| 20 | `state.py:322-338` | `sector_config` serialization inconsistent between RAGState/ReActState | Align both or remove RAGState path |
| 21 | `state.py:97-270` | RAGState deprecated but `create_initial_state()` still exists | Delete or mark with `@deprecated` |
| 22 | `tenant_knowledge_service.py:87` | **BUG**: `get_weaviate_client` used but not imported | Add import |
| 23 | `weaviate_client.py:60` | Docstring references "Apache AGE graph" | Update to "knowledge graph" |
| 24 | `graph.py:36` | StructuralQueryTool docstring references "Apache AGE" | Update to "FalkorDB" |
| 25 | `smart_search.py:7` | Module docstring references "Apache AGE" | Update to "FalkorDB" |
| 26 | `memory_recall.py:202` | Inconsistent units (chars vs tokens in budget calc) | Standardize to one unit |

---

## FalkorDB Opportunities (Phase 3 enhancements)

### Evidence-aware synthesis
**File**: `app/agents/langgraph/nodes/synthesize_react.py`

With FalkorDB Claims, the synthesize node could:
- Present claim-level evidence with confidence scores
- Highlight contradictions ("Doc A says X, Doc B says Y")
- Include provenance chains ("Extracted from chunk 3, confidence 0.95")

### Claim-based re-ranking signal
**File**: `app/agents/langgraph/tools/smart_search.py`

Add 6th re-ranking signal: `claim_confidence`. Documents with verified high-confidence Claims rank higher.

### Structured Claim recall
**File**: `app/agents/langgraph/nodes/memory_recall.py`

Replace flat text context with structured Claims (statement + source + confidence + contradictions).

### Evidence-annotated subgraphs
**File**: `app/agents/langgraph/tools/subgraph_formatter.py`

Render Claims as evidence annotations in the graph visualization:
```
- Juan Martinez (person)
  -> MENTIONED_IN -> Contrato-2024.pdf [confidence: 0.95]
    Claims:
    - "Firmo el contrato el 15/03/2024" [factual, 0.92]
    - WARNING: CONTRADICTS "Fecha: 22/03/2024" (from Acta-Junta.pdf)
```

### Full-text entity resolution
**File**: `app/agents/langgraph/sectors/graph_expander.py`

Replace regex `=~ '(?i).*value.*'` with FalkorDB full-text index `CALL db.idx.fulltext.queryNodes('Entity', 'value')`.

### Single-roundtrip evidence assembly
**File**: `app/clients/knowledge_tree_client.py:159-182`

Extend `extract_subgraph()` to request Claims (`include_claims=True`), enabling full evidence assembly in one HTTP call.

### Eliminate legacy graph expansion
**File**: `app/agents/langgraph/tools/smart_search.py:357-369`

Once FalkorDB is live, remove the `settings.smart_search_graph_enabled` legacy path. Only GraphRAG path remains.

### Per-sector claim patterns
**File**: `app/agents/langgraph/sectors/config.py`

Add `claim_patterns` field to SectorConfig for fast regex claim extraction (dates, amounts, BOE refs) per sector.

---

## Integration Points (all HTTP calls to knowledge-tree-service)

| Call Site | Endpoint | Backend-agnostic? |
|-----------|----------|-------------------|
| `knowledge_tree_client.get_tree_context()` | `POST /tree/context` | Yes |
| `knowledge_tree_client.get_structural_summary()` | `POST /tree/summary` | Yes |
| `knowledge_tree_client.structural_query()` | `POST /tree/structural/query` | Yes |
| `knowledge_tree_client.graph_query()` | `POST /tree/graph/query` | **NO** -- caller sends raw Cypher |
| `knowledge_tree_client.get_documents_by_person()` | `POST /tree/graph/documents-by-entity` | Mostly (fix default param) |
| `knowledge_tree_client.extract_subgraph()` | `POST /tree/graph/subgraph` | Yes |
| `knowledge_tree_client.store_memory()` | `POST /tree/memory/store` | Yes |
| `knowledge_tree_client.recall_memories()` | `POST /tree/memory/recall` | Yes |
| `knowledge_tree_client.get_memorized_document_ids()` | `GET /tree/memory/` | Yes |

**Only `graph_query()` is problematic** -- the graph_expander constructs AGE SQL. All other endpoints use semantic contracts.

---

## Priority Actions

1. **Immediate**: Fix `get_weaviate_client` import bug in `tenant_knowledge_service.py:87`
2. **Before Phase 2c**: Refactor `graph_expander.py` into semantic endpoint on knowledge-tree-service
3. **Before Phase 2c**: Fix `entity_type="Persona"` default
4. **During Phase 2c**: Update all hardcoded vlabels/edge names
5. **During Phase 2c**: Make `graph_name` optional in SectorConfig
6. **Phase 3**: Implement Claim-aware synthesis and re-ranking
