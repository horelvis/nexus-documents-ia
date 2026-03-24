# Batch Graph Traversal — Design Spec

**Date**: 2026-03-24
**Status**: Draft
**Scope**: knowledge-tree-service only (no EAS changes)
**Inspired by**: TrustGraph GraphRAG performance optimization (98% query reduction via batching)

## Problem

The current graph expansion pipeline executes ~11 sequential Cypher queries per search request against FalkorDB. Each query is a separate round-trip, adding network latency and connection pool pressure. The breakdown:

| Phase | Current queries | Pattern |
|-------|----------------|---------|
| documents-by-entity | 3 per entity | Sequential fallback chain |
| Seed resolution | 1 per entity (max 5) | Per-entity loop |
| N-hop traversal | 1 per seed (max 5) | Per-seed loop |
| Claims + contradictions | 1 per entity (max 10) + 1 | Per-entity loop + separate contradiction query |
| **Total** | **~11** | — |

Graph expansion latency: ~70-120ms per search request.

## Goal

Reduce Cypher queries from ~11 to ~4 per search request by batching related queries. Target latency: ~30-50ms (50-70% reduction).

## Success Criteria

- Cypher queries per search: 11 → ≤ 4
- Latency of graph expansion: 50-70% reduction
- Zero regressions in 26 sanity checks
- All 63 existing KTS unit tests pass
- HTTP API contract unchanged (graph_expander.py untouched)

## Design

### Change 1: UNION Fallback in `/tree/graph/documents-by-entity`

**File**: `app/api/tree.py` (lines ~516-587)

**Current**: 3 sequential queries with fallback logic (entity match → person property → folder name). Each level runs only if the previous returned 0 results.

**New**: 1 UNION query covering all 3 match types simultaneously:

```cypher
MATCH (d:Document)-[]-(e:Entity)
WHERE toLower(e.name) CONTAINS $name_lower AND d.tenant_id = $tid
RETURN DISTINCT d.document_id AS doc_id, 'entity' AS match_source
UNION
MATCH (d:Document)
WHERE d.associated_person IS NOT NULL
  AND toLower(d.associated_person) CONTAINS $name_lower
  AND d.tenant_id = $tid
RETURN DISTINCT d.document_id AS doc_id, 'person_property' AS match_source
UNION
MATCH (d:Document)-[:CONTAINED_IN]->(f:Folder)
WHERE toLower(f.name) CONTAINS $name_lower AND d.tenant_id = $tid
RETURN DISTINCT d.document_id AS doc_id, 'folder' AS match_source
LIMIT 50
```

**Behavior change**: Previously returned results from the first matching level only. Now returns all matches from all 3 sources, deduplicated by `doc_id`. The `match_source` field indicates provenance. This is an improvement — previously folder matches were lost if entity already matched.

**Fallback**: If FalkorDB does not support UNION, use 3 sequential OPTIONAL MATCH clauses within a single query with WITH chaining.

**Queries**: 3 → 1

### Change 2: Batch Seed Resolution

**File**: `app/services/subgraph_extractor.py` (Phase 1, lines 127-181)

**Current**: 1 query per entity to resolve seed nodes (up to 5 entities = 5 queries).

**New**: 1 query with IN operator for all entities:

```cypher
MATCH (e:Entity)
WHERE (e.tenant_id = $tid OR e.shared = true)
  AND e.normalized_name IS NOT NULL
WITH e, [name IN $names WHERE toLower(e.name) CONTAINS name | name] AS matched
WHERE size(matched) > 0
RETURN e.name AS name, labels(e) AS types, e.entity_type AS entity_type,
       matched[0] AS matched_query, elementId(e) AS eid
LIMIT $max_seeds
```

**Input**: `$names` = list of normalized entity names (max 10).

**FalkorDB compat**: If list comprehension inside WITH is not supported, use `UNWIND $names AS name` followed by `MATCH ... WHERE toLower(e.name) CONTAINS name` and `COLLECT`.

**Queries**: 5 → 1

### Change 3: Batch N-hop Traversal

**File**: `app/services/subgraph_extractor.py` (Phase 2, lines 183-306)

**Current**: 1 query per seed with variable-length path workaround (FalkorDB cannot bind `[r*1..2]` for UNWIND). Up to 5 seeds = 5 queries.

**New**: 1 query with explicit 2-hop pattern for all seeds:

```cypher
MATCH (seed:Entity)
WHERE elementId(seed) IN $seed_ids
MATCH (seed)-[r]-(hop1)
WHERE hop1.tenant_id = $tid OR hop1.shared = true
OPTIONAL MATCH (hop1)-[r2]-(hop2)
WHERE hop2.tenant_id = $tid OR hop2.shared = true
WITH seed, r, hop1, r2, hop2
RETURN
  seed.name AS seed_name,
  type(r) AS rel1_type, hop1.name AS hop1_name, labels(hop1) AS hop1_labels,
  type(r2) AS rel2_type, hop2.name AS hop2_name, labels(hop2) AS hop2_labels
LIMIT $max_nodes
```

**Why explicit hops**: Avoids the FalkorDB limitation with variable-length relationship binding. Explicit `MATCH hop1 + OPTIONAL MATCH hop2` is more predictable and produces identical results to `*1..2`.

**Behavior change**: All seeds processed in a single pass. Shared nodes between seeds are naturally deduplicated.

**Queries**: 5 → 1

### Change 4: Batch Claims + Contradictions

**File**: `app/services/subgraph_extractor.py` (Phase 3, lines 295-417)

**Current**: 1 query per entity for claims (max 10 entities) + 1 separate query for contradictions = 11 queries.

**New**: 1 query for all claims + contradictions:

```cypher
MATCH (e:Entity)
WHERE elementId(e) IN $entity_ids
MATCH (c:Claim)-[:ABOUT]->(e)
WHERE c.tenant_id = $tid
OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(d:Document)
OPTIONAL MATCH (c)-[:CONTRADICTS]-(contra:Claim)
RETURN
  e.name AS entity_name,
  c.claim_id AS claim_id, c.statement AS statement,
  c.claim_type AS claim_type, c.confidence AS confidence,
  c.source_chunk AS source_chunk,
  d.document_id AS doc_id, d.title AS doc_title,
  contra.claim_id AS contradicts_id, contra.statement AS contradicts_statement
ORDER BY c.confidence DESC
LIMIT $max_claims
```

**Behavior change**: Claims deduplicated naturally (a claim referenced by multiple entities appears once). Contradictions included in same result set.

**Queries**: 11 → 1

## Summary

| Phase | Before | After | Reduction |
|-------|--------|-------|-----------|
| documents-by-entity | 3 | 1 (UNION) | -2 |
| Seed resolution | 5 | 1 (IN batch) | -4 |
| N-hop traversal | 5 | 1 (explicit hops) | -4 |
| Claims + contradictions | 11 | 1 (batch + OPTIONAL) | -10 |
| **Total** | **~11** | **~4** | **~63%** |

## Files Modified

| File | Change |
|------|--------|
| `knowledge-tree-service/app/api/tree.py` | UNION fallback for documents-by-entity |
| `knowledge-tree-service/app/services/subgraph_extractor.py` | Batch phases 1-3 |

## Files NOT Modified

| File | Reason |
|------|--------|
| `emma-agent-service/*` | HTTP API contract unchanged |
| `graph_expander.py` | Calls same endpoints, unaware of internal batching |
| `claim_extractor.py` | Write path unchanged, only read path optimized |

## Testing

- **Unit tests**: All 63 existing KTS tests must pass
- **New tests**: Batch seed resolution, UNION fallback, batch claims
- **Sanity checks**: 26 checks as E2E validation
- **Performance**: Measure latency before/after with FalkorDB graph containing real data

## Risks

1. **FalkorDB UNION support** — not verified. Fallback: OPTIONAL MATCH chain.
2. **FalkorDB list comprehension in WITH** — not verified. Fallback: UNWIND + COLLECT.
3. **Query result size** — batched queries return more rows. LIMIT clauses prevent explosion.
4. **Deduplication change** — UNION returns all sources vs fallback-first-match. This is an improvement but changes behavior.

## Out of Scope

- Chunk nodes (separate sub-project: Provenance DAG)
- Reasoning persistence (separate sub-project)
- Explainability UI (separate sub-project)
- Label caching (TrustGraph pattern, future optimization)
