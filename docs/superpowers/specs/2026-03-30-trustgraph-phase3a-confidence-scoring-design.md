# TrustGraph Phase 3a — Confidence Scoring + Source Pinpointing

**Date**: 2026-03-30
**Status**: Draft
**Depends on**: Phase 3-PREREQ (extractors redesign — complete)
**Branch**: `feat/trustgraph-phase2`

## Problem Statement

The TrustGraph now produces 21,586 triples from 28 documents (771/doc avg) with 3 tiers of extraction methods (exact, fuzzy, freeform) and contradiction metadata on edges. However:

1. **No quality signal per edge** — graph_rag and SmartSearch treat all edges equally, regardless of extraction method or contradictions
2. **No source traceability in LLM context** — the LLM synthesizer cannot cite which document/chunk a fact came from
3. **graph_rag's LLM edge scorer** (Stage 5) doesn't see extraction quality metadata, only the relationship text

## Design

### 1. Pre-computed Confidence Score (stored on `:Rel` edges)

During extraction, each triple gets a `confidence` float (0.10–1.00) stored as a property on the `:Rel` edge in FalkorDB. Calculated from `extraction_method` at write time, then adjusted post-contradiction detection.

**Base score by extraction method:**

| `extraction_method` | Base Score | Rationale |
|---------------------|-----------|-----------|
| `system` | 1.00 | Document metadata, folder structure — deterministic |
| `llm_definitions` | 0.90 | Explicit definitions in text — high signal |
| `llm_topics` | 0.85 | Topic extraction — reliable but coarse |
| `llm_objects` | 0.85 | NER — reliable for named entities |
| `llm_relationships` | 0.90 | Exact ontology predicate match |
| `llm_relationships_fuzzy` | 0.75 | Fuzzy-matched predicate — probable but uncertain |
| `llm_relationships_freeform` | 0.60 | Free-form predicate — LLM-invented, unvalidated |

**Contradiction penalty:** After contradiction detection marks edges with `has_contradiction = true`, a batch Cypher UPDATE applies `confidence = max(confidence - 0.25, 0.10)` to those edges.

**Storage:** `batch_store_triples()` is modified to include `confidence` in the UNWIND SET clause:
```
ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence
```

### 2. graph_rag Confidence Integration

The graph_rag tool's 6-stage pipeline is modified at two points:

**Stage 4 (Semantic pre-filter):** Edges with `confidence < GRAPH_RAG_CONFIDENCE_THRESHOLD` (default: 0.30) are excluded before the expensive embedding + LLM scoring stages. This saves LLM calls on low-quality edges.

**Stage 5 (LLM edge scoring):** The edge description passed to the LLM scorer is enriched:
```
Before: "Juan García" --[empleado-de]--> "Empresa ABC S.L."
After:  "Juan García" --[empleado-de]--> "Empresa ABC S.L." [conf: 0.90, source: "Contrato-2025.pdf" chunk 3]
```
The LLM scorer can factor in confidence when assigning relevance scores.

**Stage 6 (Context formatting):** The markdown context includes source citations:
```
- Juan García empleado-de Empresa ABC S.L. [conf: 0.90, fuente: Contrato-2025.pdf#3]
```
This lets the synthesizer LLM cite specific sources in its response.

### 3. SmartSearch Confidence Integration

SmartSearch's 5-signal re-ranker has a `graph` signal (weight 0.20 default). Currently this is binary (1.0 if entity found in graph, 0.0 if not).

**Change:** The `graph_score` for a document becomes the **average confidence** of edges where the document (or its entities) appear:

```python
# Before:
graph_score = 1.0 if entity_in_graph else 0.0

# After:
graph_score = avg(edge.confidence for edge in matching_edges) if matching_edges else 0.0
```

This means documents with high-confidence graph relationships rank higher than those with only freeform/contradicted relationships.

### 4. Source Pinpointing (Inline)

Each edge in FalkorDB already stores `source_chunk` (format: `nouxcube://document/{collection}/{doc_id}#offset={n}`). To make this human-readable:

1. **Label resolution** (graph_rag Stage 3, already exists): resolve document URIs to titles via `core/label` lookup
2. **Format inline**: `[fuente: {doc_title}#{chunk_offset}]` appended to each relationship line

No new endpoint needed — the data is already in FalkorDB, just needs formatting.

### 5. triple_query Changes

The `/triples/neighbors` endpoint (used by graph_rag Stage 2) needs to return `confidence` and `source_chunk` alongside existing edge data. Currently returns `uri`, `extraction_method`, `source_chunk`. Add `confidence` to the Cypher RETURN clause.

## Files Changed

| File | Service | Change | Lines |
|------|---------|--------|-------|
| `extractors/coordinator.py` | KTS | Calculate confidence per triple in batch builder | ~15 |
| `triple_store.py` | KTS | Add `confidence` to `batch_store_triples` UNWIND | ~5 |
| `contradiction.py` | KTS | Batch penalty UPDATE for contradicted edges | ~15 |
| `triple_query.py` | KTS | Return `confidence` in neighbors query | ~5 |
| `config.py` | KTS | Add `GRAPH_RAG_CONFIDENCE_THRESHOLD` | ~2 |
| `graph_rag.py` | Emma | Pre-filter by confidence, enrich edge descriptions, inline sources | ~40 |
| `smart_search.py` | Emma | Use avg confidence for graph_score | ~15 |
| `config.py` | Emma | Add `GRAPH_RAG_CONFIDENCE_THRESHOLD` setting | ~2 |

**Total:** ~100 lines across 8 files.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPH_RAG_CONFIDENCE_THRESHOLD` | `0.30` | Minimum confidence for edges in graph_rag pre-filter |

## Validation Plan

### After implementation:

1. **Verify confidence distribution** in FalkorDB:
   ```cypher
   MATCH ()-[r:Rel]->() WHERE r.confidence IS NOT NULL
   RETURN r.extraction_method, avg(r.confidence), count(r)
   ```
   Expected: system=1.0, llm_relationships=0.90, fuzzy=0.75, freeform=0.60

2. **Verify contradiction penalty**:
   ```cypher
   MATCH ()-[r:Rel]->() WHERE r.has_contradiction = true
   RETURN avg(r.confidence)
   ```
   Expected: avg < 0.65 (base - 0.25)

3. **graph_rag integration test**: Query "relaciones entre empleados y empresas"
   - Expect: high-confidence edges ranked first
   - Expect: source citations in context text
   - Expect: low-confidence edges (<0.30) excluded

4. **SmartSearch integration test**: Query "contrato de Juan García"
   - Expect: documents with high-confidence graph links rank higher

## Out of Scope

- Frontend display of confidence scores (Phase 3b/3c candidate)
- LLM-based confidence recalculation (too expensive at extraction time)
- Cross-document confidence aggregation (entity-level confidence — Phase 3b)
- Confidence decay over time (not needed for static documents)
