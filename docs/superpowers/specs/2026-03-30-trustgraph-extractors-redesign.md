# TrustGraph Extractors Redesign — Phase 3-PREREQ

**Date**: 2026-03-30
**Status**: Draft
**Depends on**: TrustGraph Phase 1 (complete), Phase 2 (complete)
**Blocks**: Phase 3a (GraphIntelligenceLayer), Phase 3b (Discovery), Phase 3c (Multi-hop Reasoning)

## Problem Statement

The current TrustGraph extractors produce **~700 knowledge triples from 28 documents** (25 per doc), while generating **22,656 contradiction triples** (74% of the graph). The extractors were written from scratch instead of adopting the proven patterns from TrustGraph upstream (`horelvis/trustgraph`).

### Current Extraction Results (28 documents, 601 chunks)

| Extractor | Triples | Per Doc | Expected | Problem |
|---|---|---|---|---|
| Topics | 445 | 15.9 | ~20 | Acceptable (best performer) |
| Relationships | 226 | 8.1 | ~30-50 | Ontology-locked predicates silently dropped |
| Objects | 28 | 1.0 | ~15-20 | Chunks too small for NER |
| Definitions | 5 | 0.18 | ~10-15 | Silent JSON parse failures |
| **Contradictions** | **14,752** (3,688 × 4) | — | — | Stored as triples, not metadata |
| **Provenance** | **~4,800** | — | — | 6 literals per chunk |
| **Total useful** | **~700** (2%) | **25** | **~75-100** | — |

### Root Causes (validated by comparison with upstream)

1. **Ontology-locked predicates**: Local forces exact match against 32 fixed predicates. Upstream accepts free-form predicates → URI. LLM generates "trabaja-para" but ontology expects "empleado-de" → silently dropped.

2. **JSON array format (no truncation resilience)**: Local uses JSON arrays. If LLM truncates output mid-array → total parse failure → `[]`. Upstream uses JSONL (one object per line) → partial results preserved.

3. **Silent parse failures**: Local `_safe_parse_json()` returns `[]` on any error. No logging at ERROR level, no metrics. 0% visibility into failure rate.

4. **No JSON schema validation**: Local accepts any parsed JSON. Upstream validates against `jsonschema.validate()` per extractor.

5. **Contradictions stored as triples**: 4 relationships per contradiction (subject, predicate, value-a, value-b) → 74% of graph is contradiction metadata.

6. **Hardcoded prompts**: Can't iterate without code deploy. Upstream externalizes prompts via Config API.

7. **Sequential chunk processing**: Local processes chunks sequentially (extractors parallel per chunk). Upstream processes chunks in parallel across instances.

8. **No batch storage**: Local makes 1 FalkorDB MERGE per triple. Upstream batches 50 triples.

## Design

### Approach: Rewrite extractors adopting TrustGraph upstream patterns

Modify the existing extractor files in-place. No new services, no new dependencies. The coordinator pattern stays — we fix what's inside.

### 1. Free-Form Predicates with Ontology Guidance (not enforcement)

**Current** (relationships.py):
```python
# Strict: predicate MUST match ontology exactly → silent drop if not
if predicate not in extractable_predicates:
    continue  # SILENTLY DROPPED
```

**New**:
```python
# Guided: suggest ontology predicates, but accept free-form
# 1. Try exact match against ontology
matched = ontology_registry.match(predicate)
if matched:
    predicate_uri = matched.uri
else:
    # 2. Try fuzzy match (normalize + Levenshtein)
    fuzzy = ontology_registry.fuzzy_match(predicate, threshold=0.8)
    if fuzzy:
        predicate_uri = fuzzy.uri
        extraction_method = "llm_relationships_fuzzy"
    else:
        # 3. Accept as free-form → generate URI
        predicate_uri = URIBuilder.predicate("extracted", normalize_name(predicate))
        extraction_method = "llm_relationships_freeform"
```

**Prompt change**: Ontology predicates listed as "preferred" with examples, not as rigid constraints:
```
Use these predicates when they fit:
- legal/empleado-de: "X works for Y" (e.g., "Juan trabaja para Empresa SA")
- legal/references-law: "X references law Y"
...
If none fit, use a descriptive predicate in Spanish (e.g., "regula", "modifica").
```

**Impact**: Estimated 3-5x more relationship triples (from 226 to ~700-1100).

### 2. JSONL Response Format (Truncation Resilience)

**Current** (base.py):
```python
# All-or-nothing: truncated array = total failure
result = json.loads(text)  # Fails if "[{...}, {..." (truncated)
```

**New**:
```python
def _parse_jsonl(self, text: str) -> List[dict]:
    """Parse JSONL (one JSON object per line). Truncation-resilient."""
    results = []
    for line in text.strip().splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("[]", "[", "]"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                results.append(obj)
        except json.JSONDecodeError:
            logger.warning("JSONL parse skip: %s", line[:100])
    return results
```

**Prompt change**: All extractor prompts add:
```
Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Example:
{"subject": "Juan García", "predicate": "empleado-de", "object": "Empresa SA", "object-entity": true}
{"subject": "Contrato 123", "predicate": "references-law", "object": "Estatuto de los Trabajadores", "object-entity": true}
```

**Fallback**: If JSONL parse returns 0 results, fall back to JSON array parse (backwards compat with cached LLM responses).

**Impact**: Estimated 20-40% more triples recovered from truncated responses.

### 3. Parse Failure Visibility

**Current**:
```python
except Exception:
    return []  # Silent death
```

**New**:
```python
except Exception as exc:
    logger.error(
        "Extractor %s parse failure on chunk %s: %s | Raw response: %s",
        self.EXTRACTOR_NAME, chunk_id, exc, raw_response[:500]
    )
    self._parse_failures += 1
    return []
```

Plus, `ExtractionCoordinator.extract_document()` logs summary:
```python
logger.info(
    "Document %s extraction complete: %d triples, %d parse_failures, %d empty_responses",
    document_id, total_triples, total_parse_failures, total_empty
)
```

**Impact**: Full visibility into extraction health. Enables data-driven prompt iteration.

### 4. JSON Schema Validation

Each extractor defines its expected schema:

```python
# relationships.py
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "minLength": 1},
        "predicate": {"type": "string", "minLength": 1},
        "object": {"type": "string", "minLength": 1},
        "object-entity": {"type": "boolean"},
    },
    "required": ["subject", "predicate", "object"],
}
```

Validation in `BaseExtractor._parse_and_validate()`:
```python
validated = []
for item in parsed:
    try:
        jsonschema.validate(item, self.RESPONSE_SCHEMA)
        validated.append(item)
    except jsonschema.ValidationError as e:
        logger.warning("Schema validation failed: %s | item: %s", e.message, item)
        self._validation_failures += 1
return validated
```

**Impact**: Catches malformed extractions before they become garbage triples.

### 5. Contradictions as Metadata (not triples)

**Current**: 4 `:Rel` edges per contradiction → 14,752 triples (74% of graph).

**New**: Store contradictions as properties on the `:Rel` edge itself:

```python
# When contradiction detected between rel_a and rel_b:
# Instead of creating 4 new triples, mark the edges:
await client.execute_cypher(
    "MATCH ()-[r:Rel]->() WHERE id(r) = $rel_id "
    "SET r.has_contradiction = true, r.contradiction_with = $other_rel_id",
    {"rel_id": rel_a_id, "other_rel_id": rel_b_id}
)
```

**Decision**: Use edge properties (not a separate PostgreSQL table) — keeps all graph data in FalkorDB, queryable via Cypher, no cross-store joins.

**Impact**: Graph shrinks from 30K to ~8K triples. Knowledge-to-noise ratio goes from 2% to ~25%.

### 6. Prompts in Langfuse

Move all 4 extractor prompts to Langfuse (infrastructure already exists):

| Prompt Name | Current Location | Langfuse Key |
|---|---|---|
| Definitions | Hardcoded in `definitions.py` | `trustgraph_extract_definitions` |
| Relationships | Hardcoded in `relationships.py` | `trustgraph_extract_relationships` |
| Topics | Hardcoded in `topics.py` | `trustgraph_extract_topics` |
| Objects | Hardcoded in `objects.py` | `trustgraph_extract_objects` |

Seed script: Add entries to `prompt_registry.py` and `seed_langfuse_prompts.py`.

**Impact**: Prompt iteration without deploy. A/B testing via Langfuse labels.

### 7. Batch Triple Storage

**Current**: 1 `MERGE` per triple.

**New**: Batch via `UNWIND` in `TripleStore`:

```python
async def batch_store_triples(self, triples: List[dict], user: str, collection: str):
    """Store multiple triples in a single Cypher UNWIND query."""
    if not triples:
        return

    # Separate node→node and node→literal triples
    node_triples = [t for t in triples if t.get("object_is_entity")]
    literal_triples = [t for t in triples if not t.get("object_is_entity")]

    if node_triples:
        await self._client.execute_cypher(
            "UNWIND $triples AS t "
            "MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col}) "
            "MERGE (o:Node {uri: t.o_uri, user: $user, collection: $col}) "
            "MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o) "
            "SET r.extraction_method = t.method, r.source_chunk = t.chunk",
            {"triples": node_triples, "user": user, "col": collection}
        )

    if literal_triples:
        await self._client.execute_cypher(
            "UNWIND $triples AS t "
            "MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col}) "
            "MERGE (o:Literal {value: t.o_val, user: $user, collection: $col}) "
            "MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o) "
            "SET r.extraction_method = t.method, r.source_chunk = t.chunk",
            {"triples": literal_triples, "user": user, "col": collection}
        )
```

**Impact**: ~10x faster reindex (28 docs in ~6 min instead of ~57 min).

### 8. Parallel Chunk Processing

**Current**: Sequential `for chunk_offset, chunk_text in enumerate(chunks)`.

**New**: Semaphore-bounded parallel processing:

```python
async def extract_document(self, ...):
    sem = asyncio.Semaphore(settings.extraction_parallel_chunks)  # default: 3

    async def process_chunk(offset, text):
        async with sem:
            return await self.extract_chunk(text, offset, ...)

    tasks = [process_chunk(i, text) for i, text in enumerate(chunks)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Impact**: ~3x faster extraction per document (bounded by vLLM throughput).

## Files Changed

| File | Change | Lines |
|---|---|---|
| `extractors/base.py` | JSONL parser, schema validation, error metrics | ~80 |
| `extractors/relationships.py` | Free-form predicates, JSONL prompt, Langfuse | ~60 |
| `extractors/definitions.py` | JSONL prompt, Langfuse, schema | ~30 |
| `extractors/topics.py` | JSONL prompt, Langfuse, schema | ~20 |
| `extractors/objects.py` | JSONL prompt, Langfuse, schema | ~30 |
| `extractors/coordinator.py` | Parallel chunks, batch storage, extraction metrics | ~50 |
| `contradiction.py` | Metadata storage (not triples) | ~40 |
| `triple_store.py` | `batch_store_triples()` with UNWIND | ~50 |
| `ontology_registry.py` | Fuzzy match, fail-loud loading | ~30 |
| `scripts/seed_langfuse_prompts.py` | 4 new prompt entries | ~20 |
| `app/services/prompt_registry.py` | 4 new prompt names | ~10 |
| `scripts/reindex_trustgraph.py` | Use new parallel extraction | ~10 |

**Total**: ~430 lines changed/added across 12 files.

## Validation Plan

### After implementation:

1. **Clear FalkorDB graph** and reindex all 28 documents
2. **Measure extraction yield**:
   - Target: >75 triples per document (3x current)
   - Target: <5% parse failure rate
   - Target: 0 contradiction triples in graph (stored as metadata)
3. **Measure graph composition**:
   - Target: >80% knowledge triples (vs current 2%)
   - Target: <20% provenance/system triples
4. **Validate predicate distribution**:
   - Target: >10 unique predicates used (vs current 5)
   - Target: ontology-matched > 60%, fuzzy-matched ~20%, free-form < 20%
5. **Pipeline integration test**:
   - Query: "¿qué relaciones existen entre los documentos de facturación?"
   - Expect: graph_rag returns scored edges with sources
   - Expect: smart_search graph_score uses real confidence values

### Sanity checks to add:

- `extractor_yield_per_document` — triples produced vs expected minimum
- `extractor_parse_failure_rate` — track per extractor
- `graph_knowledge_ratio` — knowledge triples / total triples

## Relationship to Phase 3 Pipeline Design

This spec is a **prerequisite** for the graph-centric pipeline redesign:

```
Phase 3-PREREQ (this spec) → Quality data in FalkorDB
  ↓
Phase 3a: GraphIntelligenceLayer + confidence scoring
  - Confidence scoring uses extraction_method (now populated correctly)
  - Source pinpointing uses source_chunk (now with JSONL resilience)
  ↓
Phase 3b: Bidirectional discovery + validation
  - Inbound queries work because predicates are diverse (not ontology-locked)
  - Cross-validation possible because contradictions are queryable metadata
  ↓
Phase 3c: Multi-hop reasoning + document generation
  - Path finding works because relationship triples are 3-5x more numerous
  - Structured synthesis uses predicate semantics (ontology domain grouping)
```

## Out of Scope

- Upstream's RDF-star provenance model (requires FalkorDB feature not available)
- Upstream's ontology extractor with embedding-based schema selection (Phase 3c candidate)
- Upstream's Pulsar message bus (we keep HTTP + asyncio)
- Entity embedding regeneration (handled by existing `_populate_entity_embeddings`)
