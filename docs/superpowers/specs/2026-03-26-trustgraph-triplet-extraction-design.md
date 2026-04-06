# TrustGraph Triplet Extraction — Design Spec

**Date**: 2026-03-26
**Status**: Draft
**Scope**: Reimplementation of TrustGraph model in NouxCube on-premise stack

## 1. Objective

Transform NouxCube's knowledge graph from a property-graph with typed labels (`:Entity`, `:Document`, `:Claim`) into a **TrustGraph-model RDF-style triple store** implemented on FalkorDB. The goal is to enable **information evaluation and verification** across diverse sources (documents, database rows, APIs) using LLM-based reasoning over triples with rich provenance.

### What this is NOT

- Not a deployment of TrustGraph as an external service — we reimplement its model in our stack
- Not a trust scoring engine — the LLM reasons over provenance instead of pre-computed scores
- Not a replacement for Weaviate hybrid search — triples complement vector search, they don't replace it

### Key decisions (from brainstorming)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Model | TrustGraph Pure (`:Node`, `:Literal`, `:Rel`) | Uniform model for multi-source evaluation; simpler for small LLMs |
| Graph DB | FalkorDB (keep) | Already in stack, Apache 2.0, TrustGraph has production support |
| Extraction | 4 LLM extractors (definitions, relationships, objects, topics) | Proven TrustGraph architecture |
| LLM | CHAT model (Qwen3.5-9B) for all extractors | Single model simplicity |
| Ontology | Ontology RAG (Phase 3) — closed per sector | Precision extraction with controlled predicates |
| Existing data | Delete and reindex with new pipeline | Clean migration |
| Trust scoring | None — LLM reasons over provenance | TrustGraph itself has no trust scoring; provenance + contradictions are sufficient |
| Phases | 3 phases aligned with TrustGraph capabilities | Automated ingest → Semantic retrieval → Ontology structuring |

## 2. FalkorDB Schema — TrustGraph Pure Model

### Node labels

```cypher
-- Everything with identity: persons, organizations, documents, laws, folders, concepts
:Node {
    uri: STRING,           -- "nouxcube://entity/{collection}/{normalized_name}"
    user: STRING,          -- tenant_id (multi-tenancy)
    collection: STRING,    -- logical grouping ("default", "boe-legal", "nominas-2025")
    created_at: INTEGER    -- timestamp()
}

-- Literal values: dates, amounts, descriptions, booleans
:Literal {
    value: STRING,         -- "30000 EUR", "2025-02-01", "Departamento Legal"
    user: STRING,          -- tenant_id
    collection: STRING
}

-- Collection lifecycle sentinel
:CollectionMetadata {
    user: STRING,
    collection: STRING,
    created_at: INTEGER,
    source_type: STRING    -- "document", "database", "api", "manual"
}
```

### Edge label

```cypher
-- ALL semantic relationships via a single label
:Rel {
    uri: STRING,              -- "nouxcube://predicate/{ontology_name}/{predicate_name}"
    user: STRING,             -- tenant_id
    collection: STRING,
    extraction_method: STRING,-- "llm_relationships", "llm_definitions", "regex", "database_import"
    source_chunk: STRING,     -- source text (immediate provenance)
    valid_from: STRING,       -- temporal validity ISO (nullable)
    valid_until: STRING       -- temporal validity ISO (nullable)
}
```

### URI scheme

```
Entities:     nouxcube://entity/{collection}/{url-safe-lowercase-name}
Documents:    nouxcube://document/{collection}/{document_id}
Folders:      nouxcube://folder/{collection}/{folder_path_hash}
DB rows:      nouxcube://dbrow/{connector_id}/{table}/{primary_key}
Predicates:   nouxcube://predicate/{ontology_name}/{predicate_name}
Extractions:  nouxcube://extraction/{uuid}
```

Documents and laws share the same URI namespace (`nouxcube://document/...`). A law is just a document with `(doc, core/type, "legislation")` triples. No special labels.

### Indexes

```cypher
CREATE INDEX FOR (n:Node) ON (n.uri);
CREATE INDEX FOR (n:Node) ON (n.user, n.collection);
CREATE INDEX FOR (l:Literal) ON (l.user, l.collection, l.value);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.uri);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.user, r.collection);
CALL db.idx.fulltext.createNodeIndex('Node', 'uri');
```

### What disappears from current schema

| Current | Becomes |
|---------|---------|
| `:Entity` | `:Node` with URI `nouxcube://entity/...` |
| `:Document` | `:Node` with URI `nouxcube://document/...` |
| `:Folder` | `:Node` with URI `nouxcube://folder/...` |
| `:Law` | `:Node` with URI `nouxcube://document/{collection}/{boe_id}` + type=legislation triple |
| `:Claim` | Eliminated — replaced by `:Rel` triples with provenance |
| `:DocumentMemory` | `:Node` with URI `nouxcube://memory/...` + definition triples |
| `:EntityType` | Eliminated — types are triples `(node, core/type, "person")` |
| `:MENTIONED_IN` | `:Rel {uri: "nouxcube://predicate/core/mentioned-in"}` |
| `:EXTRACTED_FROM` | `:Rel {uri: "nouxcube://predicate/prov/derived-from"}` |
| `:CONTRADICTS` | `:Rel {uri: "nouxcube://predicate/core/contradicts"}` |
| `:REFERENCES_LAW` | `:Rel {uri: "nouxcube://predicate/legal/references-law"}` |
| `:RELATED_TO` | Eliminated — replaced by specific predicate URIs from ontology |
| `:ABOUT` | Eliminated — relationships are direct SPO triples |
| `:SUPPORTS` | `:Rel {uri: "nouxcube://predicate/core/supports"}` |
| `:INSTANCE_OF` | `:Rel {uri: "nouxcube://predicate/core/instance-of"}` |
| `:HAS_MEMORY` | `:Rel {uri: "nouxcube://predicate/core/has-memory"}` |

### Example — Juan García employment contract

```cypher
// Entity nodes
(:Node {uri: "nouxcube://entity/default/juan-garcia", user: "tenant-1", collection: "default"})
(:Node {uri: "nouxcube://entity/default/techcorp-sl", user: "tenant-1", collection: "default"})
(:Node {uri: "nouxcube://document/default/contrato-2025-001", user: "tenant-1", collection: "default"})

// Literal values
(:Literal {value: "30000 EUR", user: "tenant-1", collection: "default"})
(:Literal {value: "Juan García López", user: "tenant-1", collection: "default"})

// Semantic relationships (all :Rel)
(juan)-[:Rel {uri: "nouxcube://predicate/core/label"}]->(juan_name_literal)
(juan)-[:Rel {uri: "nouxcube://predicate/core/type"}]->(:Literal {value: "person"})
(juan)-[:Rel {uri: "nouxcube://predicate/legal/empleado-de", extraction_method: "llm_relationships"}]->(techcorp)
(juan)-[:Rel {uri: "nouxcube://predicate/legal/salario-bruto-anual"}]->(salary_literal)
(contrato)-[:Rel {uri: "nouxcube://predicate/core/type"}]->(:Literal {value: "contract"})
(contrato)-[:Rel {uri: "nouxcube://predicate/legal/regulado-por"}]->(et_node)

// Provenance
(:Node {uri: "nouxcube://extraction/ext-001"})
    -[:Rel {uri: "nouxcube://predicate/prov/derived-from"}]->
    (contrato)
(:Node {uri: "nouxcube://extraction/ext-001"})
    -[:Rel {uri: "nouxcube://predicate/prov/method"}]->
    (:Literal {value: "llm_relationships"})
(:Node {uri: "nouxcube://extraction/ext-001"})
    -[:Rel {uri: "nouxcube://predicate/prov/model"}]->
    (:Literal {value: "Qwen3.5-9B"})
(:Node {uri: "nouxcube://extraction/ext-001"})
    -[:Rel {uri: "nouxcube://predicate/prov/timestamp"}]->
    (:Literal {value: "2026-03-26T10:30:00Z"})
```

## 3. Extraction Pipeline — 4 LLM Extractors

### Architecture

```
Document ingested (PDF, text, DB row, API)
    │
    ▼
intelligence-docs-svc (existing)
    │ text extraction + chunking (unchanged)
    │
    ▼ chunks[]
knowledge-tree-svc → POST /extract/triples
    │
    │ launches 4 Celery tasks in parallel per chunk
    ▼
┌──────────────┬───────────────┬──────────────┬──────────┐
│ definitions  │ relationships │ objects      │ topics   │
│ (what things │ (how things   │ (named       │ (what    │
│  ARE)        │  RELATE)      │  entities)   │  it's    │
│              │               │              │  ABOUT)  │
└──────┬───────┴───────┬───────┴──────┬───────┴────┬─────┘
       │               │              │            │
       └───────────────┴──────────────┴────────────┘
                        │
                        ▼
              Triple Aggregator
              Dedup + URI normalization
              → FalkorDB write (MERGE)
              → Provenance triples (PROV-O)
              → Contradiction detection
              → Entity embedding (Weaviate, Phase 2+)
```

### Extractor 1: `extract_definitions`

Extracts what entities ARE — definitions, descriptions.

- **Input**: chunk text
- **Output**: `[{"entity": "TechCorp SL", "definition": "Empresa tecnológica con CIF B12345678"}]`
- **Generates 2 triples per entity**:
  - `(entity_uri, core/label, "TechCorp SL")`
  - `(entity_uri, core/definition, "Empresa tecnológica...")`
- **Langfuse prompt**: `trustgraph_extract_definitions` with `{text}` variable

### Extractor 2: `extract_relationships`

Extracts how things RELATE — subject-predicate-object semantic triples.

- **Input**: chunk text + relevant ontology predicates (Phase 3: via Ontology RAG)
- **Output**: `[{"subject": "Juan García", "predicate": "empleado-de", "object": "TechCorp SL", "object-entity": true}]`
- **Generates 1 triple per relationship**:
  - `(subject_uri, predicate_uri, object_uri)` if object-entity=true
  - `(subject_uri, predicate_uri, literal_value)` if object-entity=false
- **Langfuse prompt**: `trustgraph_extract_relationships` with `{text}` and `{ontology}` (Phase 3) variables
- **Most important extractor** — produces the semantic relationships the LLM uses for verification

### Extractor 3: `extract_objects`

Extracts named entities with type classification.

- **Input**: chunk text
- **Output**: `[{"name": "Juan García López", "type": "person"}]`
- **Generates 2 triples per entity**:
  - `(entity_uri, core/label, "Juan García López")`
  - `(entity_uri, core/type, "person")`
- **Langfuse prompt**: `trustgraph_extract_objects` with `{text}` variable
- **Replaces current NER** (`openai_ner_provider.py`) — same function, triple output format

### Extractor 4: `extract_topics`

Extracts thematic categories for indexing.

- **Input**: chunk text
- **Output**: `[{"topic": "derecho laboral"}, {"topic": "contratación temporal"}]`
- **Generates 1 triple per topic**:
  - `(document_uri, core/has-topic, topic_entity_uri)`
- **Langfuse prompt**: `trustgraph_extract_topics` with `{text}` variable

### Non-document sources

For data that isn't a document (SQL rows, API responses), skip chunking and generate a pseudo-chunk per row/record:

```python
# Payroll table row for Juan García:
pseudo_chunk = """
Registro de nómina:
- Empleado: Juan García López (NIF: 12345678A)
- Empresa: TechCorp SL
- Salario bruto mensual: 2.500 EUR
- Departamento: Legal
- Fecha alta: 01/02/2025
"""
# → Passed to the 4 extractors as any other chunk
# → collection: "nominas-2025" (separate from document collections)
```

### Prompts in Langfuse

| Prompt ID | Extractor | Variables | Response type |
|-----------|-----------|-----------|---------------|
| `trustgraph_extract_definitions` | definitions | `{text}` | json |
| `trustgraph_extract_relationships` | relationships | `{text}`, `{ontology}` (Phase 3) | json |
| `trustgraph_extract_objects` | objects | `{text}` | json |
| `trustgraph_extract_topics` | topics | `{text}` | json |

All prompts versioned in Langfuse for A/B testing. Seed script creates initial versions.

### Provenance (PROV-O simplified)

For each extraction batch, provenance triples are created:

```
(extraction_uri, prov/derived-from, document_uri)     -- source document
(extraction_uri, prov/method, "llm_relationships")     -- extraction method
(extraction_uri, prov/model, "Qwen3.5-9B")            -- LLM model used
(extraction_uri, prov/timestamp, "2026-03-26T10:30Z")  -- when extracted
(extraction_uri, prov/chunk-text, "...source text...")  -- source chunk
(extraction_uri, prov/chunk-offset, "1500")            -- position in document
```

### Contradiction detection

After storing triples, detect contradictions:

```cypher
-- Same subject + same predicate but different object from different sources
MATCH (s:Node)-[r1:Rel]->(o1)
WHERE r1.uri = $predicate_uri AND s.uri = $subject_uri AND r1.user = $tenant_id
MATCH (s)-[r2:Rel]->(o2)
WHERE r2.uri = $predicate_uri AND id(o1) <> id(o2)
RETURN o1, o2
```

When detected, store the contradiction. Since triples are edges (`:Rel`) and FalkorDB cannot create edges between edges, we track contradictions by linking the two object nodes that disagree for the same subject+predicate combination:

```cypher
-- Example: Juan's salary is 30K (doc A) vs 28K (doc B)
-- Both o1 (:Literal "30000 EUR") and o2 (:Literal "28000 EUR") are targets of
-- (juan)-[:Rel {uri: "legal/salario-bruto"}]->(o1|o2)
-- We create a contradiction node that references both:
CREATE (c:Node {
    uri: "nouxcube://contradiction/{uuid}",
    user: $tenant_id,
    collection: $collection
})
CREATE (c)-[:Rel {uri: "nouxcube://predicate/core/contradiction-subject"}]->(subject_node)
CREATE (c)-[:Rel {uri: "nouxcube://predicate/core/contradiction-predicate"}]->(:Literal {value: $predicate_uri})
CREATE (c)-[:Rel {uri: "nouxcube://predicate/core/contradiction-value-a"}]->(o1)
CREATE (c)-[:Rel {uri: "nouxcube://predicate/core/contradiction-value-b"}]->(o2)
```

This creates a first-class `:Node` for each contradiction, queryable and visualizable in the Knowledge Graph 3D.

## 4. Ontology RAG (Phase 3)

### Ontology storage — triples in the graph

The ontology lives in the graph itself, in a collection `_ontology`:

```
-- Predicate definition
(nouxcube://predicate/legal/empleado-de, onto/label, "Empleado de")
(nouxcube://predicate/legal/empleado-de, onto/domain, "person")
(nouxcube://predicate/legal/empleado-de, onto/range, "organization")
(nouxcube://predicate/legal/empleado-de, onto/description, "Relación laboral entre persona y empresa")
(nouxcube://predicate/legal/empleado-de, onto/sector, "legal")

-- Entity type definition
(nouxcube://type/person, onto/label, "Persona")
(nouxcube://type/person, onto/description, "Persona física identificada por nombre")
(nouxcube://type/person, onto/sector, "core")
```

### Predicate catalog per sector

**Core** (shared across all sectors, ~10 predicates):
- `core/label`, `core/definition`, `core/type`, `core/has-topic`, `core/modifier`
- `core/contradicts`, `core/supports`, `core/instance-of`, `core/has-memory`, `core/mentioned-in`

**Legal** (~25 predicates):
- `legal/empleado-de`, `legal/firmante-de`, `legal/representante-de`
- `legal/regulado-por`, `legal/vigente-desde`, `legal/vigente-hasta`
- `legal/salario-bruto`, `legal/antiguedad-desde`, `legal/categoria-profesional`
- `legal/tipo-contrato`, `legal/jornada-laboral`, `legal/convenio-aplicable`
- `legal/clausula`, `legal/obligacion`, `legal/derecho`, `legal/sancion`
- `legal/articulo-referencia`, `legal/derogado-por`, `legal/modifica`
- `legal/parte-demandante`, `legal/parte-demandada`, `legal/jurisdiccion`
- `legal/cuantia`, `legal/resolucion`, `legal/fecha-efecto`

**Medical** (~20 predicates):
- `medical/diagnosticado-con`, `medical/tratado-con`, `medical/prescrito`
- `medical/alergia`, `medical/fecha-diagnostico`, `medical/medico-responsable`
- `medical/centro-sanitario`, `medical/resultado-prueba`, `medical/dosis`
- `medical/contraindicacion`, `medical/antecedente`
- (full list to be defined during Phase 3 implementation)

**Documental** (~15 predicates):
- `documental/autor-de`, `documental/propietario-de`, `documental/ubicado-en`
- `documental/valorado-en`, `documental/fecha-creacion`, `documental/clasificado-como`
- `documental/relacionado-con`, `documental/pertenece-a`
- (full list to be defined during Phase 3 implementation)

**Provenance** (PROV-O, shared):
- `prov/derived-from`, `prov/generated`, `prov/method`, `prov/model`
- `prov/timestamp`, `prov/chunk-text`, `prov/chunk-offset`

### Ontology RAG flow

```
1. INITIALIZATION (once at service startup):
   - Query FalkorDB for all predicates in sector ontology
   - Vectorize each predicate (label + description) in Weaviate "OntologyTerms" collection

2. PER CHUNK (in relationships extractor):
   - Embed chunk text
   - Similarity search against OntologyTerms → top 15 relevant predicates
   - Inject predicates into Langfuse prompt as {ontology} variable
   - LLM extracts relationships using ONLY those predicates

3. POST-EXTRACTION VALIDATION:
   - Binary pass/fail: does the predicate URI exist in ontology?
   - Invalid predicates logged and discarded
```

### Ontology management

| Operation | Method |
|-----------|--------|
| View ontology | `GET /ontology/predicates?sector=legal` |
| Add predicate | `POST /ontology/predicates` → create triples + re-vectorize in Weaviate |
| Modify predicate | `PUT /ontology/predicates/{uri}` → update triples + re-vectorize |
| Delete predicate | `DELETE /ontology/predicates/{uri}` → remove triples + remove from Weaviate |
| Seed ontology | `python scripts/seed_ontology.py` |

### Source authority — dynamic via graph triples

Source authority is NOT hardcoded. It is defined as triples in the `_ontology` collection:

```
-- Authority weights per document type
(nouxcube://type/legislation,     trust/authority-weight, "1.0")
(nouxcube://type/court_ruling,    trust/authority-weight, "0.95")
(nouxcube://type/contract,        trust/authority-weight, "0.90")
(nouxcube://type/payroll,         trust/authority-weight, "0.85")
(nouxcube://type/database_record, trust/authority-weight, "0.80")
(nouxcube://type/email,           trust/authority-weight, "0.50")

-- Authority boost modifiers
(nouxcube://modifier/signed,    trust/authority-boost, "0.10")
(nouxcube://modifier/notarized, trust/authority-boost, "0.15")
```

Calculated via Cypher query at query-time — zero hardcode in application code. Adding new source types requires only creating triples, no code changes.

## 5. Impact on Existing Services

### knowledge-tree-service (port 8011) — Full rewrite

**Deleted** (all files that assume typed labels):
- `services/claim_extractor.py` — Claims → triples
- `services/entity_graph_bridge.py` — `:Entity` → `:Node`
- `services/structural_indexer.py` — `:Document`/`:Folder` → `:Node`
- `services/subgraph_extractor.py` — typed label queries → `:Rel` URI queries
- `services/memory_bank_service.py` — `:DocumentMemory` → `:Node` with definition triples
- `services/tenant_knowledge_service.py` — typed label queries → rewrite
- `api/claims.py`, `api/entities.py`, `api/legal_links.py`, `api/tree.py`, `api/memory_bank.py`
- `config/graphs/knowledge_graph_schema.cypher`

**Created**:
- `services/triple_store.py` — CRUD of triples in FalkorDB (MERGE Node/Literal/Rel)
- `services/triple_query.py` — 8 SPO query patterns + contradiction queries
- `services/extractors/definitions.py` — Definitions extractor (Celery task)
- `services/extractors/relationships.py` — Relationships extractor (Celery task)
- `services/extractors/objects.py` — Objects/NER extractor (Celery task)
- `services/extractors/topics.py` — Topics extractor (Celery task)
- `services/extractors/coordinator.py` — Orchestrates 4 extractors in parallel per chunk
- `services/ontology_rag.py` — Ontology RAG: vectorize + search predicates (Phase 3)
- `services/ontology_manager.py` — Ontology CRUD as triples
- `services/provenance.py` — PROV-O triple creation per extraction
- `services/uri_builder.py` — Canonical URI generation
- `api/triples.py` — REST endpoints for triple query, contradictions, provenance
- `api/ontology.py` — REST endpoints for ontology management
- `api/extract.py` — Endpoint to trigger triple extraction
- `config/graphs/trustgraph_schema.cypher` — New schema indexes
- `scripts/seed_ontology.py` — Seed base ontology per sector
- `scripts/reindex_trustgraph.py` — Full reindexation script

**Kept unchanged**: `services/falkordb_client.py` (already generic Cypher)

### emma-agent-service (port 8009) — Tool + context adaptation

**Modified**:
- `agents/langgraph/tools/smart_search.py` — Graph expansion queries `:Node`/`:Rel` instead of typed labels
- `agents/langgraph/tools/structural_query.py` — Rewrite for `:Node`/`:Rel` model
- `agents/langgraph/nodes/react_loop.py` — Subgraph context format changes to triples
- `agents/langgraph/nodes/synthesize*.py` — Prompt receives triples with provenance
- `agents/langgraph/sectors/config.py` — `rerank_weights` move to graph triples
- `agents/langgraph/sectors/graph_expander.py` — Rewrite for `:Node`/`:Rel` queries

**Deleted**:
- `agents/langgraph/sectors/entity_extractor.py` — Replaced by KTS 4 extractors

**Created**:
- `services/trustgraph_context.py` — Formats triples + provenance + contradictions for ReAct prompts

### weaviate-service (port 8007) — Moderate changes

**Modified**:
- `services/knowledge/extraction_service.py` — Adapts to new `/extract/triples` endpoint
- `services/knowledge/schemas.py` — `EntityType`/`RelationshipType` enums removed (ontology is in graph)

**Created**:
- Weaviate collection `OntologyTerms` — Vectors of ontology predicates for Ontology RAG
- Weaviate collection `TrustGraphEntities` — Vectors of `:Node` entities for semantic search (Phase 2)

### intelligence-docs-service (port 8012) — Minimal changes

- `providers/entities/openai_ner_provider.py` — Kept as fallback; no longer primary extractor
- `providers/extraction/docling.py` — Unchanged (text/chunk extraction continues as-is)

### background-worker — New Celery tasks

**New tasks** (queue: `trustgraph_extraction`):
- `trustgraph.extract_definitions`
- `trustgraph.extract_relationships`
- `trustgraph.extract_objects`
- `trustgraph.extract_topics`
- `trustgraph.extract_all` — Orchestrator: launches 4 in parallel (Celery chord)
- `trustgraph.reindex_collection` — Full reindexation of a collection

### Frontend — Both graphs adapted

**Knowledge Graph 3D** (`app/knowledge-graph/`):
- `explainability-theme.ts` — Node differentiation by `core/type` triple instead of label
- `ExplainabilityGraph3D.tsx` — Node coloring by type, edge labels from `Rel.uri` last segment
- `NodeDetailsDrawer.tsx` — Shows triples for selected node with provenance + contradictions panel
- `explainability.service.ts` — New endpoints: `/triples/query`, `/triples/contradictions`

**Knowledge Tree 2D** (`app/admin/knowledge-tree/`):
- `graph-theme.ts` — `NodeKind` derived from `core/type` triple
- `ForceGraph.tsx` — Same coloring/labeling changes
- `knowledge-tree.service.ts` — Updated to new triple API endpoints

### Docker — No new containers

- 4 extractors are Celery tasks in existing background-worker
- Ontology RAG uses existing Weaviate + FalkorDB
- Prompts go in existing Langfuse
- New Celery queue `trustgraph_extraction` (config in `docker-compose.onpremise.yml`)

## 6. Implementation Phases

Aligned with TrustGraph's 3 capability levels.

### Phase 1: Automated Ingest — Schema + Extractors + Basic pipeline

**Goal**: Documents in → triples out → FalkorDB stores

| Component | Work |
|-----------|------|
| FalkorDB schema | Migrate to `:Node`/`:Literal`/`:Rel`. Create indexes. Seed script for base triples |
| `triple_store.py` | Triple CRUD (MERGE nodes, create Rel) |
| `uri_builder.py` | Canonical URI generation |
| 4 extractors | Celery tasks with Langfuse prompts. **Free extraction** (no ontology — LLM proposes predicates freely) |
| `coordinator.py` | Orchestrates 4 extractors in parallel per chunk |
| `provenance.py` | PROV-O triples per extraction |
| `triple_query.py` | 8 SPO query patterns |
| API endpoints | `/extract/triples`, `/triples/query`, `/triples/contradictions` |
| Reindexation | Script to delete graph + reindex all documents |
| Langfuse | 4 extraction prompts seeded |

**Result**: Graph has triples with provenance. Predicates are free strings normalized by the LLM.

### Phase 2: Semantic Similarity Retrieval — GraphRAG over triples

**Goal**: ReAct agent can search triples by semantic similarity and assemble context with provenance

| Component | Work |
|-----------|------|
| Entity embeddings | Vectorize each `:Node` (label + definition) in Weaviate `TrustGraphEntities` |
| Subgraph extractor | Rewrite for `:Node`/`:Rel` — multi-hop traversal + contradictions |
| `trustgraph_context.py` | Format triples + provenance for ReAct prompts |
| SmartSearch | Adapt graph expansion to `:Node`/`:Rel` queries |
| Frontend 3D | Adapt ExplainabilityGraph3D for `:Node`/`:Rel` rendering with provenance |
| Frontend 2D | Adapt ForceGraph for new schema |

**Result**: LLM can verify facts citing triples with provenance. Knowledge Graph 3D shows semantic relationships and contradictions.

### Phase 3: Ontology Structuring — Ontology RAG for precision

**Goal**: Predicates controlled by sector ontology, precise extraction

| Component | Work |
|-----------|------|
| Sector ontology | Define predicate catalog as triples in `_ontology` collection |
| `ontology_rag.py` | Vectorize predicates in Weaviate `OntologyTerms`, search top-K per chunk |
| `ontology_manager.py` | Ontology CRUD + API endpoints |
| Post-extraction validation | Binary pass/fail against ontology (as TrustGraph does) |
| Reindexation | Re-extract with Ontology RAG for controlled predicates |
| Authority weights | Define `trust/authority-weight` triples per document type |
| Sector weights | Define `trust/weight-*` triples per sector for scoring signals |

**Result**: Graph with 100% schema-conformant predicates. Zero noise.

## 7. Reindexation Pipeline

Executed at the end of each phase to rebuild the graph cleanly.

```
1. DELETE existing graph
   MATCH (n) DETACH DELETE n

2. Re-create indexes
   → Execute trustgraph_schema.cypher

3. Seed base ontology
   → python scripts/seed_ontology.py (core types, base predicates, authority weights)

4. Get document list from PostgreSQL
   → SELECT * FROM indexed_documents WHERE tenant_id = $tid

5. For each document:
   a. Get chunks from Weaviate (already exist from prior indexing)
   b. Create structural triples:
      - (:Node {uri: document/...}) with core/type, core/label, core/title triples
      - (:Node {uri: folder/...}) with core/type, core/label triples
      - Rel between document and folder
   c. Launch 4 extractors in parallel (Celery chord):
      - definitions → label + definition triples
      - objects → label + type triples
      - relationships → semantic SPO triples
      - topics → has-topic triples
   d. Generate PROV-O provenance triples
   e. Detect contradictions with existing triples

6. Vectorize entities in Weaviate (Phase 2+)

7. Re-vectorize ontology (Phase 3)
```

**Estimated time** (based on current 9B throughput):
- ~300ms per chunk per extractor × 4 in parallel = ~300ms/chunk total
- Typical document: ~10 chunks = ~3 seconds
- 100 documents = ~5 minutes
- 1000 documents = ~50 minutes
- BOE (47 laws, ~500 chunks) = ~2.5 minutes

**Execution methods**:
- CLI: `./onboarding.sh reindex-graph`
- API: `POST /extract/reindex?tenant_id=X`
- Script: `docker compose exec knowledge-tree-service python scripts/reindex_trustgraph.py`

## 8. Reference — TrustGraph Project

This design is based on [TrustGraph](https://github.com/trustgraph-ai/trustgraph) (Apache 2.0 license):
- Schema model: `:Node`/`:Literal`/`:Rel` with URI-based predicates
- 4 parallel LLM extractors (definitions, relationships, objects, topics)
- Ontology RAG for precision extraction
- W3C PROV-O provenance model
- FalkorDB as supported graph backend

**What we adapted to our stack**:
- Apache Pulsar → Redis Streams + Celery
- ConfigService prompts → Langfuse
- Qdrant embeddings → Weaviate (BGE-M3)
- Multi-provider LLM → SGLang (Qwen3.5-9B)
- Named graphs for provenance → properties in same graph

**What TrustGraph does NOT have** (that we may add later):
- Trust scoring engine (the name is aspirational — no pre-computed scores exist)
- Query-time confidence propagation
- Source authority weighting
