# Batch Graph Traversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce FalkorDB Cypher queries from ~24 to ~4 per search request by batching operations in knowledge-tree-service.

**Architecture:** Four independent changes inside knowledge-tree-service — OPTIONAL MATCH chain for document-entity lookup, UNWIND batch for seed resolution, explicit 2-hop batch traversal, and batch claims+contradictions fetch. HTTP API contract unchanged.

**Tech Stack:** FalkorDB (openCypher), Python 3.12, FastAPI, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-24-batch-graph-traversal-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `knowledge-tree-service/app/api/tree.py:517-592` | Modify | OPTIONAL MATCH chain for `/tree/graph/documents-by-entity` |
| `knowledge-tree-service/app/services/subgraph_extractor.py:127-181` | Modify | Batch `_resolve_seeds()` with UNWIND |
| `knowledge-tree-service/app/services/subgraph_extractor.py:183-306` | Modify | Batch `_traverse()` with explicit 2-hop |
| `knowledge-tree-service/app/services/subgraph_extractor.py:309-417` | Modify | Batch `_fetch_entity_claims()` + contradictions |
| `knowledge-tree-service/app/services/falkordb_client.py` | Modify | Add query counter context manager |
| `knowledge-tree-service/tests/test_batch_traversal.py` | Create | Tests for all 4 batched queries |

---

### Task 1: Add Query Counter to FalkorDB Client

**Files:**
- Modify: `knowledge-tree-service/app/services/falkordb_client.py`
- Create: `knowledge-tree-service/tests/test_batch_traversal.py`

This enables verifying query counts in tests — success criteria is ≤4 queries per subgraph extraction.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_batch_traversal.py
"""Tests for batch graph traversal optimizations."""

import pytest
import pytest_asyncio
from app.services.falkordb_client import falkordb_client, QueryCounter


@pytest.mark.asyncio
class TestQueryCounter:
    """Verify query counting infrastructure."""

    async def test_counter_tracks_queries(self, falkordb_client):
        """Counter increments on each execute_cypher call."""
        async with QueryCounter() as counter:
            await falkordb_client.execute_cypher("RETURN 1 AS n")
            await falkordb_client.execute_cypher("RETURN 2 AS n")
            assert counter.count == 2

    async def test_counter_zero_without_queries(self, falkordb_client):
        """Counter starts at zero."""
        async with QueryCounter() as counter:
            assert counter.count == 0

    async def test_counter_isolated_between_contexts(self, falkordb_client):
        """Nested counters don't interfere."""
        async with QueryCounter() as outer:
            await falkordb_client.execute_cypher("RETURN 1 AS n")
            async with QueryCounter() as inner:
                await falkordb_client.execute_cypher("RETURN 2 AS n")
                assert inner.count == 1
            assert outer.count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && docker compose run --rm ... pytest tests/test_batch_traversal.py -v`
Expected: FAIL with `ImportError: cannot import name 'QueryCounter'`

- [ ] **Step 3: Implement QueryCounter**

Add to `falkordb_client.py`:

```python
import contextvars
from contextlib import asynccontextmanager

_query_counter: contextvars.ContextVar[list] = contextvars.ContextVar("query_counter", default=None)


class QueryCounter:
    """Context manager that counts FalkorDB queries within a scope."""

    def __init__(self):
        self.count = 0
        self._token = None

    async def __aenter__(self):
        self._token = _query_counter.set(self)
        return self

    async def __aexit__(self, *exc):
        _query_counter.reset(self._token)


def _increment_query_counter():
    """Called internally by execute_cypher to track query count."""
    counter = _query_counter.get(None)
    if counter is not None:
        counter.count += 1
```

In `FalkorDBClient.execute_cypher()`, add `_increment_query_counter()` as the first line of the method body.

- [ ] **Step 4: Run test to verify it passes**

Run: same as step 2
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/falkordb_client.py tests/test_batch_traversal.py
git commit -m "feat(kts): add QueryCounter for batch traversal verification"
```

---

### Task 2: Batch documents-by-entity (OPTIONAL MATCH chain)

**Files:**
- Modify: `knowledge-tree-service/app/api/tree.py:517-592`
- Modify: `knowledge-tree-service/tests/test_batch_traversal.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_batch_traversal.py`:

```python
@pytest.mark.asyncio
class TestBatchDocumentsByEntity:
    """Verify OPTIONAL MATCH chain replaces 3-query fallback."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        """Seed documents, entities, and folders for testing."""
        await falkordb_client.execute_cypher("""
            CREATE (d1:Document {document_id: 'doc-batch-1', title: 'Contrato Juan', tenant_id: 't1', associated_person: 'juan garcia'})
            CREATE (d2:Document {document_id: 'doc-batch-2', title: 'Nomina Maria', tenant_id: 't1'})
            CREATE (d3:Document {document_id: 'doc-batch-3', title: 'Factura', tenant_id: 't1'})
            CREATE (e1:Entity {name: 'Juan Garcia', entity_type: 'person', tenant_id: 't1'})
            CREATE (f1:Folder {name: 'Maria Lopez', tenant_id: 't1'})
            CREATE (e1)-[:MENTIONED_IN]->(d1)
            CREATE (d2)-[:CONTAINED_IN]->(f1)
        """)

    async def test_finds_by_entity_name(self, falkordb_client):
        """Matches documents via entity relationship."""
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('juan garcia', 't1')
        assert 'doc-batch-1' in doc_ids

    async def test_finds_by_associated_person(self, falkordb_client):
        """Matches documents via associated_person property."""
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('juan garcia', 't1')
        assert 'doc-batch-1' in doc_ids  # matched via associated_person too

    async def test_finds_by_folder_name(self, falkordb_client):
        """Matches documents inside folders named like person."""
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('maria lopez', 't1')
        assert 'doc-batch-2' in doc_ids

    async def test_uses_single_query(self, falkordb_client):
        """CRITICAL: Must execute only 1 Cypher query, not 3."""
        from app.api.tree import _batch_documents_by_entity
        async with QueryCounter() as counter:
            await _batch_documents_by_entity('juan garcia', 't1')
            assert counter.count == 1, f"Expected 1 query, got {counter.count}"

    async def test_deduplicates_results(self, falkordb_client):
        """Same doc found via multiple sources appears once."""
        from app.api.tree import _batch_documents_by_entity
        doc_ids = await _batch_documents_by_entity('juan garcia', 't1')
        assert len(doc_ids) == len(set(doc_ids))
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL with `ImportError: cannot import name '_batch_documents_by_entity'`

- [ ] **Step 3: Implement `_batch_documents_by_entity`**

In `tree.py`, add a new function and update the `documents_by_entity` endpoint to call it:

```python
async def _batch_documents_by_entity(entity_name: str, tenant_id: str) -> List[str]:
    """Find document IDs by entity name using single OPTIONAL MATCH chain.

    Searches 3 sources in one query:
    1. Entity nodes linked via relationships
    2. Document associated_person property
    3. Folder names matching entity
    """
    sanitized = re.sub(r'[\\"\';]', '', entity_name).lower()

    rows = await falkordb_client.execute_cypher(
        """
        MATCH (d:Document {tenant_id: $tid})
        OPTIONAL MATCH (d)-[]-(e:Entity)
        WHERE toLower(e.name) CONTAINS $name
        WITH d, e
        WHERE e IS NOT NULL
           OR (d.associated_person IS NOT NULL AND toLower(d.associated_person) CONTAINS $name)
        RETURN DISTINCT d.document_id AS doc_id
        UNION
        MATCH (d:Document {tenant_id: $tid})-[:CONTAINED_IN]->(f:Folder)
        WHERE toLower(f.name) CONTAINS $name
        RETURN DISTINCT d.document_id AS doc_id
        """,
        {"name": sanitized, "tid": tenant_id},
    )

    # Deduplicate and collect
    seen = set()
    doc_ids = []
    for row in rows:
        did = row.get("doc_id")
        if did and did not in seen:
            seen.add(did)
            doc_ids.append(did)
    return doc_ids[:50]
```

If FalkorDB does not support UNION, fall back to 2 separate queries (entity+person in one, folder in another = 2 queries instead of 3):

```python
    # Fallback: 2 queries if UNION not supported
    rows1 = await falkordb_client.execute_cypher(
        """
        MATCH (d:Document {tenant_id: $tid})
        WHERE EXISTS {
            MATCH (d)-[]-(e:Entity) WHERE toLower(e.name) CONTAINS $name
        } OR (d.associated_person IS NOT NULL AND toLower(d.associated_person) CONTAINS $name)
        RETURN DISTINCT d.document_id AS doc_id
        LIMIT 50
        """,
        {"name": sanitized, "tid": tenant_id},
    )
    rows2 = await falkordb_client.execute_cypher(
        """
        MATCH (d:Document {tenant_id: $tid})-[:CONTAINED_IN]->(f:Folder)
        WHERE toLower(f.name) CONTAINS $name
        RETURN DISTINCT d.document_id AS doc_id
        LIMIT 50
        """,
        {"name": sanitized, "tid": tenant_id},
    )
```

Update the `documents_by_entity` endpoint to call `_batch_documents_by_entity()` and remove the old 3-query fallback chain.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_batch_traversal.py::TestBatchDocumentsByEntity -v`
Expected: 5 PASS

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `pytest tests/ -v`
Expected: all 63+ tests pass

- [ ] **Step 6: Commit**

```bash
git add app/api/tree.py tests/test_batch_traversal.py
git commit -m "feat(kts): batch documents-by-entity with OPTIONAL MATCH chain (3→1 queries)"
```

---

### Task 3: Batch Seed Resolution (UNWIND)

**Files:**
- Modify: `knowledge-tree-service/app/services/subgraph_extractor.py:127-181`
- Modify: `knowledge-tree-service/tests/test_batch_traversal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
class TestBatchSeedResolution:
    """Verify UNWIND batch replaces per-entity seed resolution."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        await falkordb_client.execute_cypher("""
            CREATE (e1:Entity {name: 'Juan Garcia', entity_type: 'person', tenant_id: 't1', normalized_name: 'juan garcia'})
            CREATE (e2:Entity {name: 'Acme Corp', entity_type: 'organization', tenant_id: 't1', normalized_name: 'acme corp'})
            CREATE (d1:Document {document_id: 'doc-seed-1', title: 'Contrato Laboral', tenant_id: 't1'})
            CREATE (e1)-[:MENTIONED_IN]->(d1)
            CREATE (e2)-[:MENTIONED_IN]->(d1)
        """)

    async def test_resolves_multiple_seeds_in_one_query(self, falkordb_client):
        """Must find both entities with a single Cypher query."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        entities = [
            {"name": "juan garcia", "type": "person"},
            {"name": "acme corp", "type": "organization"},
        ]
        async with QueryCounter() as counter:
            seeds = await extractor._resolve_seeds(entities, 't1')
            assert counter.count == 1, f"Expected 1 query, got {counter.count}"

        seed_names = [s["name"].lower() for s in seeds]
        assert "juan garcia" in seed_names
        assert "acme corp" in seed_names

    async def test_returns_node_ids(self, falkordb_client):
        """Seeds must include integer node IDs for Phase 2."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        entities = [{"name": "juan garcia", "type": "person"}]
        seeds = await extractor._resolve_seeds(entities, 't1')
        assert len(seeds) >= 1
        assert "nid" in seeds[0] or "id" in seeds[0], "Seed must include node ID"

    async def test_matches_by_title(self, falkordb_client):
        """Seed resolution matches Document nodes by title too."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        entities = [{"name": "contrato laboral", "type": "document"}]
        seeds = await extractor._resolve_seeds(entities, 't1')
        assert len(seeds) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Expected: tests fail because `_resolve_seeds` still uses per-entity loop

- [ ] **Step 3: Rewrite `_resolve_seeds` with UNWIND batch**

In `subgraph_extractor.py`, replace the for-loop in `_resolve_seeds` with:

```python
async def _resolve_seeds(self, entities: List[Dict], tenant_id: str) -> List[Dict]:
    """Resolve entity names to graph nodes in a single batched query.

    Uses UNWIND to search all entity names in one Cypher execution.
    Matches across name, title, and associated_person properties
    on any node label (Entity, Document, etc.).
    """
    if not entities:
        return []

    names = [e["name"].lower().strip() for e in entities if e.get("name")]
    if not names:
        return []

    rows = await falkordb_client.execute_cypher(
        """
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
        """,
        {"names": names, "tid": tenant_id, "max_seeds": self._max_seeds},
    )

    seeds = []
    seen_ids = set()
    for row in rows:
        nid = row.get("nid")
        if nid is not None and nid not in seen_ids:
            seen_ids.add(nid)
            seeds.append({
                "name": row.get("name", ""),
                "types": row.get("types", []),
                "entity_type": row.get("entity_type"),
                "matched_query": row.get("matched_query"),
                "nid": nid,
            })
    return seeds
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_batch_traversal.py::TestBatchSeedResolution -v`
Expected: 3 PASS

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/services/subgraph_extractor.py tests/test_batch_traversal.py
git commit -m "feat(kts): batch seed resolution with UNWIND (5→1 queries)"
```

---

### Task 4: Batch N-hop Traversal (explicit 2-hop)

**Files:**
- Modify: `knowledge-tree-service/app/services/subgraph_extractor.py:183-306`
- Modify: `knowledge-tree-service/tests/test_batch_traversal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
class TestBatchTraversal:
    """Verify explicit 2-hop batch replaces per-seed traversal."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        await falkordb_client.execute_cypher("""
            CREATE (e1:Entity {name: 'Juan', entity_type: 'person', tenant_id: 't1'})
            CREATE (e2:Entity {name: 'Acme', entity_type: 'organization', tenant_id: 't1'})
            CREATE (d1:Document {document_id: 'doc-t-1', title: 'Contrato', tenant_id: 't1'})
            CREATE (d2:Document {document_id: 'doc-t-2', title: 'Nomina', tenant_id: 't1'})
            CREATE (e1)-[:MENTIONED_IN]->(d1)
            CREATE (e2)-[:MENTIONED_IN]->(d1)
            CREATE (e1)-[:MENTIONED_IN]->(d2)
            CREATE (e1)-[:RELATED_TO {relation_type: 'empleado_de'}]->(e2)
        """)

    async def test_traverses_all_seeds_in_one_query(self, falkordb_client):
        """Must traverse from multiple seeds with 1 Cypher query."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        # Get seed IDs first
        rows = await falkordb_client.execute_cypher(
            "MATCH (e:Entity {tenant_id: 't1'}) RETURN id(e) AS nid, e.name AS name"
        )
        seed_ids = [r["nid"] for r in rows]

        async with QueryCounter() as counter:
            nodes, edges = await extractor._traverse(seed_ids, 't1')
            assert counter.count == 1, f"Expected 1 traversal query, got {counter.count}"

        # Should find documents connected to seeds
        doc_ids = [n.get("document_id") for n in nodes if n.get("document_id")]
        assert len(doc_ids) >= 1

    async def test_reaches_2_hops(self, falkordb_client):
        """Explicit hop1 + OPTIONAL hop2 reaches 2-hop neighbors."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        # Seed from Juan only — should reach Acme (hop1) and doc-t-1 (hop2 via Acme)
        rows = await falkordb_client.execute_cypher(
            "MATCH (e:Entity {name: 'Juan', tenant_id: 't1'}) RETURN id(e) AS nid"
        )
        seed_ids = [rows[0]["nid"]]

        nodes, edges = await extractor._traverse(seed_ids, 't1')
        node_names = [n.get("name", n.get("title", "")) for n in nodes]
        assert any("Acme" in n for n in node_names), "Should reach Acme via hop1"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `_traverse` still uses per-seed loop

- [ ] **Step 3: Rewrite `_traverse` with batch explicit 2-hop**

```python
async def _traverse(self, seed_ids: List[int], tenant_id: str) -> Tuple[List[Dict], List[Dict]]:
    """Batch 2-hop traversal from all seeds in a single query.

    Uses explicit MATCH hop1 + OPTIONAL MATCH hop2 instead of
    variable-length paths (FalkorDB limitation workaround).
    """
    if not seed_ids:
        return [], []

    rows = await falkordb_client.execute_cypher(
        """
        MATCH (seed)
        WHERE id(seed) IN $seed_ids
        MATCH (seed)-[r1]-(hop1)
        WHERE hop1.tenant_id = $tid OR hop1.shared = true
        OPTIONAL MATCH (hop1)-[r2]-(hop2)
        WHERE (hop2.tenant_id = $tid OR hop2.shared = true)
          AND id(hop2) <> id(seed)
        RETURN
          id(seed) AS seed_id, seed.name AS seed_name,
          type(r1) AS r1_type, id(hop1) AS h1_id,
          hop1.name AS h1_name, labels(hop1) AS h1_labels,
          hop1.document_id AS h1_doc_id, hop1.title AS h1_title,
          type(r2) AS r2_type, id(hop2) AS h2_id,
          hop2.name AS h2_name, labels(hop2) AS h2_labels,
          hop2.document_id AS h2_doc_id, hop2.title AS h2_title
        LIMIT $max_nodes
        """,
        {"seed_ids": seed_ids, "tid": tenant_id, "max_nodes": self._max_nodes},
    )

    # Collect unique nodes and edges
    nodes = {}  # id -> dict
    edges = []

    for row in rows:
        # hop1 node
        h1_id = row.get("h1_id")
        if h1_id is not None and h1_id not in nodes:
            nodes[h1_id] = {
                "name": row.get("h1_name") or row.get("h1_title", ""),
                "labels": row.get("h1_labels", []),
                "document_id": row.get("h1_doc_id"),
                "title": row.get("h1_title"),
            }

        # hop1 edge
        if row.get("r1_type"):
            edges.append({
                "source": row["seed_id"],
                "target": h1_id,
                "type": row["r1_type"],
            })

        # hop2 node (optional)
        h2_id = row.get("h2_id")
        if h2_id is not None and h2_id not in nodes:
            nodes[h2_id] = {
                "name": row.get("h2_name") or row.get("h2_title", ""),
                "labels": row.get("h2_labels", []),
                "document_id": row.get("h2_doc_id"),
                "title": row.get("h2_title"),
            }

        if h2_id is not None and row.get("r2_type"):
            edges.append({
                "source": h1_id,
                "target": h2_id,
                "type": row["r2_type"],
            })

    return list(nodes.values()), edges
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_batch_traversal.py::TestBatchTraversal -v`
Expected: 2 PASS

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`

- [ ] **Step 6: Commit**

```bash
git add app/services/subgraph_extractor.py tests/test_batch_traversal.py
git commit -m "feat(kts): batch 2-hop traversal for all seeds (5→1 queries)"
```

---

### Task 5: Batch Claims + Contradictions

**Files:**
- Modify: `knowledge-tree-service/app/services/subgraph_extractor.py:309-417`
- Modify: `knowledge-tree-service/tests/test_batch_traversal.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
class TestBatchClaims:
    """Verify batch claims+contradictions replaces per-entity loop."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        await falkordb_client.execute_cypher("""
            CREATE (e1:Entity {name: 'Juan', entity_type: 'person', tenant_id: 't1'})
            CREATE (d1:Document {document_id: 'doc-c-1', title: 'Contrato', tenant_id: 't1'})
            CREATE (c1:Claim {claim_id: 'claim-1', statement: '45000 EUR', claim_type: 'numeric', confidence: 0.9, tenant_id: 't1'})
            CREATE (c2:Claim {claim_id: 'claim-2', statement: '42000 EUR', claim_type: 'numeric', confidence: 0.85, tenant_id: 't1'})
            CREATE (c1)-[:ABOUT]->(e1)
            CREATE (c2)-[:ABOUT]->(e1)
            CREATE (c1)-[:EXTRACTED_FROM]->(d1)
            CREATE (c2)-[:EXTRACTED_FROM]->(d1)
            CREATE (c1)-[:CONTRADICTS]->(c2)
        """)

    async def test_fetches_claims_for_multiple_entities(self, falkordb_client):
        """Batch query returns claims for all entity IDs."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        rows = await falkordb_client.execute_cypher(
            "MATCH (e:Entity {tenant_id: 't1'}) RETURN id(e) AS nid"
        )
        entity_ids = [r["nid"] for r in rows]

        async with QueryCounter() as counter:
            claims = await extractor._fetch_entity_claims(entity_ids, 't1')
            assert counter.count == 1, f"Expected 1 query, got {counter.count}"

        claim_ids = [c["claim_id"] for c in claims]
        assert "claim-1" in claim_ids
        assert "claim-2" in claim_ids

    async def test_includes_contradictions(self, falkordb_client):
        """Batch query includes contradiction info."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        rows = await falkordb_client.execute_cypher(
            "MATCH (e:Entity {tenant_id: 't1'}) RETURN id(e) AS nid"
        )
        entity_ids = [r["nid"] for r in rows]
        claims = await extractor._fetch_entity_claims(entity_ids, 't1')

        # At least one claim should have contradiction info
        contradicted = [c for c in claims if c.get("contradicts_id")]
        assert len(contradicted) >= 1

    async def test_includes_document_source(self, falkordb_client):
        """Claims include their source document."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        rows = await falkordb_client.execute_cypher(
            "MATCH (e:Entity {tenant_id: 't1'}) RETURN id(e) AS nid"
        )
        entity_ids = [r["nid"] for r in rows]
        claims = await extractor._fetch_entity_claims(entity_ids, 't1')

        sourced = [c for c in claims if c.get("doc_id")]
        assert len(sourced) >= 1
        assert sourced[0]["doc_id"] == "doc-c-1"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `_fetch_entity_claims` takes different args or uses per-entity loop

- [ ] **Step 3: Rewrite `_fetch_entity_claims` with batch query**

```python
async def _fetch_entity_claims(self, entity_ids: List[int], tenant_id: str) -> List[Dict]:
    """Fetch all claims + contradictions for discovered entities in one query.

    Replaces per-entity claims loop + separate contradiction scan.
    Contradictions are anchored to specific claims (not full-tenant scan).
    """
    if not entity_ids:
        return []

    rows = await falkordb_client.execute_cypher(
        """
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
          contra.claim_id AS contradicts_id,
          contra.statement AS contradicts_statement
        ORDER BY c.confidence DESC
        LIMIT $max_claims
        """,
        {"entity_ids": entity_ids, "tid": tenant_id, "max_claims": 50},
    )

    # Deduplicate claims (same claim may appear for multiple entities)
    seen = set()
    claims = []
    for row in rows:
        cid = row.get("claim_id")
        if cid and cid not in seen:
            seen.add(cid)
            claims.append(row)
    return claims
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_batch_traversal.py::TestBatchClaims -v`
Expected: 3 PASS

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`

- [ ] **Step 6: Commit**

```bash
git add app/services/subgraph_extractor.py tests/test_batch_traversal.py
git commit -m "feat(kts): batch claims+contradictions fetch (20→1 queries)"
```

---

### Task 6: Wire Up and Integration Test

**Files:**
- Modify: `knowledge-tree-service/app/services/subgraph_extractor.py` (extract method)
- Modify: `knowledge-tree-service/tests/test_batch_traversal.py`

- [ ] **Step 1: Write integration test with query counter**

```python
@pytest.mark.asyncio
class TestFullSubgraphExtraction:
    """End-to-end: full extract() call uses ≤4 queries total."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_data(self, falkordb_client):
        await falkordb_client.execute_cypher("""
            CREATE (e1:Entity {name: 'Juan Garcia', entity_type: 'person', tenant_id: 't1', normalized_name: 'juan garcia'})
            CREATE (e2:Entity {name: 'Acme Corp', entity_type: 'organization', tenant_id: 't1', normalized_name: 'acme corp'})
            CREATE (d1:Document {document_id: 'doc-int-1', title: 'Contrato', tenant_id: 't1'})
            CREATE (c1:Claim {claim_id: 'claim-int-1', statement: '45000 EUR', claim_type: 'numeric', confidence: 0.9, tenant_id: 't1'})
            CREATE (e1)-[:MENTIONED_IN]->(d1)
            CREATE (e2)-[:MENTIONED_IN]->(d1)
            CREATE (e1)-[:RELATED_TO]->(e2)
            CREATE (c1)-[:ABOUT]->(e1)
            CREATE (c1)-[:EXTRACTED_FROM]->(d1)
        """)

    async def test_total_queries_within_budget(self, falkordb_client):
        """Full subgraph extraction must use ≤4 Cypher queries."""
        from app.services.subgraph_extractor import SubgraphExtractor
        extractor = SubgraphExtractor()
        await extractor.initialize()

        entities = [
            {"name": "juan garcia", "type": "person"},
            {"name": "acme corp", "type": "organization"},
        ]
        async with QueryCounter() as counter:
            result = await extractor.extract(
                entities=entities,
                tenant_id='t1',
                max_hops=2,
                max_nodes=30,
            )
            assert counter.count <= 4, \
                f"Query budget exceeded: {counter.count} queries (max 4)"

        assert result is not None
```

- [ ] **Step 2: Run test to verify it fails or passes**

If extract() still uses old methods internally, this may fail on query count. Wire up the new batched methods in extract().

- [ ] **Step 3: Update `extract()` to use batched phases**

Ensure `extract()` calls:
1. `_resolve_seeds(entities, tenant_id)` → batched (1 query)
2. `_traverse(seed_ids, tenant_id)` → batched (1 query)
3. `_fetch_entity_claims(entity_ids, tenant_id)` → batched (1 query)
4. Pruning + scoring → in-memory (0 queries)

Total: 3 queries (within ≤4 budget).

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: all pass, including new batch tests and existing 63 tests

- [ ] **Step 5: Run sanity checks**

```bash
APIKEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)
curl -s http://localhost:8019/diagnostics/e2e -H "X-API-Key: $APIKEY" | python3 -m json.tool
```

Expected: 13/13 E2E checks pass (including `graph_entity_query`)

- [ ] **Step 6: Commit**

```bash
git add app/services/subgraph_extractor.py tests/test_batch_traversal.py
git commit -m "feat(kts): wire up batched subgraph extraction (24→3 queries)"
```
