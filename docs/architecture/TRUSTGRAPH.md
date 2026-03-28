# TrustGraph — Knowledge Graph Triple Store

NouxCube's knowledge graph uses a **TrustGraph-model RDF-style triple store** implemented on FalkorDB. Documents are processed by 4 parallel LLM extractors that produce semantic triples (subject-predicate-object) with W3C PROV-O provenance tracking and automatic contradiction detection.

The model is based on [TrustGraph](https://github.com/trustgraph-ai/trustgraph) (Apache 2.0), adapted to our stack: Celery replaces Apache Pulsar, Langfuse replaces ConfigService prompts, Weaviate (BGE-M3) replaces Qdrant embeddings, and SGLang (Qwen3.5-9B) replaces the multi-provider LLM layer.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     INGESTION PIPELINE                           │
│                                                                  │
│  Document ingested (PDF, text, DB row, API)                      │
│       │                                                          │
│       ▼                                                          │
│  intelligence-docs-svc ──→ text extraction + chunking            │
│       │                                                          │
│       ▼ chunks[]                                                 │
│  weaviate-svc ──→ Weaviate hybrid index (unchanged)              │
│       │                                                          │
│       ▼ POST /extract/triples                                    │
│  knowledge-tree-svc ──→ ExtractionCoordinator                    │
│       │                                                          │
│       │  launches 4 extractors in parallel per chunk              │
│       ▼                                                          │
│  ┌────────────┬────────────────┬─────────────┬──────────┐        │
│  │ definitions│ relationships  │ objects     │ topics   │        │
│  │ (what ARE) │ (how RELATE)   │ (NER+type) │ (ABOUT)  │        │
│  └─────┬──────┴───────┬────────┴──────┬──────┴────┬─────┘        │
│        └──────────────┴───────────────┴───────────┘              │
│                        │                                         │
│                        ▼                                         │
│              Triple Aggregator                                   │
│              Dedup + URI normalization                            │
│              → FalkorDB write (MERGE)                            │
│              → PROV-O provenance triples                         │
│              → Contradiction detection                           │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                      QUERY PATH                                  │
│                                                                  │
│  Emma ReAct Agent                                                │
│       │                                                          │
│       ▼                                                          │
│  SmartSearch → graph_expander → KTS /triples/query               │
│                                  → 8 SPO query patterns          │
│                                  → build_context() for LLM       │
│       │                                                          │
│       ▼                                                          │
│  Synthesize → triples + provenance + contradictions in prompt    │
└──────────────────────────────────────────────────────────────────┘
```

## FalkorDB Schema — TrustGraph Pure Model

Everything is represented with 3 label types and 1 edge type:

| Label | Purpose | Key Properties |
|-------|---------|----------------|
| `:Node` | Named entities, documents, folders, concepts | `uri`, `user` (tenant), `collection`, `created_at` |
| `:Literal` | Scalar values (dates, amounts, descriptions) | `value`, `user`, `collection` |
| `:Rel` | ALL semantic relationships | `uri` (predicate), `user`, `collection`, `extraction_method`, `source_chunk`, `valid_from`, `valid_until` |
| `:CollectionMetadata` | Lifecycle sentinel per collection | `user`, `collection`, `created_at`, `source_type` |

### URI Scheme

```
Entities:     nouxcube://entity/{collection}/{url-safe-lowercase-name}
Documents:    nouxcube://document/{collection}/{document_id}
Folders:      nouxcube://folder/{collection}/{folder_path_hash}
DB rows:      nouxcube://dbrow/{connector_id}/{table}/{primary_key}
Predicates:   nouxcube://predicate/{ontology_name}/{predicate_name}
Extractions:  nouxcube://extraction/{uuid}
```

Laws are NOT a special type — they are documents with `(doc, core/type, "legislation")` triples.

### Indexes (9 total)

```cypher
CREATE INDEX FOR (n:Node) ON (n.uri);
CREATE INDEX FOR (n:Node) ON (n.user, n.collection);
CREATE INDEX FOR (l:Literal) ON (l.value, l.user, l.collection);
CREATE INDEX FOR (l:Literal) ON (l.user, l.collection);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.uri);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.user, r.collection);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.user, r.collection, r.uri);
CREATE INDEX FOR (c:CollectionMetadata) ON (c.user, c.collection);
CALL db.idx.fulltext.createNodeIndex('Node', 'uri');
```

### Example — Employment Contract

```cypher
// Entity nodes
(:Node {uri: "nouxcube://entity/default/juan-garcia"})
(:Node {uri: "nouxcube://entity/default/techcorp-sl"})
(:Node {uri: "nouxcube://document/default/contrato-2025-001"})

// Literal values
(:Literal {value: "30000 EUR"})
(:Literal {value: "Juan García López"})

// Semantic relationships (all :Rel with predicate URIs)
(juan)-[:Rel {uri: "nouxcube://predicate/core/label"}]->(juan_name)
(juan)-[:Rel {uri: "nouxcube://predicate/core/type"}]->(:Literal {value: "person"})
(juan)-[:Rel {uri: "nouxcube://predicate/legal/empleado-de"}]->(techcorp)
(juan)-[:Rel {uri: "nouxcube://predicate/legal/salario-bruto-anual"}]->(salary)

// Provenance
(:Node {uri: "nouxcube://extraction/ext-001"})
    -[:Rel {uri: "nouxcube://predicate/prov/derived-from"}]->(contrato)
(:Node {uri: "nouxcube://extraction/ext-001"})
    -[:Rel {uri: "nouxcube://predicate/prov/model"}]->(:Literal {value: "Qwen3.5-9B"})
```

## 4 LLM Extractors

All extractors inherit from `BaseExtractor`, which handles SGLang HTTP calls and JSON parsing. Each extractor implements `_build_prompt()` and `_parse_output()` only.

| Extractor | What it extracts | Output triples | Langfuse prompt |
|-----------|-----------------|----------------|-----------------|
| **Definitions** | What entities ARE (descriptions) | `(entity, core/label, name)` + `(entity, core/definition, description)` | `trustgraph_extract_definitions` |
| **Relationships** | How things RELATE (SPO triples) | `(subject, predicate_uri, object)` | `trustgraph_extract_relationships` |
| **Objects** | Named entities with type (NER) | `(entity, core/label, name)` + `(entity, core/type, type)` | `trustgraph_extract_objects` |
| **Topics** | Thematic categories | `(document, core/has-topic, topic_entity)` | `trustgraph_extract_topics` |

The `ExtractionCoordinator` runs all 4 in parallel per chunk via `asyncio.gather`, deduplicates results by URI, stores triples, records provenance, and runs contradiction detection.

### Provenance (PROV-O)

Each extraction batch creates a provenance `:Node` with 6 triples:

| Predicate | Value |
|-----------|-------|
| `prov/derived-from` | Source document `:Node` URI |
| `prov/method` | Extraction algorithm (`llm_relationships`, `llm_definitions`, etc.) |
| `prov/model` | LLM model name (`Qwen3.5-9B`) |
| `prov/timestamp` | ISO-8601 UTC datetime |
| `prov/chunk-text` | First 500 chars of source chunk |
| `prov/chunk-offset` | Character offset of chunk in document |

### Contradiction Detection

After all extractors finish for a document, `ContradictionDetector` finds cases where the same subject + same predicate have different literal values from different sources:

```cypher
MATCH (s:Node {uri: $uri})-[r1:Rel]->(o1:Literal)
WHERE r1.user = $user
MATCH (s)-[r2:Rel]->(o2:Literal)
WHERE r2.uri = r1.uri AND r2.user = $user
  AND id(o1) < id(o2) AND o1.value <> o2.value
RETURN DISTINCT r1.uri AS predicate, o1.value AS value_a, o2.value AS value_b
```

Each contradiction becomes a first-class `:Node` (`nouxcube://contradiction/{uuid}`) with edges to the subject, predicate, and both conflicting values — queryable and visualizable in the Knowledge Graph 3D.

## Mini-Ontology

32 predicates seeded via `scripts/seed_ontology.py`, stored in `_ontology` collection, user=`_system`:

| Namespace | Count | Examples |
|-----------|-------|---------|
| `core/` | 12 | `label`, `definition`, `type`, `has-topic`, `mentioned-in`, `contained-in`, `part-of`, `instance-of`, `supports`, `contradicts`, `semantic-type`, `domain` |
| `legal/` | 14 | `empleado-de`, `firmante-de`, `regulado-por`, `vigente-desde`, `tipo-contrato`, `salario-bruto`, `clausula`, `derogado-por` |
| `prov/` | 6 | `derived-from`, `method`, `model`, `timestamp`, `chunk-text`, `chunk-offset` |

## API Endpoints (knowledge-tree-service, port 8011)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/extract/triples` | POST | Full LLM extraction from document chunks |
| `/extract/structural` | POST | Metadata-only node creation (no LLM) |
| `/triples/query` | POST | 8 SPO query patterns |
| `/triples/context` | POST | Build LLM context from graph triples |
| `/triples/stats` | GET | Node, literal, rel, and contradiction counts |
| `/triples/clear` | DELETE | Clear tenant graph |
| `/health` | GET | Health check |

### Triple Query Patterns

The `TripleQuery` service supports 8 SPO combinations via `/triples/query`:

| Fields provided | Query pattern |
|----------------|---------------|
| `subject_uri` + `predicate_uri` | All objects for that subject+predicate |
| `subject_uri` only | All triples about that subject |
| `predicate_uri` + `object_value` | All subjects with that predicate→object |
| `predicate_uri` only | All triples using that predicate |
| `object_value` (node) | All triples pointing to that object node |
| `object_value` (literal) | All triples with that literal value |
| All three | Exact SPO match |
| None | Recent triples (limited) |

Additionally, `build_context()` assembles a formatted text block from graph triples suitable for injection into LLM prompts.

## Cross-Service Integration

### weaviate-service (port 8007)

The indexing pipeline (`extraction_service.py`) calls `POST /extract/triples` on KTS after Weaviate indexing completes. The request includes tenant_id, document_id, chunks, and document metadata (title, file_path, semantic_type, domain).

### emma-agent-service (port 8009)

- **graph_expander.py**: Rewritten for `:Node`/`:Rel` triple queries (used by SmartSearch for graph expansion)
- **entity_extractor.py**: KEPT — still used by `smart_search.py` for regex-based filter enrichment (separate from LLM extraction)
- **structural_query tool**: Rewritten for `:Node`/`:Rel` model

### background-worker

- Celery queue: `trustgraph_extraction`
- 2 tasks: extraction coordinator + reindex

## Reindexation

Full graph rebuild script for a tenant:

```bash
# Standard reindex
docker compose exec knowledge-tree-service \
    python scripts/reindex_trustgraph.py --tenant-id TENANT_ID

# Dry run (show what would happen)
docker compose exec knowledge-tree-service \
    python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --dry-run

# Single collection only
docker compose exec knowledge-tree-service \
    python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --collection legal

# Incremental (skip graph clear)
docker compose exec knowledge-tree-service \
    python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --skip-clear
```

**Pipeline**:
1. Clear existing graph for tenant (unless `--skip-clear`)
2. Re-create indexes (bootstrap schema)
3. Seed mini-ontology (32 predicates)
4. Fetch document list from weaviate-service
5. For each document: get chunks → run 4 extractors in parallel → store triples → provenance → contradictions

**Estimated throughput** (~300ms per chunk, 4 extractors in parallel):
- 10-chunk document: ~3 seconds
- 100 documents: ~5 minutes
- 1000 documents: ~50 minutes
- BOE (47 laws, ~500 chunks): ~2.5 minutes

## Setup After Deployment

```bash
# 1. Seed ontology (32 predicates)
docker compose exec knowledge-tree-service python scripts/seed_ontology.py

# 2. Seed Langfuse extraction prompts (4 prompts)
docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py

# 3. Reindex graph for tenant
docker compose exec knowledge-tree-service \
    python scripts/reindex_trustgraph.py --tenant-id 00000000-0000-0000-0000-000000000001
```

## Implementation Phases

### Phase 1: Automated Ingest (COMPLETE)

Schema migration, 4 LLM extractors, PROV-O provenance, contradiction detection, mini-ontology, API endpoints, cross-service integration, reindexation script. KTS fully rewritten: 18 commits, 59 files changed, +6,107 / -7,658 lines (net -1,551). 92 tests.

### Phase 2: Semantic Similarity Retrieval (PLANNED)

- Entity embeddings in Weaviate (`TrustGraphEntities` collection)
- Subgraph extractor rewrite for semantic similarity retrieval
- `trustgraph_context.py` — format triples + provenance for ReAct prompts
- Frontend 3D/2D graph adaptation for `:Node`/`:Rel` rendering
- `rerank_weights` migration to graph triples

### Phase 3: Ontology Structuring (PLANNED)

- Ontology RAG — vectorize predicates in Weaviate `OntologyTerms` collection
- Per-sector predicate catalog (core ~10, legal ~25, medical ~20, documental ~15)
- Binary validation against ontology (invalid predicates discarded)
- Authority weight triples (`trust/authority-weight` per document type)
- Source authority via Cypher queries — zero hardcode in application code

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Model | TrustGraph Pure (`:Node`/`:Literal`/`:Rel`) | Uniform model for multi-source evaluation |
| Graph DB | FalkorDB (keep) | Already in stack, Apache 2.0, TrustGraph has production support |
| Trust scoring | None | TrustGraph itself has no trust scoring — LLM reasons over provenance + contradictions |
| Laws | Not a special URI — documents with `type=legislation` | Uniform model, no special-casing |
| Ontology | Phase 1: free extraction; Phase 3: closed per sector | Incremental precision |
| Existing data | Delete and reindex | Clean migration |

## Key Files

| File | Purpose |
|------|---------|
| `knowledge-tree-service/app/services/triple_store.py` | CRUD: MERGE Node, MERGE Literal (dedup), CREATE Rel |
| `knowledge-tree-service/app/services/triple_query.py` | 8 SPO query patterns + `build_context()` |
| `knowledge-tree-service/app/services/uri_builder.py` | Canonical URI generation + Spanish name normalization |
| `knowledge-tree-service/app/services/provenance.py` | PROV-O triples per extraction batch |
| `knowledge-tree-service/app/services/contradiction.py` | Batch contradiction detection + `:Node` creation |
| `knowledge-tree-service/app/services/extractors/base.py` | Base extractor: SGLang HTTP call + JSON parse |
| `knowledge-tree-service/app/services/extractors/coordinator.py` | Orchestrates 4 extractors, dedup, store, provenance |
| `knowledge-tree-service/app/services/extractors/definitions.py` | Definitions extractor |
| `knowledge-tree-service/app/services/extractors/relationships.py` | Relationships extractor |
| `knowledge-tree-service/app/services/extractors/objects.py` | Objects/NER extractor |
| `knowledge-tree-service/app/services/extractors/topics.py` | Topics extractor |
| `knowledge-tree-service/app/api/triples.py` | REST endpoints: query, stats, context, clear |
| `knowledge-tree-service/app/api/extract.py` | REST endpoint: trigger extraction |
| `knowledge-tree-service/app/schemas/triples.py` | 13 Pydantic models |
| `knowledge-tree-service/scripts/seed_ontology.py` | Seed 32 predicates |
| `knowledge-tree-service/scripts/seed_langfuse_extraction_prompts.py` | Seed 4 Langfuse prompts |
| `knowledge-tree-service/scripts/reindex_trustgraph.py` | Full graph rebuild |
| `knowledge-tree-service/config/graphs/trustgraph_schema.cypher` | FalkorDB indexes |
| `emma-agent-service/app/agents/langgraph/sectors/graph_expander.py` | Graph expansion for SmartSearch (`:Node`/`:Rel`) |

## Reference

- **TrustGraph repo**: https://github.com/trustgraph-ai/trustgraph
- **TrustGraph docs**: https://docs.trustgraph.ai/
- **Design spec**: `docs/superpowers/specs/2026-03-26-trustgraph-triplet-extraction-design.md`
- **Phase 1 plan**: `docs/superpowers/plans/2026-03-27-trustgraph-phase1-automated-ingest.md`
