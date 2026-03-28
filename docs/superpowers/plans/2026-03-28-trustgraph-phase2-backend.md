# TrustGraph Phase 2 Backend — Graph RAG + SmartSearch Improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Graph RAG as a new ReAct tool alongside multi-concept SmartSearch improvements, both sharing a concept extraction pre-step.

**Architecture:** Shared concept extraction (LLM) feeds two independent pipelines: (1) `graph_rag` tool — entity embeddings → BFS subgraph → LLM edge scoring → formatted context, (2) upgraded `smart_search` — multi-concept parallel hybrid search + retrieval provenance. Both registered as ReAct tools.

**Tech Stack:** Python 3.9+, FalkorDB (Cypher), Weaviate (vector search), Langfuse (prompts), intelligence-docs-service (BGE-M3 embeddings), asyncio, httpx.

**Spec:** `docs/superpowers/specs/2026-03-28-trustgraph-phase2-backend-graph-rag-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `emma/tools/concept_extractor.py` | **NEW** — LLM concept extraction shared by graph_rag and smart_search |
| `emma/tools/graph_rag.py` | **NEW** — Full Graph RAG pipeline (6 stages) as ReAct tool |
| `emma/tools/smart_search.py` | **MODIFY** — Multi-concept search, provenance, continuous graph signal |
| `emma/tools/registry.py` | **MODIFY** — Register graph_rag tool |
| `emma/sectors/graph_expander.py` | **DEPRECATE** — Replaced by graph_rag tool |
| `emma/core/config.py` | **MODIFY** — New GRAPH_RAG_* settings |
| `emma/clients/knowledge_tree_client.py` | **MODIFY** — Add `batch_neighbors()` method |
| `emma/clients/weaviate_client.py` | **MODIFY** — Add `search_entities()` method |
| `emma/services/prompt_registry.py` | **MODIFY** — Register 3 new prompt names |
| `emma/scripts/migrate_trustgraph_phase2_prompts.py` | **NEW** — Push 3 prompts to Langfuse |
| `kts/api/triples.py` | **MODIFY** — Add POST /triples/neighbors |
| `kts/services/triple_query.py` | **MODIFY** — Add `batch_neighbors()` method |
| `weaviate-service/services/weaviate_service.py` | **MODIFY** — TrustGraphEntities collection |
| `weaviate-service/api/weaviate.py` | **MODIFY** — Entity search endpoint |
| `kts/scripts/reindex_trustgraph.py` | **MODIFY** — Entity embedding step |
| `emma/tests/test_concept_extractor.py` | **NEW** — Unit tests |
| `emma/tests/test_graph_rag.py` | **NEW** — Unit tests |
| `kts/tests/test_batch_neighbors.py` | **NEW** — Unit tests |

**Path prefix legend:**
- `emma/` = `backend/microservices/emma-agent-service/app/agents/langgraph/`
- `kts/` = `backend/microservices/knowledge-tree-service/app/`
- `weaviate-service/` = `backend/microservices/weaviate-service/app/`

---

## Task 1: KTS Batch Neighbors Endpoint

The Graph RAG pipeline needs efficient BFS traversal. Instead of N individual `/triples/query` calls, we add a single `/triples/neighbors` endpoint that does iterative BFS server-side.

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/services/triple_query.py`
- Modify: `backend/microservices/knowledge-tree-service/app/api/triples.py`
- Create: `backend/microservices/knowledge-tree-service/tests/test_batch_neighbors.py`

- [ ] **Step 1: Write the failing test for `batch_neighbors`**

```python
# backend/microservices/knowledge-tree-service/tests/test_batch_neighbors.py
"""Tests for TripleQuery.batch_neighbors — BFS subgraph traversal."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.triple_query import TripleQuery


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.execute_cypher = AsyncMock(return_value=[])
    return client


@pytest.fixture
def tq(mock_client):
    return TripleQuery(mock_client)


@pytest.mark.asyncio
async def test_batch_neighbors_empty_seeds(tq):
    """Empty seed list returns empty result."""
    result = await tq.batch_neighbors(
        seed_uris=[], user="tenant-1",
    )
    assert result["edges"] == []
    assert result["entities_visited"] == 0
    assert result["hops_used"] == 0


@pytest.mark.asyncio
async def test_batch_neighbors_single_hop(tq, mock_client):
    """Single seed entity returns its direct neighbors."""
    mock_client.execute_cypher = AsyncMock(return_value=[
        {
            "subject": "nouxcube://entity/default/lgt",
            "predicate": "nouxcube://predicate/legal/regula",
            "object": "nouxcube://entity/default/irpf",
            "object_type": "node",
            "extraction_method": "relationship_extractor",
            "source_chunk": None,
        },
    ])
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/lgt"],
        user="tenant-1",
        max_hops=1,
        max_edges=150,
    )
    assert len(result["edges"]) == 1
    assert result["edges"][0]["subject"] == "nouxcube://entity/default/lgt"
    assert result["edges"][0]["predicate"] == "nouxcube://predicate/legal/regula"
    assert result["entities_visited"] >= 1
    assert result["hops_used"] == 1


@pytest.mark.asyncio
async def test_batch_neighbors_excludes_prov_predicates(tq, mock_client):
    """Edges with prov/* predicates are excluded."""
    mock_client.execute_cypher = AsyncMock(return_value=[
        {
            "subject": "nouxcube://entity/default/lgt",
            "predicate": "nouxcube://predicate/prov/generated-by",
            "object": "nouxcube://entity/default/extractor",
            "object_type": "node",
        },
        {
            "subject": "nouxcube://entity/default/lgt",
            "predicate": "nouxcube://predicate/legal/regula",
            "object": "nouxcube://entity/default/irpf",
            "object_type": "node",
        },
    ])
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/lgt"],
        user="tenant-1",
        max_hops=1,
        exclude_predicates=["prov/.*"],
    )
    # Only the legal edge survives
    assert len(result["edges"]) == 1
    assert "prov/" not in result["edges"][0]["predicate"]


@pytest.mark.asyncio
async def test_batch_neighbors_respects_max_edges(tq, mock_client):
    """Stop collecting when max_edges is reached."""
    # Return 10 edges per call
    edges = [
        {
            "subject": f"nouxcube://entity/default/e{i}",
            "predicate": "nouxcube://predicate/core/related-to",
            "object": f"nouxcube://entity/default/e{i+100}",
            "object_type": "node",
        }
        for i in range(10)
    ]
    mock_client.execute_cypher = AsyncMock(return_value=edges)
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/e0"],
        user="tenant-1",
        max_hops=3,
        max_edges=5,
    )
    assert len(result["edges"]) <= 5


@pytest.mark.asyncio
async def test_batch_neighbors_multi_hop(tq, mock_client):
    """Two hops: seeds → hop1 neighbors → hop2 neighbors."""
    call_count = 0

    async def mock_cypher(query, params=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Hop 1: seed → neighbor
            return [{
                "subject": "nouxcube://entity/default/a",
                "predicate": "nouxcube://predicate/core/related-to",
                "object": "nouxcube://entity/default/b",
                "object_type": "node",
            }]
        else:
            # Hop 2: neighbor → new entity
            return [{
                "subject": "nouxcube://entity/default/b",
                "predicate": "nouxcube://predicate/legal/modifica",
                "object": "nouxcube://entity/default/c",
                "object_type": "node",
            }]

    mock_client.execute_cypher = AsyncMock(side_effect=mock_cypher)
    result = await tq.batch_neighbors(
        seed_uris=["nouxcube://entity/default/a"],
        user="tenant-1",
        max_hops=2,
        max_edges=150,
    )
    assert len(result["edges"]) == 2
    assert result["hops_used"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_batch_neighbors.py -v`
Expected: FAIL — `batch_neighbors` not found on `TripleQuery`

- [ ] **Step 3: Implement `batch_neighbors` in triple_query.py**

Add to `backend/microservices/knowledge-tree-service/app/services/triple_query.py` after the existing methods:

```python
    # ------------------------------------------------------------------
    # batch_neighbors — BFS subgraph traversal
    # ------------------------------------------------------------------

    async def batch_neighbors(
        self,
        seed_uris: list[str],
        user: str,
        collection: str | None = None,
        max_hops: int = 2,
        max_edges: int = 150,
        triples_per_entity: int = 30,
        exclude_predicates: list[str] | None = None,
    ) -> dict[str, Any]:
        """Iterative BFS from seed entities, collecting Node→Node edges.

        Args:
            seed_uris: Starting entity URIs.
            user: Tenant ID for isolation.
            collection: Optional collection scope.
            max_hops: Maximum BFS depth.
            max_edges: Stop collecting after this many edges.
            triples_per_entity: Max outgoing edges per entity per hop.
            exclude_predicates: Regex patterns to skip (e.g. ["prov/.*"]).

        Returns:
            {"edges": [...], "entities_visited": int, "hops_used": int}
        """
        if not seed_uris:
            return {"edges": [], "entities_visited": 0, "hops_used": 0}

        import re

        exclude_patterns = [
            re.compile(f".*{p}") for p in (exclude_predicates or [])
        ]

        all_edges: list[dict[str, Any]] = []
        visited: set[str] = set()
        frontier: set[str] = set(seed_uris)
        hops_used = 0

        col_filter = _col_where("s", collection)

        for hop in range(max_hops):
            if not frontier or len(all_edges) >= max_edges:
                break

            # Build UNWIND query for all frontier URIs at once
            batch_uris = list(frontier - visited)
            if not batch_uris:
                break

            visited.update(batch_uris)

            query = (
                "UNWIND $uris AS uri "
                "MATCH (s:Node {user: $user})-[r:Rel]->(o:Node) "
                f"WHERE s.uri = uri{col_filter} "
                "RETURN s.uri AS subject, r.uri AS predicate, "
                f"{_OBJECT_EXPR}, "
                "r.extraction_method AS extraction_method, "
                "r.source_chunk AS source_chunk "
                "LIMIT $limit"
            )
            params = self._base_params(
                user, collection,
                uris=batch_uris,
                limit=triples_per_entity * len(batch_uris),
            )

            rows = await self._client.execute_cypher(query, params=params)

            next_frontier: set[str] = set()
            for row in rows:
                triple = self._row_to_triple(row)
                predicate = triple.get("predicate", "")

                # Apply exclude patterns
                if any(p.match(predicate) for p in exclude_patterns):
                    continue

                # Skip core/label — resolved separately
                if predicate.endswith("core/label"):
                    continue

                all_edges.append(triple)
                if len(all_edges) >= max_edges:
                    break

                # Add object to next frontier if it's a node
                obj = triple.get("object", "")
                if triple.get("object_type") == "node" and obj not in visited:
                    next_frontier.add(obj)

            frontier = next_frontier
            hops_used = hop + 1

        return {
            "edges": all_edges[:max_edges],
            "entities_visited": len(visited),
            "hops_used": hops_used,
        }
```

- [ ] **Step 4: Add the API endpoint in triples.py**

Add to `backend/microservices/knowledge-tree-service/app/api/triples.py`:

```python
class NeighborsRequest(BaseModel):
    tenant_id: str
    seed_uris: list[str]
    max_hops: int = 2
    max_edges: int = 150
    triples_per_entity: int = 30
    exclude_predicates: list[str] = []


class NeighborsResponse(BaseModel):
    edges: list[dict]
    entities_visited: int
    hops_used: int


@router.post("/neighbors", response_model=NeighborsResponse)
async def batch_neighbors(request: NeighborsRequest) -> NeighborsResponse:
    """BFS subgraph traversal from seed entities."""
    tq = TripleQuery(falkordb_client)
    result = await tq.batch_neighbors(
        seed_uris=request.seed_uris,
        user=request.tenant_id,
        max_hops=request.max_hops,
        max_edges=request.max_edges,
        triples_per_entity=request.triples_per_entity,
        exclude_predicates=request.exclude_predicates,
    )
    return NeighborsResponse(**result)
```

- [ ] **Step 5: Run tests and verify they pass**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_batch_neighbors.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/triple_query.py \
       backend/microservices/knowledge-tree-service/app/api/triples.py \
       backend/microservices/knowledge-tree-service/tests/test_batch_neighbors.py
git commit -m "feat(trustgraph): add /triples/neighbors BFS endpoint for Graph RAG"
```

---

## Task 2: Weaviate TrustGraphEntities Collection + Search Endpoint

Entity embeddings stored in Weaviate for vector similarity search during Graph RAG entity retrieval.

**Files:**
- Modify: `backend/microservices/weaviate-service/app/services/weaviate_service.py`
- Modify: `backend/microservices/weaviate-service/app/api/weaviate.py`

- [ ] **Step 1: Add `TrustGraphEntities` collection management to WeaviateService**

In `backend/microservices/weaviate-service/app/services/weaviate_service.py`, add after the existing collection creation methods:

```python
    # ── TrustGraphEntities ────────────────────────────────────────────

    TRUSTGRAPH_ENTITIES_COLLECTION = "TrustGraphEntities"

    async def ensure_trustgraph_entities_collection(self) -> None:
        """Create TrustGraphEntities collection if it doesn't exist."""
        await self.ensure_initialized()
        name = self.TRUSTGRAPH_ENTITIES_COLLECTION
        if self.client.collections.exists(name):
            logger.info(f"Collection {name} already exists")
            return

        dims = await self._get_embedding_dimensions()

        from weaviate.classes.config import (
            Configure,
            Property,
            DataType,
        )

        self.client.collections.create(
            name=name,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=Configure.VectorDistances.COSINE,
            ),
            properties=[
                Property(name="entity_uri", data_type=DataType.TEXT),
                Property(name="label", data_type=DataType.TEXT),
                Property(name="definition", data_type=DataType.TEXT),
                Property(name="entity_type", data_type=DataType.TEXT),
                Property(name="tenant_id", data_type=DataType.TEXT),
                Property(name="collection", data_type=DataType.TEXT),
                Property(name="embed_text", data_type=DataType.TEXT),
            ],
        )
        logger.info(f"Created collection {name} with {dims}d vectors")

    async def upsert_trustgraph_entity(
        self,
        entity_uri: str,
        label: str,
        definition: str,
        entity_type: str,
        tenant_id: str,
        collection: str,
        embedding: list[float],
    ) -> None:
        """Upsert a single entity with its embedding."""
        await self.ensure_initialized()
        coll = self.client.collections.get(self.TRUSTGRAPH_ENTITIES_COLLECTION)
        embed_text = f"{label} ({entity_type}). {definition}" if definition else f"{label} ({entity_type})"

        # Delete existing by entity_uri + tenant_id (upsert semantics)
        from weaviate.classes.query import Filter

        existing = coll.query.fetch_objects(
            filters=(
                Filter.by_property("entity_uri").equal(entity_uri)
                & Filter.by_property("tenant_id").equal(tenant_id)
            ),
            limit=1,
        )
        for obj in existing.objects:
            coll.data.delete_by_id(obj.uuid)

        coll.data.insert(
            properties={
                "entity_uri": entity_uri,
                "label": label,
                "definition": definition or "",
                "entity_type": entity_type,
                "tenant_id": tenant_id,
                "collection": collection,
                "embed_text": embed_text,
            },
            vector=embedding,
        )

    async def upsert_trustgraph_entities_batch(
        self,
        entities: list[dict],
        embeddings: list[list[float]],
        tenant_id: str,
    ) -> int:
        """Batch upsert entities with embeddings.

        Args:
            entities: List of dicts with keys: entity_uri, label, definition, entity_type, collection
            embeddings: Corresponding embedding vectors.
            tenant_id: Tenant isolation.

        Returns:
            Number of entities upserted.
        """
        await self.ensure_initialized()
        await self.ensure_trustgraph_entities_collection()
        coll = self.client.collections.get(self.TRUSTGRAPH_ENTITIES_COLLECTION)

        count = 0
        with coll.batch.dynamic() as batch:
            for entity, embedding in zip(entities, embeddings):
                embed_text = (
                    f"{entity['label']} ({entity['entity_type']}). {entity.get('definition', '')}"
                    if entity.get("definition")
                    else f"{entity['label']} ({entity['entity_type']})"
                )
                batch.add_object(
                    properties={
                        "entity_uri": entity["entity_uri"],
                        "label": entity["label"],
                        "definition": entity.get("definition", ""),
                        "entity_type": entity["entity_type"],
                        "tenant_id": tenant_id,
                        "collection": entity.get("collection", "default"),
                        "embed_text": embed_text,
                    },
                    vector=embedding,
                )
                count += 1
        return count

    async def search_trustgraph_entities(
        self,
        query_embedding: list[float],
        tenant_id: str,
        collection: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search entities by vector similarity.

        Returns:
            List of dicts: {entity_uri, label, definition, entity_type, score}
        """
        await self.ensure_initialized()
        name = self.TRUSTGRAPH_ENTITIES_COLLECTION
        if not self.client.collections.exists(name):
            return []

        coll = self.client.collections.get(name)
        from weaviate.classes.query import Filter, MetadataQuery

        filters = Filter.by_property("tenant_id").equal(tenant_id)
        if collection:
            filters = filters & Filter.by_property("collection").equal(collection)

        result = coll.query.near_vector(
            near_vector=query_embedding,
            filters=filters,
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
        )

        entities = []
        for obj in result.objects:
            score = 1.0 - (obj.metadata.distance or 0.0)  # cosine distance → similarity
            entities.append({
                "entity_uri": obj.properties.get("entity_uri", ""),
                "label": obj.properties.get("label", ""),
                "definition": obj.properties.get("definition", ""),
                "entity_type": obj.properties.get("entity_type", ""),
                "score": round(score, 4),
            })
        return entities

    async def delete_trustgraph_entities(self, tenant_id: str) -> int:
        """Delete all entities for a tenant (used by reindex)."""
        await self.ensure_initialized()
        name = self.TRUSTGRAPH_ENTITIES_COLLECTION
        if not self.client.collections.exists(name):
            return 0

        coll = self.client.collections.get(name)
        from weaviate.classes.query import Filter

        result = coll.data.delete_many(
            where=Filter.by_property("tenant_id").equal(tenant_id),
        )
        return result.successful if hasattr(result, "successful") else 0
```

- [ ] **Step 2: Add entity search API endpoint**

In `backend/microservices/weaviate-service/app/api/weaviate.py`, add:

```python
class EntitySearchRequest(BaseModel):
    query: str
    tenant_id: str
    collection: str | None = None
    limit: int = 50


@router.post("/entities/search")
async def search_entities(
    request: EntitySearchRequest,
    _: bool = Depends(verify_api_key),
):
    """Search TrustGraph entities by similarity."""
    # Embed the query
    embedding = await generate_embedding(request.query, task="retrieval.query")
    if embedding is None:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    service = get_weaviate_service()
    entities = await service.search_trustgraph_entities(
        query_embedding=embedding,
        tenant_id=request.tenant_id,
        collection=request.collection,
        limit=request.limit,
    )
    return {"entities": entities, "count": len(entities)}
```

- [ ] **Step 3: Run existing weaviate-service tests to check for regressions**

Run: `cd backend/microservices/weaviate-service && python -m pytest tests/ -v --timeout=30`
Expected: Existing tests still pass

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/weaviate-service/app/services/weaviate_service.py \
       backend/microservices/weaviate-service/app/api/weaviate.py
git commit -m "feat(trustgraph): TrustGraphEntities collection + entity search endpoint"
```

---

## Task 3: Emma Config — Graph RAG Settings

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/core/config.py`

- [ ] **Step 1: Add Graph RAG configuration settings**

In `backend/microservices/emma-agent-service/app/core/config.py`, find the existing `graphrag_*` settings block and replace with:

```python
    # ── Graph RAG (Phase 2) ─────────────────────────────────────────
    # Replaces Phase 1 graphrag_* settings
    graph_rag_enabled: bool = os.getenv("GRAPH_RAG_ENABLED", "true").lower() == "true"
    graph_rag_entity_limit: int = int(os.getenv("GRAPH_RAG_ENTITY_LIMIT", "50"))
    graph_rag_max_hops: int = int(os.getenv("GRAPH_RAG_MAX_HOPS", "2"))
    graph_rag_max_edges: int = int(os.getenv("GRAPH_RAG_MAX_EDGES", "150"))
    graph_rag_edge_limit: int = int(os.getenv("GRAPH_RAG_EDGE_LIMIT", "25"))
    graph_rag_prefilter_limit: int = int(os.getenv("GRAPH_RAG_PREFILTER_LIMIT", "30"))
    graph_rag_label_cache_ttl: int = int(os.getenv("GRAPH_RAG_LABEL_CACHE_TTL", "300"))

    # SmartSearch multi-concept (Phase 2)
    smart_search_multi_concept: bool = os.getenv("SMART_SEARCH_MULTI_CONCEPT", "true").lower() == "true"

    # Retrieval provenance tracking
    retrieval_provenance_enabled: bool = os.getenv("RETRIEVAL_PROVENANCE_ENABLED", "true").lower() == "true"
```

Keep the old `graphrag_*` settings but mark them deprecated with a comment. SmartSearch still references `graphrag_enabled` internally for the _extract_subgraph call — we'll remove that reference in Task 7 when we integrate multi-concept search.

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/core/config.py
git commit -m "feat(trustgraph): add Graph RAG Phase 2 config settings"
```

---

## Task 4: Langfuse Prompt Migration

Register 3 new prompts in the prompt registry and push them to Langfuse.

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/services/prompt_registry.py`
- Create: `backend/microservices/emma-agent-service/scripts/migrate_trustgraph_phase2_prompts.py`

- [ ] **Step 1: Add prompt entries to the registry**

In `backend/microservices/emma-agent-service/app/services/prompt_registry.py`, add to `PROMPT_REGISTRY`:

```python
    # ── TrustGraph Phase 2 ──────────────────────────────────────────
    "trustgraph_extract_concepts": PromptEntry(
        yaml_path=("trustgraph", "extract_concepts"),
        description="Extract high/low-level concepts from user query for Graph RAG",
        section="trustgraph",
    ),
    "trustgraph_edge_scoring": PromptEntry(
        yaml_path=("trustgraph", "edge_scoring"),
        description="Score knowledge graph edges for relevance to query",
        section="trustgraph",
    ),
```

- [ ] **Step 2: Create migration script**

```python
#!/usr/bin/env python3
"""
Migration: TrustGraph Phase 2 prompts — concept extraction + edge scoring.

Pushes prompts directly to Langfuse (no YAML).

Usage:
    docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py
    docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py --dry-run
    docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py --force
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Concept extraction prompt ────────────────────────────────────────────────

EXTRACT_CONCEPTS_PROMPT = """\
You are a query analysis expert for a document management and legal knowledge system.
Extract key concepts from the user query for knowledge graph and document retrieval.

Return TWO types of concepts:
1. high_level_keywords: overarching themes, subject areas, legal domains, business topics
   Examples: "derecho laboral", "fiscalidad empresarial", "protección de datos"
2. low_level_keywords: specific entities, proper nouns, legal references, dates, amounts, document types
   Examples: "LGT", "Juan García", "contrato temporal", "Art. 54 ET"

Query: {query}

Respond ONLY with valid JSON:
{{"high_level_keywords": ["..."], "low_level_keywords": ["..."]}}"""


# ── Edge scoring prompt ──────────────────────────────────────────────────────

EDGE_SCORING_PROMPT = """\
Score the relevance of each knowledge graph edge to the user query.
Score 0 (irrelevant) to 10 (highly relevant).
Only consider edges that directly help answer the question.

Query: {query}

Edges (format: id | subject → predicate → object):
{edges_json}

Respond ONLY with a JSON array. Only include edges with score > 0:
[{{"id": "edge_id", "score": N}}, ...]"""


# ── Prompt definitions ───────────────────────────────────────────────────────

PROMPTS = {
    "trustgraph_extract_concepts": {
        "prompt": EXTRACT_CONCEPTS_PROMPT,
        "type": "text",
        "labels": ["production"],
    },
    "trustgraph_edge_scoring": {
        "prompt": EDGE_SCORING_PROMPT,
        "type": "text",
        "labels": ["production"],
    },
}


def main():
    parser = argparse.ArgumentParser(description="Migrate TrustGraph Phase 2 prompts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--force", action="store_true", help="Overwrite existing prompts")
    args = parser.parse_args()

    from langfuse import Langfuse

    langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "http://langfuse:3000"),
    )

    for name, config in PROMPTS.items():
        existing = None
        try:
            existing = langfuse.get_prompt(name, label="production")
        except Exception:
            pass

        if existing and not args.force:
            print(f"  SKIP {name} (exists, use --force to overwrite)")
            continue

        if args.dry_run:
            print(f"  DRY-RUN would create: {name}")
            continue

        langfuse.create_prompt(
            name=name,
            prompt=config["prompt"],
            type=config["type"],
            labels=config["labels"],
        )
        print(f"  ✓ Created {name}")

    langfuse.flush()
    print("Done.")


if __name__ == "__main__":
    main()
```

Save to: `backend/microservices/emma-agent-service/scripts/migrate_trustgraph_phase2_prompts.py`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/services/prompt_registry.py \
       backend/microservices/emma-agent-service/scripts/migrate_trustgraph_phase2_prompts.py
git commit -m "feat(trustgraph): Phase 2 Langfuse prompts — concept extraction + edge scoring"
```

---

## Task 5: KTS Client — `batch_neighbors` Method

Add the HTTP client method in emma-agent-service to call the new KTS endpoint.

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py`

- [ ] **Step 1: Add `batch_neighbors` to KnowledgeTreeClient**

In `backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py`, add before the singleton block:

```python
    async def batch_neighbors(
        self,
        tenant_id: str,
        seed_uris: list[str],
        max_hops: int = 2,
        max_edges: int = 150,
        triples_per_entity: int = 30,
        exclude_predicates: list[str] | None = None,
    ) -> dict[str, Any]:
        """BFS subgraph traversal via /triples/neighbors."""
        payload = {
            "tenant_id": tenant_id,
            "seed_uris": seed_uris,
            "max_hops": max_hops,
            "max_edges": max_edges,
            "triples_per_entity": triples_per_entity,
            "exclude_predicates": exclude_predicates or ["prov/.*"],
        }
        try:
            return await self.post_json("/triples/neighbors", json=payload, headers=self._headers())
        except Exception as e:
            logger.warning(f"Batch neighbors failed: {e}")
            return {"edges": [], "entities_visited": 0, "hops_used": 0}
```

- [ ] **Step 2: Add `search_entities` to WeaviateClient**

In `backend/microservices/emma-agent-service/app/clients/weaviate_client.py`, add a method:

```python
    async def search_entities(
        self,
        query: str,
        tenant_id: str,
        collection: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search TrustGraph entities by text similarity via weaviate-service."""
        payload = {
            "query": query,
            "tenant_id": tenant_id,
            "limit": limit,
        }
        if collection:
            payload["collection"] = collection
        try:
            result = await self.post_json(
                "/entities/search", json=payload, headers=self._headers()
            )
            return result.get("entities", [])
        except Exception as e:
            logger.warning(f"Entity search failed: {e}")
            return []

    async def search_entities_by_embedding(
        self,
        embedding: list[float],
        tenant_id: str,
        collection: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search entities using a pre-computed embedding vector."""
        payload = {
            "query_embedding": embedding,
            "tenant_id": tenant_id,
            "limit": limit,
        }
        if collection:
            payload["collection"] = collection
        try:
            result = await self.post_json(
                "/entities/search-by-embedding", json=payload, headers=self._headers()
            )
            return result.get("entities", [])
        except Exception as e:
            logger.warning(f"Entity search by embedding failed: {e}")
            return []
```

Also add a corresponding `/entities/search-by-embedding` endpoint in weaviate-service that accepts a raw embedding vector (similar to the text endpoint but skipping the embed step):

In `backend/microservices/weaviate-service/app/api/weaviate.py`:

```python
class EntitySearchByEmbeddingRequest(BaseModel):
    query_embedding: list[float]
    tenant_id: str
    collection: str | None = None
    limit: int = 50


@router.post("/entities/search-by-embedding")
async def search_entities_by_embedding(
    request: EntitySearchByEmbeddingRequest,
    _: bool = Depends(verify_api_key),
):
    """Search TrustGraph entities by pre-computed embedding."""
    service = get_weaviate_service()
    entities = await service.search_trustgraph_entities(
        query_embedding=request.query_embedding,
        tenant_id=request.tenant_id,
        collection=request.collection,
        limit=request.limit,
    )
    return {"entities": entities, "count": len(entities)}
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py \
       backend/microservices/emma-agent-service/app/clients/weaviate_client.py \
       backend/microservices/weaviate-service/app/api/weaviate.py
git commit -m "feat(trustgraph): client methods for batch_neighbors + entity search"
```

---

## Task 6: Concept Extractor (Shared)

LLM-based concept extraction shared by Graph RAG and SmartSearch.

**Files:**
- Create: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/concept_extractor.py`
- Create: `backend/microservices/emma-agent-service/tests/test_concept_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/microservices/emma-agent-service/tests/test_concept_extractor.py
"""Tests for shared concept extraction."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.langgraph.tools.concept_extractor import (
    extract_concepts,
    ConceptResult,
    _fallback_regex_concepts,
)


def test_fallback_regex_extracts_entities():
    """Regex fallback extracts person names and legal refs."""
    result = _fallback_regex_concepts("contratos de Juan García sobre la LGT")
    assert "Juan García" in result.low_level or any(
        "juan" in c.lower() for c in result.low_level
    )
    assert len(result.high_level) >= 0  # May or may not extract themes
    assert result.embeddings == {}  # Not computed in fallback


def test_fallback_regex_empty_query():
    """Empty query returns empty concepts."""
    result = _fallback_regex_concepts("")
    assert result.high_level == []
    assert result.low_level == []


@pytest.mark.asyncio
async def test_extract_concepts_success():
    """LLM extraction returns parsed concepts."""
    mock_response = MagicMock()
    mock_response.content = '{"high_level_keywords": ["derecho laboral"], "low_level_keywords": ["ET", "Juan García"]}'

    with patch(
        "app.agents.langgraph.tools.concept_extractor._call_llm",
        new_callable=AsyncMock,
        return_value=mock_response,
    ), patch(
        "app.agents.langgraph.tools.concept_extractor._batch_embed",
        new_callable=AsyncMock,
        return_value={"derecho laboral": [0.1] * 1024, "ET": [0.2] * 1024, "Juan García": [0.3] * 1024},
    ):
        result = await extract_concepts("derechos laborales de Juan García según ET", "tenant-1")

    assert "derecho laboral" in result.high_level
    assert "ET" in result.low_level
    assert "Juan García" in result.low_level
    assert len(result.embeddings) == 3


@pytest.mark.asyncio
async def test_extract_concepts_llm_failure_falls_back():
    """On LLM failure, falls back to regex extraction."""
    with patch(
        "app.agents.langgraph.tools.concept_extractor._call_llm",
        new_callable=AsyncMock,
        side_effect=Exception("LLM down"),
    ):
        result = await extract_concepts("contratos de María López", "tenant-1")

    # Should not raise — falls back to regex
    assert isinstance(result, ConceptResult)
    assert result.embeddings == {}  # No embeddings in fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/test_concept_extractor.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement concept_extractor.py**

```python
# backend/microservices/emma-agent-service/app/agents/langgraph/tools/concept_extractor.py
"""
Shared Concept Extraction — decomposes queries into high-level themes
and low-level entities for Graph RAG and SmartSearch.

Adopted from TrustGraph's extract_concepts pattern. Runs once per query,
results shared by both pipelines to avoid redundant LLM calls.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)

# Regex patterns for fallback entity extraction (from smart_search entity patterns)
_PERSON_RE = re.compile(
    r"\b(?:de|para|sobre|empleado|trabajador[a]?|sr\.?|sra\.?|don|doña|d\.)\s+"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3})",
)
_LEGAL_REF_RE = re.compile(
    r"\b(?:L(?:ey)?\.?\s*(?:Orgánica\s+)?|R\.?D\.?\s*|ET|LGT|LIRPF|LIS|LIVA|LSC|CC|LEC|LPRL|LGSS)"
    r"(?:\s+\d+/\d+)?",
    re.IGNORECASE,
)
_DOC_TYPE_RE = re.compile(
    r"\b(factura|contrato|nómina|nomina|informe|expediente|acta|presupuesto|certificado|escritura)\b",
    re.IGNORECASE,
)


@dataclass
class ConceptResult:
    """Extracted concepts from a query."""
    high_level: List[str] = field(default_factory=list)
    low_level: List[str] = field(default_factory=list)
    embeddings: Dict[str, List[float]] = field(default_factory=dict)


def _fallback_regex_concepts(query: str) -> ConceptResult:
    """Fast regex-based concept extraction as LLM fallback."""
    low_level: List[str] = []

    for m in _PERSON_RE.finditer(query):
        name = m.group(1).strip()
        if len(name) > 2:
            low_level.append(name)

    for m in _LEGAL_REF_RE.finditer(query):
        low_level.append(m.group(0).strip())

    for m in _DOC_TYPE_RE.finditer(query):
        low_level.append(m.group(1).strip().lower())

    # Deduplicate preserving order
    seen = set()
    deduped = []
    for c in low_level:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return ConceptResult(high_level=[], low_level=deduped, embeddings={})


async def _call_llm(query: str) -> object:
    """Call planner LLM for concept extraction."""
    from app.agents.llm_models import get_planner_model
    from app.services.langfuse_prompt_client import get_langfuse_prompt

    prompt_text = await get_langfuse_prompt("trustgraph_extract_concepts")
    formatted = prompt_text.replace("{query}", query)

    model = get_planner_model()
    return await model.ainvoke(formatted)


async def _batch_embed(concepts: List[str], tenant_id: str) -> Dict[str, List[float]]:
    """Batch embed all concepts via intelligence-docs-service."""
    if not concepts:
        return {}

    from app.clients.weaviate_client import get_weaviate_client

    client = get_weaviate_client()
    try:
        result = await client.post_json(
            "/embed-batch",
            json={"texts": concepts, "task": "retrieval.query"},
            headers=client._headers(),
        )
        vectors = result.get("embeddings", [])
        return {
            concept: vec
            for concept, vec in zip(concepts, vectors)
            if vec is not None
        }
    except Exception as e:
        logger.warning(f"Batch embedding failed: {e}")
        return {}


async def extract_concepts(query: str, tenant_id: str) -> ConceptResult:
    """Decompose query into high-level themes and low-level entities.

    LLM primary, regex fallback on failure. Embeddings computed for
    all concepts (shared by Graph RAG and SmartSearch).

    Args:
        query: User's natural language query.
        tenant_id: Tenant ID (for embedding cache scope).

    Returns:
        ConceptResult with high_level, low_level, and pre-computed embeddings.
    """
    # Try LLM extraction
    try:
        response = await _call_llm(query)
        content = response.content if hasattr(response, "content") else str(response)

        # Parse JSON from response
        # Handle markdown code blocks
        clean = content.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)

        parsed = json.loads(clean)
        high_level = parsed.get("high_level_keywords", [])
        low_level = parsed.get("low_level_keywords", [])

        if not isinstance(high_level, list) or not isinstance(low_level, list):
            raise ValueError("Invalid concept format")

    except Exception as e:
        logger.warning(f"LLM concept extraction failed, using regex fallback: {e}")
        return _fallback_regex_concepts(query)

    # Batch embed all concepts
    all_concepts = list(set(high_level + low_level))
    embeddings = await _batch_embed(all_concepts, tenant_id)

    return ConceptResult(
        high_level=high_level,
        low_level=low_level,
        embeddings=embeddings,
    )
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/test_concept_extractor.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/concept_extractor.py \
       backend/microservices/emma-agent-service/tests/test_concept_extractor.py
git commit -m "feat(trustgraph): shared concept extractor with LLM + regex fallback"
```

---

## Task 7: Graph RAG Tool (6-Stage Pipeline)

The main Graph RAG tool — entity retrieval → BFS → label resolution → semantic pre-filter → LLM edge scoring → context formatting.

**Files:**
- Create: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py`
- Create: `backend/microservices/emma-agent-service/tests/test_graph_rag.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/microservices/emma-agent-service/tests/test_graph_rag.py
"""Tests for GraphRAGTool — 6-stage pipeline."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass

from app.agents.langgraph.tools.graph_rag import (
    GraphRAGTool,
    GraphRAGResult,
    _build_edge_description,
    _resolve_labels_batch,
)


def test_build_edge_description():
    """Edge description format: 'subject, predicate, object'."""
    desc = _build_edge_description("LGT", "regula", "IRPF")
    assert desc == "LGT, regula, IRPF"


@pytest.mark.asyncio
async def test_graph_rag_disabled_returns_empty():
    """When graph_rag_enabled=False, tool returns empty result."""
    tool = GraphRAGTool()
    with patch("app.agents.langgraph.tools.graph_rag.settings") as mock_settings:
        mock_settings.graph_rag_enabled = False
        result = await tool.execute(
            {"query": "test"}, {"tenant_id": "t1"}
        )
    assert result.success is True
    assert "disabled" in result.output.lower() or result.output == ""


@pytest.mark.asyncio
async def test_graph_rag_no_entities_returns_empty():
    """When no entities found in vector search, return empty context."""
    tool = GraphRAGTool()

    mock_concepts = MagicMock()
    mock_concepts.low_level = ["something"]
    mock_concepts.high_level = []
    mock_concepts.embeddings = {"something": [0.1] * 1024}

    with patch("app.agents.langgraph.tools.graph_rag.settings") as mock_s, \
         patch("app.agents.langgraph.tools.graph_rag.extract_concepts", new_callable=AsyncMock, return_value=mock_concepts), \
         patch("app.agents.langgraph.tools.graph_rag._get_entities", new_callable=AsyncMock, return_value=[]):
        mock_s.graph_rag_enabled = True
        result = await tool.execute(
            {"query": "something"}, {"tenant_id": "t1"}
        )
    assert result.success is True
    assert "no entities" in result.output.lower() or "no relevant" in result.output.lower()


@pytest.mark.asyncio
async def test_graph_rag_full_pipeline():
    """Full pipeline with mocked stages returns formatted context."""
    tool = GraphRAGTool()

    mock_concepts = MagicMock()
    mock_concepts.low_level = ["LGT"]
    mock_concepts.high_level = ["fiscalidad"]
    mock_concepts.embeddings = {"LGT": [0.1] * 1024, "fiscalidad": [0.2] * 1024}

    mock_entities = [
        {"entity_uri": "nouxcube://entity/default/lgt", "label": "LGT", "definition": "Ley General Tributaria", "entity_type": "law", "score": 0.95},
    ]

    mock_subgraph = {
        "edges": [
            {"subject": "nouxcube://entity/default/lgt", "predicate": "nouxcube://predicate/legal/regula", "object": "nouxcube://entity/default/irpf", "object_type": "node"},
        ],
        "entities_visited": 2,
        "hops_used": 1,
    }

    mock_scored = [
        {"id": "nouxcube://entity/default/lgt@@nouxcube://predicate/legal/regula@@nouxcube://entity/default/irpf", "score": 9},
    ]

    with patch("app.agents.langgraph.tools.graph_rag.settings") as mock_s, \
         patch("app.agents.langgraph.tools.graph_rag.extract_concepts", new_callable=AsyncMock, return_value=mock_concepts), \
         patch("app.agents.langgraph.tools.graph_rag._get_entities", new_callable=AsyncMock, return_value=mock_entities), \
         patch("app.agents.langgraph.tools.graph_rag._get_subgraph", new_callable=AsyncMock, return_value=mock_subgraph), \
         patch("app.agents.langgraph.tools.graph_rag._resolve_labels_batch", new_callable=AsyncMock, return_value={"nouxcube://entity/default/lgt": "LGT", "nouxcube://entity/default/irpf": "IRPF"}), \
         patch("app.agents.langgraph.tools.graph_rag._score_edges_llm", new_callable=AsyncMock, return_value=mock_scored):
        mock_s.graph_rag_enabled = True
        mock_s.graph_rag_entity_limit = 50
        mock_s.graph_rag_max_hops = 2
        mock_s.graph_rag_max_edges = 150
        mock_s.graph_rag_edge_limit = 25
        mock_s.graph_rag_prefilter_limit = 30
        mock_s.graph_rag_label_cache_ttl = 300
        mock_s.retrieval_provenance_enabled = False

        result = await tool.execute(
            {"query": "qué regula la LGT"}, {"tenant_id": "t1"}
        )

    assert result.success is True
    assert "LGT" in result.output
    assert "IRPF" in result.output or "regula" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/test_graph_rag.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement graph_rag.py**

```python
# backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py
"""
Graph RAG Tool — TrustGraph knowledge graph retrieval pipeline.

6-stage pipeline:
  1. Entity retrieval (Weaviate vector search on TrustGraphEntities)
  2. BFS subgraph traversal (KTS /triples/neighbors)
  3. Label resolution (KTS /triples/query with caching)
  4. Semantic pre-filter (cosine similarity on edge descriptions)
  5. LLM edge scoring (Langfuse prompt)
  6. Context formatting (markdown for ReAct system prompt)

Replaces graph_expander.py (Phase 1).
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Type

import numpy as np
from cachetools import TTLCache
from pydantic import BaseModel, Field

from app.core.config import settings
from .base import EmmaTool, ToolResult
from .concept_extractor import extract_concepts, ConceptResult

logger = logging.getLogger(__name__)

# Label cache: {"{tenant_id}:{uri}": "label"}
_label_cache: TTLCache = TTLCache(maxsize=2000, ttl=settings.graph_rag_label_cache_ttl)


# ─── Data classes ────────────────────────────────────────────────────────────

class GraphRAGResult:
    """Structured result from Graph RAG pipeline."""
    def __init__(
        self,
        context_text: str,
        expanded_doc_ids: List[str],
        avg_score: float,
        entities: List[Dict[str, Any]],
    ):
        self.context_text = context_text
        self.expanded_doc_ids = expanded_doc_ids
        self.avg_score = avg_score
        self.entities = entities


# ─── Pipeline stages ─────────────────────────────────────────────────────────

async def _get_entities(
    concept_embeddings: Dict[str, List[float]],
    tenant_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Stage 1: Entity retrieval via Weaviate vector search."""
    from app.clients.weaviate_client import get_weaviate_client

    client = get_weaviate_client()
    if not concept_embeddings:
        return []

    per_concept_limit = max(1, limit // len(concept_embeddings))
    all_entities: Dict[str, Dict[str, Any]] = {}  # Dedup by entity_uri

    for concept, embedding in concept_embeddings.items():
        entities = await client.search_entities_by_embedding(
            embedding=embedding,
            tenant_id=tenant_id,
            limit=per_concept_limit,
        )
        for e in entities:
            uri = e.get("entity_uri", "")
            if uri not in all_entities or e.get("score", 0) > all_entities[uri].get("score", 0):
                all_entities[uri] = e

    # Sort by score descending, limit
    sorted_entities = sorted(all_entities.values(), key=lambda x: x.get("score", 0), reverse=True)
    return sorted_entities[:limit]


async def _get_subgraph(
    seed_uris: List[str],
    tenant_id: str,
    max_hops: int = 2,
    max_edges: int = 150,
) -> Dict[str, Any]:
    """Stage 2: BFS subgraph traversal via KTS."""
    from app.clients.knowledge_tree_client import get_knowledge_tree_client

    client = get_knowledge_tree_client()
    return await client.batch_neighbors(
        tenant_id=tenant_id,
        seed_uris=seed_uris,
        max_hops=max_hops,
        max_edges=max_edges,
        exclude_predicates=["prov/.*"],
    )


async def _resolve_labels_batch(
    uris: List[str],
    tenant_id: str,
) -> Dict[str, str]:
    """Stage 3: Resolve URIs to human-readable labels with caching."""
    from app.clients.knowledge_tree_client import get_knowledge_tree_client

    result: Dict[str, str] = {}
    to_fetch: List[str] = []

    for uri in uris:
        cache_key = f"{tenant_id}:{uri}"
        cached = _label_cache.get(cache_key)
        if cached is not None:
            result[uri] = cached
        else:
            to_fetch.append(uri)

    if to_fetch:
        client = get_knowledge_tree_client()
        for uri in to_fetch:
            try:
                resp = await client.query_triples(
                    tenant_id=tenant_id,
                    subject_uri=uri,
                    predicate_uri="nouxcube://predicate/core/label",
                    limit=1,
                )
                triples = resp.get("triples", [])
                if triples:
                    label = triples[0].get("object", uri)
                else:
                    # Fallback: URI last segment humanized
                    label = uri.rsplit("/", 1)[-1].replace("-", " ").title()

                result[uri] = label
                _label_cache[f"{tenant_id}:{uri}"] = label
            except Exception:
                label = uri.rsplit("/", 1)[-1].replace("-", " ").title()
                result[uri] = label

    return result


def _build_edge_description(subject_label: str, predicate: str, object_label: str) -> str:
    """Build textual description for embedding/scoring."""
    return f"{subject_label}, {predicate}, {object_label}"


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


async def _prefilter_edges(
    edges: List[Dict[str, Any]],
    labels: Dict[str, str],
    concept_embeddings: Dict[str, List[float]],
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Stage 4: Semantic pre-filter — keep most relevant edges by embedding similarity."""
    if not concept_embeddings or not edges:
        return edges[:limit]

    from app.clients.weaviate_client import get_weaviate_client

    # Build edge descriptions
    descriptions = []
    for edge in edges:
        subj = labels.get(edge.get("subject", ""), edge.get("subject", ""))
        pred = edge.get("predicate", "").rsplit("/", 1)[-1].replace("-", " ")
        obj = labels.get(edge.get("object", ""), edge.get("object", ""))
        descriptions.append(_build_edge_description(subj, pred, obj))

    # Batch embed descriptions
    client = get_weaviate_client()
    try:
        resp = await client.post_json(
            "/embed-batch",
            json={"texts": descriptions, "task": "retrieval.passage"},
            headers=client._headers(),
        )
        desc_embeddings = resp.get("embeddings", [])
    except Exception as e:
        logger.warning(f"Edge embedding failed, skipping pre-filter: {e}")
        return edges[:limit]

    if len(desc_embeddings) != len(edges):
        return edges[:limit]

    # Score each edge by max similarity to any concept
    concept_vecs = list(concept_embeddings.values())
    scored = []
    for i, (edge, desc_emb) in enumerate(zip(edges, desc_embeddings)):
        if desc_emb is None:
            continue
        max_sim = max(
            _cosine_similarity(desc_emb, cv) for cv in concept_vecs
        )
        scored.append((max_sim, i, edge))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [edge for _, _, edge in scored[:limit]]


async def _score_edges_llm(
    query: str,
    edges: List[Dict[str, Any]],
    labels: Dict[str, str],
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """Stage 5: LLM-based edge scoring."""
    from app.agents.llm_models import get_planner_model
    from app.services.langfuse_prompt_client import get_langfuse_prompt

    # Format edges for LLM
    edge_lines = []
    for i, edge in enumerate(edges):
        subj = labels.get(edge.get("subject", ""), edge.get("subject", ""))
        pred = edge.get("predicate", "").rsplit("/", 1)[-1].replace("-", " ")
        obj = labels.get(edge.get("object", ""), edge.get("object", ""))
        edge_id = f"{edge.get('subject', '')}@@{edge.get('predicate', '')}@@{edge.get('object', '')}"
        edge_lines.append(f"{edge_id} | {subj} → {pred} → {obj}")

    edges_json = "\n".join(edge_lines)

    prompt_text = await get_langfuse_prompt("trustgraph_edge_scoring")
    formatted = prompt_text.replace("{query}", query).replace("{edges_json}", edges_json)

    model = get_planner_model()
    response = await model.ainvoke(formatted)
    content = response.content if hasattr(response, "content") else str(response)

    # Parse response
    try:
        clean = content.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)

        scored = json.loads(clean)
        if not isinstance(scored, list):
            scored = []
    except (json.JSONDecodeError, ValueError):
        logger.warning("Edge scoring LLM returned invalid JSON, using pre-filter order")
        scored = [{"id": f"{e.get('subject','')}@@{e.get('predicate','')}@@{e.get('object','')}", "score": 5} for e in edges[:limit]]

    # Filter and sort by score
    scored = [s for s in scored if isinstance(s.get("score"), (int, float)) and s["score"] > 0]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def _format_graph_context(
    scored_edges: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    labels: Dict[str, str],
    entities: List[Dict[str, Any]],
) -> GraphRAGResult:
    """Stage 6: Format as markdown context for LLM."""
    # Build edge lookup by ID
    edge_lookup: Dict[str, Dict[str, Any]] = {}
    for edge in edges:
        edge_id = f"{edge.get('subject', '')}@@{edge.get('predicate', '')}@@{edge.get('object', '')}"
        edge_lookup[edge_id] = edge

    # Build entities section
    entity_lines = []
    for e in entities[:10]:
        entity_lines.append(json.dumps({
            "name": e.get("label", ""),
            "type": e.get("entity_type", ""),
            "definition": e.get("definition", ""),
        }, ensure_ascii=False))

    # Build relationships section
    rel_lines = []
    doc_ids: set[str] = set()
    total_score = 0.0
    for se in scored_edges:
        edge = edge_lookup.get(se["id"])
        if not edge:
            continue
        subj = labels.get(edge.get("subject", ""), "")
        pred = edge.get("predicate", "").rsplit("/", 1)[-1].replace("-", " ")
        obj = labels.get(edge.get("object", ""), "")
        score = se["score"] / 10.0  # Normalize 0-10 → 0-1

        rel_lines.append(json.dumps({
            "subject": subj,
            "predicate": pred,
            "object": obj,
            "score": round(score, 2),
        }, ensure_ascii=False))
        total_score += score

        # Collect source doc IDs from edge metadata
        source_chunk = edge.get("source_chunk", "")
        if source_chunk:
            doc_ids.add(source_chunk.split("#")[0] if "#" in source_chunk else source_chunk)

    avg_score = total_score / len(scored_edges) if scored_edges else 0.0

    context = "## Knowledge Graph Context\n\n"
    context += "### Entities\n"
    context += "\n".join(entity_lines) + "\n\n"
    context += "### Relationships\n"
    context += "\n".join(rel_lines) + "\n"

    return GraphRAGResult(
        context_text=context,
        expanded_doc_ids=list(doc_ids),
        avg_score=avg_score,
        entities=entities[:10],
    )


# ─── Tool definition ─────────────────────────────────────────────────────────

class GraphRAGInput(BaseModel):
    """Input for Graph RAG tool."""
    query: str = Field(
        description="Consulta en lenguaje natural. Usa esta herramienta cuando necesites "
        "relaciones entre entidades, patrones entre documentos, o referencias legales cruzadas."
    )


class GraphRAGTool(EmmaTool):
    """Graph RAG — entity relationships via knowledge graph traversal."""

    @property
    def name(self) -> str:
        return "graph_rag"

    @property
    def description(self) -> str:
        return (
            "Busca relaciones entre entidades en el grafo de conocimiento. "
            "Útil para: relaciones entre personas y documentos, referencias cruzadas entre leyes, "
            "patrones entre contratos, o cualquier consulta que requiera conexiones. "
            "Para buscar CONTENIDO de documentos, usa smart_search en su lugar."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return GraphRAGInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        if not settings.graph_rag_enabled:
            return ToolResult(output="", success=True)

        tenant_id = context.get("tenant_id", "")
        if not tenant_id:
            return ToolResult.from_error("No tenant_id in context")

        query = arguments["query"]
        t0 = time.monotonic()

        # Stage 0: Concept extraction (shared, may already be cached in context)
        concepts: Optional[ConceptResult] = context.get("_concepts")
        if concepts is None:
            concepts = await extract_concepts(query, tenant_id)

        all_embeddings = concepts.embeddings
        if not all_embeddings:
            return ToolResult(
                output="No relevant entities found in the knowledge graph for this query.",
                success=True,
            )

        # Stage 1: Entity retrieval
        entities = await _get_entities(
            all_embeddings, tenant_id,
            limit=settings.graph_rag_entity_limit,
        )
        if not entities:
            return ToolResult(
                output="No relevant entities found in the knowledge graph for this query.",
                success=True,
            )

        # Stage 2: BFS subgraph
        seed_uris = [e["entity_uri"] for e in entities[:20]]
        subgraph = await _get_subgraph(
            seed_uris, tenant_id,
            max_hops=settings.graph_rag_max_hops,
            max_edges=settings.graph_rag_max_edges,
        )
        edges = subgraph.get("edges", [])
        if not edges:
            return ToolResult(
                output="No relationships found in the knowledge graph for the matched entities.",
                success=True,
                data={"entities": entities[:5]},
            )

        # Stage 3: Label resolution
        all_uris = set()
        for edge in edges:
            all_uris.add(edge.get("subject", ""))
            if edge.get("object_type") == "node":
                all_uris.add(edge.get("object", ""))
        labels = await _resolve_labels_batch(list(all_uris), tenant_id)

        # Stage 4: Semantic pre-filter
        filtered_edges = await _prefilter_edges(
            edges, labels, all_embeddings,
            limit=settings.graph_rag_prefilter_limit,
        )

        # Stage 5: LLM edge scoring
        scored_edges = await _score_edges_llm(
            query, filtered_edges, labels,
            limit=settings.graph_rag_edge_limit,
        )

        # Stage 6: Format context
        result = _format_graph_context(scored_edges, edges, labels, entities)

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            f"Graph RAG: {len(entities)} entities, {len(edges)} edges, "
            f"{len(scored_edges)} scored, avg={result.avg_score:.2f}, {elapsed:.0f}ms"
        )

        return ToolResult(
            output=result.context_text,
            sources=[],
            data={
                "entities": result.entities,
                "expanded_doc_ids": result.expanded_doc_ids,
                "avg_score": result.avg_score,
            },
            success=True,
        )
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/test_graph_rag.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py \
       backend/microservices/emma-agent-service/tests/test_graph_rag.py
git commit -m "feat(trustgraph): Graph RAG tool — 6-stage pipeline"
```

---

## Task 8: Register Graph RAG Tool + Deprecate Graph Expander

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/graph_expander.py`

- [ ] **Step 1: Add GraphRAGTool to the registry**

In `backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py`, add the import inside `_ensure_initialized()`:

```python
        from .graph_rag import GraphRAGTool
```

And add to the tools list (after SmartSearchTool):

```python
            GraphRAGTool(),            # Graph RAG: entity relationships via knowledge graph
```

- [ ] **Step 2: Add deprecation notice to graph_expander.py**

At the top of `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/graph_expander.py`, add:

```python
"""
DEPRECATED: Sector-aware Graph Expander — replaced by graph_rag tool in Phase 2.

The graph_rag tool uses TrustGraph's full pipeline:
entity embeddings → BFS → LLM edge scoring → formatted context.

This module is kept for backward compatibility. SmartSearch's _extract_subgraph
still calls KnowledgeTreeClient.extract_subgraph which calls KTS's /tree/graph/subgraph
endpoint — that path is independent of this module.

Will be removed when SmartSearch fully migrates to multi-concept search (Task 9).
"""
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py \
       backend/microservices/emma-agent-service/app/agents/langgraph/sectors/graph_expander.py
git commit -m "feat(trustgraph): register graph_rag tool, deprecate graph_expander"
```

---

## Task 9: SmartSearch Multi-Concept + Continuous Graph Signal

Upgrade SmartSearch with multi-concept parallel search and continuous graph scoring.

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/smart_search.py`

- [ ] **Step 1: Add multi-concept search method to SmartSearchTool**

In `smart_search.py`, add after the `_extract_entities` method:

```python
    async def _multi_concept_search(
        self,
        concepts: List[str],
        concept_embeddings: Dict[str, List[float]],
        tenant_id: str,
        weaviate_client: Any,
        collection_name: str,
        person_filter: Optional[str],
        domain_filter: Optional[str],
        semantic_type_filter: Optional[str],
        folder_filter: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
        total_limit: int,
        user_id: Optional[str],
        user_role_ids: Optional[List[str]],
        is_admin: bool,
    ) -> List[Dict[str, Any]]:
        """Run independent hybrid search per concept, merge + dedup.

        Falls back to single-query search if concept_embeddings is empty.
        """
        if not concepts or not concept_embeddings:
            return []

        import asyncio as _asyncio

        per_concept_limit = max(3, total_limit // len(concepts))
        tasks = []
        for concept in concepts:
            embedding = concept_embeddings.get(concept)
            tasks.append(
                weaviate_client.hybrid_search(
                    tenant_id=tenant_id,
                    query=concept,
                    query_embedding=embedding,
                    collection_name=collection_name,
                    limit=per_concept_limit,
                    person_filter=person_filter,
                    domain_filter=domain_filter,
                    semantic_type_filter=semantic_type_filter,
                    folder_filter=folder_filter,
                    date_from=date_from,
                    date_to=date_to,
                    user_id=user_id,
                    user_role_ids=user_role_ids,
                    is_admin=is_admin,
                )
            )

        results = await _asyncio.gather(*tasks, return_exceptions=True)

        # Merge + dedup by document_id, keep highest score
        merged: Dict[str, Dict[str, Any]] = {}
        for result_list in results:
            if isinstance(result_list, Exception):
                logger.warning(f"Multi-concept search partial failure: {result_list}")
                continue
            if not isinstance(result_list, list):
                continue
            for doc in result_list:
                doc_id = doc.get("id") or doc.get("document_id", "")
                if doc_id not in merged or doc.get("score", 0) > merged[doc_id].get("score", 0):
                    merged[doc_id] = doc

        # Sort by score descending
        deduped = sorted(merged.values(), key=lambda d: d.get("score", 0), reverse=True)
        return deduped[:total_limit]
```

- [ ] **Step 2: Integrate multi-concept into the execute method**

In `SmartSearchTool.execute()`, after the entity extraction step (Step 1), add concept-based search logic. Find the section that calls `weaviate_client.hybrid_search` for document search and wrap it:

```python
        # ── Step 4b: Multi-concept search (Phase 2) ──
        concepts_result = context.get("_concepts")  # May be pre-computed
        if settings.smart_search_multi_concept and concepts_result and concepts_result.low_level:
            doc_results = await self._multi_concept_search(
                concepts=concepts_result.low_level,
                concept_embeddings=concepts_result.embeddings,
                tenant_id=tenant_id,
                weaviate_client=weaviate_client,
                collection_name=collection_name,
                person_filter=enriched_person,
                domain_filter=enriched_domain,
                semantic_type_filter=enriched_semantic_type,
                folder_filter=folder_filter,
                date_from=date_from,
                date_to=date_to,
                total_limit=limit,
                user_id=context.get("user_id"),
                user_role_ids=context.get("user_role_ids"),
                is_admin=context.get("is_admin", False),
            )
        else:
            # Fallback: original single-query hybrid search
            doc_results = await weaviate_client.hybrid_search(...)
```

The exact integration point depends on the current flow — the engineer should locate the existing `hybrid_search` call for documents and wrap it with this conditional.

- [ ] **Step 3: Upgrade graph signal from binary to continuous**

In the reranking section of `smart_search.py`, find where the `graph` signal is computed (binary 0/1) and update:

```python
        # Graph signal — continuous score from Graph RAG (Phase 2)
        graph_rag_data = context.get("_graph_rag_data")
        if graph_rag_data and graph_rag_data.get("expanded_doc_ids"):
            # Continuous: use avg_edge_score for docs from graph provenance
            graph_avg = graph_rag_data.get("avg_score", 0.5)
            graph_doc_set = set(graph_rag_data["expanded_doc_ids"])
            for doc in results:
                doc_id = doc.get("id", "")
                if doc_id in graph_doc_set:
                    doc["_graph_score"] = graph_avg
                elif doc_id in graph_doc_ids:
                    doc["_graph_score"] = 1.0  # Binary fallback from entity match
                else:
                    doc["_graph_score"] = 0.0
        else:
            # Binary fallback (backward compat)
            for doc in results:
                doc["_graph_score"] = 1.0 if doc.get("id", "") in graph_doc_ids else 0.0
```

- [ ] **Step 4: Run existing SmartSearch tests to check regressions**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/ -k "smart_search" -v`
Expected: Existing tests still pass (multi-concept is additive, fallback preserves old behavior)

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/smart_search.py
git commit -m "feat(trustgraph): SmartSearch multi-concept search + continuous graph signal"
```

---

## Task 10: Reindex Script — Entity Embedding Step

Add entity embedding population to the TrustGraph reindex pipeline.

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py`

- [ ] **Step 1: Add entity embedding function to reindex script**

After the main extraction loop in `reindex_trustgraph.py`, add:

```python
async def _populate_entity_embeddings(tenant_id: str, collection: str) -> int:
    """Query all :Node entities, embed, and upsert to Weaviate TrustGraphEntities."""
    import httpx

    weaviate_url = WEAVIATE_SERVICE_URL

    # 1. Query all entities with core/label + core/type + core/definition
    logger.info("Querying entities for embedding...")
    # Use the FalkorDB client directly (we're inside KTS)
    from app.services.falkordb_client import get_falkordb_client
    from app.services.triple_query import TripleQuery

    client = get_falkordb_client()
    tq = TripleQuery(client)

    # Get all unique subjects
    stats = await tq.stats(user=tenant_id, collection=collection)
    node_count = stats.get("node_count", 0)
    logger.info(f"Found {node_count} nodes to embed")

    if node_count == 0:
        return 0

    # Query all nodes with their labels, types, definitions
    query = (
        "MATCH (n:Node {user: $user}) "
        "OPTIONAL MATCH (n)-[r1:Rel {uri: 'nouxcube://predicate/core/label'}]->(l:Literal) "
        "OPTIONAL MATCH (n)-[r2:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal) "
        "OPTIONAL MATCH (n)-[r3:Rel {uri: 'nouxcube://predicate/core/definition'}]->(d:Literal) "
        "RETURN n.uri AS uri, l.value AS label, t.value AS type, d.value AS definition"
    )
    params = {"user": tenant_id}
    rows = await client.execute_cypher(query, params=params)

    if not rows:
        return 0

    # 2. Build embed texts
    entities = []
    embed_texts = []
    for row in rows:
        uri = row.get("uri", "")
        label = row.get("label") or uri.rsplit("/", 1)[-1].replace("-", " ").title()
        entity_type = row.get("type", "other")
        definition = row.get("definition", "")

        if definition:
            embed_text = f"{label} ({entity_type}). {definition}"
        else:
            embed_text = f"{label} ({entity_type})"

        entities.append({
            "entity_uri": uri,
            "label": label,
            "entity_type": entity_type,
            "definition": definition,
            "collection": collection,
        })
        embed_texts.append(embed_text)

    # 3. Batch embed via intelligence-docs-service
    logger.info(f"Embedding {len(embed_texts)} entities...")
    INTELLIGENCE_URL = os.getenv("INTELLIGENCE_DOCS_SERVICE_URL", "http://intelligence-docs-service:8012")
    async with httpx.AsyncClient(timeout=120) as http_client:
        # Embed in batches of 64
        all_embeddings = []
        batch_size = 64
        for i in range(0, len(embed_texts), batch_size):
            batch = embed_texts[i:i + batch_size]
            resp = await http_client.post(
                f"{INTELLIGENCE_URL}/embed",
                json={"texts": batch, "task": "retrieval.passage"},
                headers={"X-API-Key": MICROSERVICES_API_KEY},
            )
            resp.raise_for_status()
            all_embeddings.extend(resp.json().get("embeddings", []))

    # 4. Upsert to Weaviate TrustGraphEntities
    logger.info(f"Upserting {len(entities)} entities to Weaviate...")
    async with httpx.AsyncClient(timeout=120) as http_client:
        # Delete existing entities for this tenant first
        await http_client.delete(
            f"{weaviate_url}/entities/delete",
            params={"tenant_id": tenant_id},
            headers={"X-API-Key": MICROSERVICES_API_KEY},
        )

        # Batch upsert
        resp = await http_client.post(
            f"{weaviate_url}/entities/batch-upsert",
            json={
                "entities": entities,
                "embeddings": all_embeddings,
                "tenant_id": tenant_id,
            },
            headers={"X-API-Key": MICROSERVICES_API_KEY, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        count = resp.json().get("count", 0)

    logger.info(f"✓ Embedded and upserted {count} entities")
    return count
```

Then call it at the end of the main reindex flow:

```python
    # After triple extraction is complete:
    logger.info("── Phase 2: Entity Embeddings ──")
    embed_count = await _populate_entity_embeddings(tenant_id, collection)
    logger.info(f"Entity embeddings: {embed_count} entities")
```

**Note**: This also requires adding batch-upsert and delete endpoints in weaviate-service. Add these to `weaviate.py`:

```python
@router.post("/entities/batch-upsert")
async def batch_upsert_entities(request: dict, _: bool = Depends(verify_api_key)):
    """Batch upsert TrustGraph entities with embeddings."""
    service = get_weaviate_service()
    count = await service.upsert_trustgraph_entities_batch(
        entities=request["entities"],
        embeddings=request["embeddings"],
        tenant_id=request["tenant_id"],
    )
    return {"count": count}


@router.delete("/entities/delete")
async def delete_entities(tenant_id: str, _: bool = Depends(verify_api_key)):
    """Delete all TrustGraph entities for a tenant."""
    service = get_weaviate_service()
    count = await service.delete_trustgraph_entities(tenant_id)
    return {"deleted": count}
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py \
       backend/microservices/weaviate-service/app/api/weaviate.py
git commit -m "feat(trustgraph): entity embedding step in reindex pipeline"
```

---

## Task 11: Integration Sanity Checks

Add sanity checks to the diagnostics endpoint.

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/diagnostics.py`

- [ ] **Step 1: Add Graph RAG sanity checks**

Find the existing sanity checks list in `diagnostics.py` and add:

```python
    # ── TrustGraph Phase 2 ──
    async def _check_graph_rag_entity_retrieval():
        """Verify Weaviate TrustGraphEntities returns results."""
        from app.clients.weaviate_client import get_weaviate_client
        client = get_weaviate_client()
        results = await client.search_entities(
            query="test", tenant_id=tenant_id, limit=1,
        )
        return {"status": "ok" if isinstance(results, list) else "error"}

    async def _check_graph_rag_subgraph_traversal():
        """Verify KTS /triples/neighbors returns valid response."""
        from app.clients.knowledge_tree_client import get_knowledge_tree_client
        client = get_knowledge_tree_client()
        result = await client.batch_neighbors(
            tenant_id=tenant_id,
            seed_uris=["nouxcube://entity/default/test"],
            max_hops=1,
            max_edges=5,
        )
        has_keys = "edges" in result and "entities_visited" in result
        return {"status": "ok" if has_keys else "error"}
```

Register these in the sanity checks list with names `graph_rag_entity_retrieval` and `graph_rag_subgraph_traversal`.

- [ ] **Step 2: Run a quick smoke test**

Run: `cd backend/docker && docker compose exec emma-agent-service python -c "from app.agents.langgraph.tools.graph_rag import GraphRAGTool; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/api/diagnostics.py
git commit -m "feat(trustgraph): sanity checks for Graph RAG entity retrieval + BFS"
```

---

## Summary — Execution Order

| Task | Depends on | Est. Time |
|------|-----------|-----------|
| 1. KTS batch_neighbors | — | 15 min |
| 2. Weaviate TrustGraphEntities | — | 15 min |
| 3. Config settings | — | 5 min |
| 4. Langfuse prompts | — | 10 min |
| 5. Client methods | Tasks 1, 2 | 10 min |
| 6. Concept extractor | Task 4 | 15 min |
| 7. Graph RAG tool | Tasks 5, 6 | 25 min |
| 8. Tool registration | Task 7 | 5 min |
| 9. SmartSearch upgrade | Task 6 | 20 min |
| 10. Reindex embeddings | Tasks 2, 5 | 15 min |
| 11. Sanity checks | Tasks 7, 8 | 10 min |

**Parallelizable**: Tasks 1-4 can all run in parallel (independent). Tasks 5-6 can run in parallel after 1-4 complete. Tasks 7-9 are sequential.
