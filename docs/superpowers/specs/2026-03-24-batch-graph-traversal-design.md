# Batch Graph Traversal — Design Spec

**Date**: 2026-03-24
**Status**: Draft
**Scope**: knowledge-tree-service only (no EAS changes)
**Inspired by**: TrustGraph GraphRAG performance optimization (98% query reduction via batching)

## Problem

The current graph expansion pipeline executes ~24 sequential Cypher queries (worst case) per search request against FalkorDB. Each query is a separate round-trip, adding network latency and connection pool pressure. The breakdown:

| Phase | Current queries | Pattern |
|-------|----------------|---------|
| documents-by-entity | 3 per entity | Sequential fallback chain |
| Seed resolution | 1 per entity (max 5) | Per-entity loop |
| N-hop traversal | 1 per seed (max 5) | Per-seed loop |
| Claims fetch | 1 per entity (max 10) | Per-entity loop |
| Contradiction detection | 1 per entity (max 10) | Per-entity full-tenant scan (most expensive) |
| **Total** | **~24 worst case** | — |

Note: The contradiction query at `subgraph_extractor.py:393` is a full tenant scan of all CONTRADICTS edges, repeated per entity inside the claims loop. This is the single most expensive pattern — the batched version eliminates it entirely by anchoring contradictions to specific claims.

Graph expansion latency: ~70-120ms per search request.

## Goal

Reduce Cypher queries from ~24 (worst case) to ~4 per search request by batching related queries. Target latency: ~30-50ms (50-70% reduction).

## Success Criteria

- Cypher queries per search: ~24 → ≤ 4
- Latency of graph expansion: 50-70% reduction
- Zero regressions in 26 sanity checks
- All 63 existing KTS unit tests pass
- HTTP API contract unchanged (graph_expander.py untouched)

## Design

### Change 1: UNION Fallback in `/tree/graph/documents-by-entity`

**File**: `app/api/tree.py` (lines ~516-587)

**Current**: 3 sequential queries with fallback logic (entity match → person property → folder name). Each level runs only if the previous returned 0 results.

**New**: 1 query using OPTIONAL MATCH chaining (avoids UNION LIMIT issues and unverified UNION support):

```cypher
MATCH (d:Document {tenant_id: $tid})
OPTIONAL MATCH (d)-[]-(e:Entity)
WHERE toLower(e.name) CONTAINS $name_lower
WITH d, CASE WHEN e IS NOT NULL THEN 'entity' ELSE NULL END AS src1
OPTIONAL MATCH (d)
WHERE d.associated_person IS NOT NULL
  AND toLower(d.associated_person) CONTAINS $name_lower
WITH d, src1, CASE WHEN d.associated_person IS NOT NULL AND toLower(d.associated_person) CONTAINS $name_lower THEN 'person_property' ELSE NULL END AS src2
OPTIONAL MATCH (d)-[:CONTAINED_IN]->(f:Folder)
WHERE toLower(f.name) CONTAINS $name_lower
WITH d, src1, src2, CASE WHEN f IS NOT NULL THEN 'folder' ELSE NULL END AS src3
WHERE src1 IS NOT NULL OR src2 IS NOT NULL OR src3 IS NOT NULL
RETURN DISTINCT d.document_id AS doc_id,
  COALESCE(src1, src2, src3) AS match_source
LIMIT 50
```

**Alternative (if FalkorDB supports UNION)**: Use UNION with per-branch LIMIT 50 (openCypher LIMIT after UNION applies only to the last branch).

**Behavior change**: Previously returned results from the first matching level only. Now returns all matches from all 3 sources, deduplicated by `doc_id`. The `match_source` field indicates provenance. This is an improvement — previously folder matches were lost if entity already matched.

**Queries**: 3 → 1

### Change 2: Batch Seed Resolution

**File**: `app/services/subgraph_extractor.py` (Phase 1, lines 127-181)

**Current**: 1 query per entity to resolve seed nodes (up to 5 entities = 5 queries).

**New**: 1 query using UNWIND for all entities (FalkorDB-compatible, avoids list comprehension):

```cypher
UNWIND $names AS search_name
MATCH (n)
WHERE (n.tenant_id = $tid OR n.shared = true)
  AND (toLower(n.name) CONTAINS search_name
       OR toLower(n.title) CONTAINS search_name
       OR toLower(n.associated_person) CONTAINS search_name)
RETURN n.name AS name, labels(n) AS types,
       n.entity_type AS entity_type,
       search_name AS matched_query, id(n) AS nid
LIMIT $max_seeds
```

**Input**: `$names` = list of normalized entity names (max 10).

**Key design decisions**:
- Uses `UNWIND` (FalkorDB-safe) instead of list comprehension in WITH.
- Matches **any node label** (not just Entity) to preserve current behavior — `_resolve_seeds` matches Document by title and associated_person too.
- Searches across 3 properties: `name`, `title`, `associated_person` (matching current multi-property pattern).

**Data flow**: Phase 1 output includes `id(n)` values (integer node IDs). Phase 2 consumes these as `$seed_ids`.

**Queries**: 5 → 1

### Change 3: Batch N-hop Traversal

**File**: `app/services/subgraph_extractor.py` (Phase 2, lines 183-306)

**Current**: 1 query per seed with variable-length path workaround (FalkorDB cannot bind `[r*1..2]` for UNWIND). Up to 5 seeds = 5 queries.

**New**: 1 query with explicit 2-hop pattern for all seeds:

```cypher
MATCH (seed:Entity)
WHERE id(seed) IN $seed_ids
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

**Current**: 1 query per entity for claims (max 10) + 1 contradiction full-tenant scan per entity (max 10) = up to 20 queries. The contradiction query is the most expensive — it scans ALL CONTRADICTS edges for the tenant, repeated inside the per-entity loop.

**New**: 1 query for all claims + contradictions:

```cypher
MATCH (e:Entity)
WHERE id(e) IN $entity_ids
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
| documents-by-entity | 3 | 1 (OPTIONAL MATCH chain) | -2 |
| Seed resolution | 5 | 1 (UNWIND batch) | -4 |
| N-hop traversal | 5 | 1 (explicit hops) | -4 |
| Claims fetch | 10 | 1 (batch + OPTIONAL) | -9 |
| Contradiction detection | 10 (full tenant scan each) | 0 (merged into claims query) | -10 |
| **Total** | **~24 worst case** | **~4** | **~83%** |

Note: The contradiction detection improvement is particularly significant — the current per-entity full-tenant scan is replaced by an anchored OPTIONAL MATCH on specific claims, fundamentally improving the query plan.

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
- **Query counter**: Add a context-scoped counter to `falkordb_client.execute_cypher()` to verify query counts in tests (assert ≤ 4 per subgraph extraction)

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
