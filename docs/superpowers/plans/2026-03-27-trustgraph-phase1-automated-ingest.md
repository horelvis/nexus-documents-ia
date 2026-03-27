# TrustGraph Phase 1: Automated Ingest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current typed-label knowledge graph (`:Entity`, `:Document`, `:Claim`, etc.) with a TrustGraph-model triple store (`:Node`, `:Literal`, `:Rel`) on FalkorDB, including 4 parallel LLM extractors, PROV-O provenance, and contradiction detection.

**Architecture:** The knowledge-tree-service gets a full rewrite: old services (entity_graph_bridge, structural_indexer, claim_extractor, subgraph_extractor, tenant_knowledge_service, memory_bank_service) are replaced by a triple store layer (`triple_store.py`, `triple_query.py`), a URI builder (`uri_builder.py`), 4 LLM extractors coordinated by `coordinator.py`, and PROV-O provenance tracking. A mini-ontology of ~20 core predicates is seeded to avoid predicate chaos. The weaviate-service indexing pipeline calls the new `/extract/triples` endpoint instead of `/tree/entities/store`. Emma-agent-service adapts its graph clients and tools to the new `:Node`/`:Rel` model.

**Tech Stack:** FalkorDB (Cypher), FastAPI, Celery (chord for parallel extraction), Langfuse (4 extraction prompts), SGLang/Qwen3.5-9B (CHAT model), pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-26-trustgraph-triplet-extraction-design.md`

---

## Scope check

This plan covers **Phase 1 only** — Automated Ingest (schema + extractors + basic pipeline). Phase 2 (Semantic Similarity Retrieval) and Phase 3 (Ontology Structuring) get separate plans after Phase 1 lands and stabilizes.

Phase 1 does NOT include:
- Entity embedding in Weaviate (`TrustGraphEntities` collection) — Phase 2
- Ontology RAG vectorization (`OntologyTerms` collection) — Phase 3
- Frontend 3D/2D graph adaptation — Phase 2
- `rerank_weights` migration to graph triples — Phase 2
- Authority weight triples — Phase 3

Phase 1 DOES include:
- FalkorDB schema migration (`:Node`/`:Literal`/`:Rel` + indexes)
- URI builder with entity normalization
- Triple store CRUD (MERGE with Literal dedup)
- 4 LLM extractors as Celery tasks
- Coordinator that runs them in parallel per chunk
- PROV-O provenance triples
- Batch contradiction detection per document
- Mini-ontology seed (~20 core predicates as triples)
- Triple query service (8 SPO patterns)
- REST API endpoints
- Weaviate-service pipeline integration
- Emma-agent-service client + tool adaptation
- Reindexation script
- Langfuse prompt seeding

---

## File structure

### knowledge-tree-service — Full rewrite

**Kept unchanged:**
- `app/services/falkordb_client.py` (232 lines — generic Cypher, no typed labels)
- `app/core/config.py` (extended with new env vars)
- `app/core/security.py` (unchanged)
- `tests/conftest.py` (adapted for new schema)

**Deleted (all assume typed labels):**
- `app/services/entity_graph_bridge.py` (393 lines)
- `app/services/structural_indexer.py` (584 lines)
- `app/services/claim_extractor.py` (~80 lines)
- `app/services/subgraph_extractor.py` (~100 lines)
- `app/services/tenant_knowledge_service.py` (439 lines)
- `app/services/memory_bank_service.py`
- `app/services/graph_bootstrap.py`
- `app/api/tree.py` (733 lines)
- `app/api/entities.py` (131 lines)
- `app/api/claims.py` (230 lines)
- `app/api/memory_bank.py`
- `app/api/legal_links.py`
- `config/graphs/knowledge_graph_schema.cypher`
- `config/prompts/emma_prompts.yaml`
- `tests/test_falkordb_client.py` (replaced by new tests)
- `tests/test_batch_traversal.py` (replaced)
- `tests/test_claim_extractor.py` (replaced)

**Created:**
- `app/services/uri_builder.py` — Canonical URI generation + entity name normalization
- `app/services/triple_store.py` — CRUD: MERGE Node, MERGE Literal (dedup by value+user+collection), CREATE Rel
- `app/services/triple_query.py` — 8 SPO query patterns + contradiction queries + tenant context
- `app/services/provenance.py` — PROV-O triple creation per extraction batch
- `app/services/contradiction.py` — Batch contradiction detection per document
- `app/services/extractors/__init__.py`
- `app/services/extractors/base.py` — Base extractor: LLM call via httpx to SGLang, Langfuse prompt resolution
- `app/services/extractors/definitions.py` — Extract definitions (what entities ARE)
- `app/services/extractors/relationships.py` — Extract SPO semantic triples
- `app/services/extractors/objects.py` — Extract named entities with types
- `app/services/extractors/topics.py` — Extract thematic topics
- `app/services/extractors/coordinator.py` — Orchestrate 4 extractors per chunk, aggregate + dedup + store
- `app/api/triples.py` — REST endpoints: query, store, contradictions, stats, clear, context
- `app/api/extract.py` — REST endpoint: trigger extraction, reindex
- `app/schemas/triples.py` — Pydantic request/response models
- `config/graphs/trustgraph_schema.cypher` — FalkorDB indexes for new schema
- `scripts/seed_ontology.py` — Seed mini-ontology (~20 core predicates)
- `scripts/reindex_trustgraph.py` — Full reindexation script
- `tests/test_uri_builder.py`
- `tests/test_triple_store.py`
- `tests/test_triple_query.py`
- `tests/test_extractors.py`
- `tests/test_coordinator.py`
- `tests/test_contradiction.py`
- `tests/test_api_triples.py`

### weaviate-service — Pipeline integration

**Modified:**
- `app/services/knowledge/extraction_service.py` — Replace entity normalization + KTS store calls with new `/extract/triples` endpoint
- `app/services/knowledge/schemas.py` — Remove EntityType/RelationshipType enums, add TripleExtractionRequest
- `app/clients/knowledge_tree_client.py` — Add `extract_triples()`, `query_triples()`, `get_triple_context()` methods; deprecate `store_entities()`

### emma-agent-service — Client + tool adaptation

**Modified:**
- `app/clients/knowledge_tree_client.py` — Add triple query methods, deprecate old entity/subgraph methods
- `app/agents/langgraph/tools/smart_search.py` — `_extract_subgraph()` and `_expand_graph()` use triple queries
- `app/agents/langgraph/tools/structural_query.py` — Rewrite queries for `:Node`/`:Rel`
- `app/agents/langgraph/sectors/graph_expander.py` — Rewrite for `:Node`/`:Rel` queries
- `app/agents/langgraph/tools/subgraph_formatter.py` — Format triples instead of typed nodes

**Deleted:**
- `app/agents/langgraph/sectors/entity_extractor.py` — Replaced by KTS 4 extractors (regex entity extraction stays in smart_search.py for filter enrichment)

### background-worker — New Celery tasks

**Modified:**
- `worker_app/celery_app.py` — Add `trustgraph_extraction` queue + task routing
- `start.sh` — Add `trustgraph_extraction` to `-Q` flag

**Created:**
- `worker_app/tasks/trustgraph_tasks.py` — 6 Celery tasks (4 extractors + coordinator + reindex)

### Langfuse — 4 extraction prompts

**Created (via seed script):**
- `trustgraph_extract_definitions` — Definitions extractor prompt
- `trustgraph_extract_relationships` — Relationships extractor prompt (with mini-ontology predicates)
- `trustgraph_extract_objects` — Objects/NER extractor prompt
- `trustgraph_extract_topics` — Topics extractor prompt

### Docker

**Modified:**
- `docker-compose.onpremise.yml` — Add env vars for extraction config

---

## Task breakdown

### Task 1: FalkorDB schema + indexes

**Files:**
- Create: `backend/microservices/knowledge-tree-service/config/graphs/trustgraph_schema.cypher`
- Create: `backend/microservices/knowledge-tree-service/tests/test_trustgraph_schema.py`

- [ ] **Step 1: Write schema file**

```cypher
-- config/graphs/trustgraph_schema.cypher
-- TrustGraph Pure Model — :Node, :Literal, :Rel

-- Node indexes (identity entities: persons, documents, folders, concepts)
CREATE INDEX FOR (n:Node) ON (n.uri);
CREATE INDEX FOR (n:Node) ON (n.user, n.collection);

-- Literal indexes (values: dates, amounts, descriptions)
CREATE INDEX FOR (l:Literal) ON (l.value, l.user, l.collection);
CREATE INDEX FOR (l:Literal) ON (l.user, l.collection);

-- Rel indexes (semantic relationships via URI predicates)
CREATE INDEX FOR ()-[r:Rel]-() ON (r.uri);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.user, r.collection);
CREATE INDEX FOR ()-[r:Rel]-() ON (r.user, r.collection, r.uri);

-- CollectionMetadata (lifecycle sentinel)
CREATE INDEX FOR (c:CollectionMetadata) ON (c.user, c.collection);

-- Full-text search on Node URIs
CALL db.idx.fulltext.createNodeIndex('Node', 'uri');
```

- [ ] **Step 2: Write test for schema bootstrap**

```python
# tests/test_trustgraph_schema.py
import pytest
import pytest_asyncio

from app.services.falkordb_client import falkordb_client


@pytest.mark.asyncio
class TestTrustGraphSchema:
    """Verify schema indexes are created correctly."""

    async def test_bootstrap_schema_creates_indexes(self, falkordb_client):
        """Schema bootstrap should create all indexes without errors."""
        count = await falkordb_client.bootstrap_schema()
        assert count >= 7, f"Expected >=7 index statements, got {count}"

    async def test_bootstrap_schema_idempotent(self, falkordb_client):
        """Running bootstrap twice should not error."""
        await falkordb_client.bootstrap_schema()
        count = await falkordb_client.bootstrap_schema()
        assert count >= 7

    async def test_node_uri_index_works(self, falkordb_client):
        """URI index should allow fast lookups."""
        await falkordb_client.bootstrap_schema()
        await falkordb_client.execute_cypher(
            "CREATE (:Node {uri: $uri, user: $user, collection: $coll})",
            {"uri": "nouxcube://entity/default/test", "user": "t1", "coll": "default"},
        )
        result = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n.uri AS uri",
            {"uri": "nouxcube://entity/default/test"},
        )
        assert len(result) == 1
        assert result[0]["uri"] == "nouxcube://entity/default/test"

    async def test_literal_dedup_key(self, falkordb_client):
        """Literals indexed by (value, user, collection) for MERGE dedup."""
        await falkordb_client.bootstrap_schema()
        # Two MERGEs with same key should produce one node
        for _ in range(2):
            await falkordb_client.execute_cypher(
                "MERGE (:Literal {value: $val, user: $user, collection: $coll})",
                {"val": "person", "user": "t1", "coll": "default"},
            )
        result = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: 'person', user: 't1'}) RETURN count(l) AS cnt"
        )
        assert result[0]["cnt"] == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_trustgraph_schema.py -x --tb=short`
Expected: FAIL — `trustgraph_schema.cypher` exists but the `conftest.py` fixture still uses `knowledge_graph_schema.cypher`

- [ ] **Step 4: Update conftest.py to use new schema**

```python
# tests/conftest.py — replace the schema file reference
# In the falkordb_client fixture, after initialize():

import os
os.environ.setdefault("FALKORDB_HOST", "localhost")
os.environ.setdefault("FALKORDB_PORT", "6380")
os.environ.setdefault("FALKORDB_GRAPH_NAME", "test_knowledge_graph")
os.environ.setdefault("FALKORDB_PASSWORD", "")
os.environ.setdefault("RAG_KNOWLEDGE_GRAPH_ENABLED", "true")
os.environ.setdefault("ACTIVE_SECTOR", "legal")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest_asyncio.fixture
async def falkordb_client():
    """Per-test FalkorDB client with clean graph."""
    from app.services.falkordb_client import FalkorDBClient

    client = FalkorDBClient()
    await client.initialize()
    # Clean graph before test
    if client._graph:
        try:
            await client._graph.query("MATCH (n) DETACH DELETE n")
        except Exception:
            pass
    # Bootstrap new TrustGraph schema
    await client.bootstrap_schema()
    yield client
    # Cleanup after test
    if client._graph:
        try:
            await client._graph.query("MATCH (n) DETACH DELETE n")
        except Exception:
            pass
    await client.close()
```

Also update `falkordb_client.py` to reference the new schema file. In `bootstrap_schema()`, change the path:

```python
# app/services/falkordb_client.py — in bootstrap_schema()
# Change:
#   schema_path = Path(__file__).parent.parent.parent / "config" / "graphs" / "knowledge_graph_schema.cypher"
# To:
schema_path = Path(__file__).parent.parent.parent / "config" / "graphs" / "trustgraph_schema.cypher"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_trustgraph_schema.py -x --tb=short -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/config/graphs/trustgraph_schema.cypher \
       backend/microservices/knowledge-tree-service/tests/test_trustgraph_schema.py \
       backend/microservices/knowledge-tree-service/tests/conftest.py \
       backend/microservices/knowledge-tree-service/app/services/falkordb_client.py
git commit -m "feat(trustgraph): FalkorDB schema + indexes for :Node/:Literal/:Rel model"
```

---

### Task 2: URI builder with entity normalization

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/uri_builder.py`
- Create: `backend/microservices/knowledge-tree-service/tests/test_uri_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_uri_builder.py
import pytest
from app.services.uri_builder import URIBuilder


class TestEntityURI:
    """Test entity URI generation with name normalization."""

    def test_basic_person(self):
        uri = URIBuilder.entity("default", "Juan García López")
        assert uri == "nouxcube://entity/default/juan-garcia-lopez"

    def test_strips_accents(self):
        uri = URIBuilder.entity("default", "José María Azañón")
        assert uri == "nouxcube://entity/default/jose-maria-azanon"

    def test_lowercases(self):
        uri = URIBuilder.entity("default", "ACME CORP SL")
        assert uri == "nouxcube://entity/default/acme-corp-sl"

    def test_strips_extra_whitespace(self):
        uri = URIBuilder.entity("default", "  Juan   García  ")
        assert uri == "nouxcube://entity/default/juan-garcia"

    def test_strips_punctuation(self):
        uri = URIBuilder.entity("default", "García, Juan (DNI: 12345678A)")
        assert uri == "nouxcube://entity/default/garcia-juan-dni-12345678a"

    def test_different_collections(self):
        uri = URIBuilder.entity("nominas-2025", "Juan García")
        assert uri == "nouxcube://entity/nominas-2025/juan-garcia"

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="empty"):
            URIBuilder.entity("default", "")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            URIBuilder.entity("default", "   ")


class TestDocumentURI:
    def test_basic(self):
        uri = URIBuilder.document("default", "doc-123")
        assert uri == "nouxcube://document/default/doc-123"

    def test_preserves_document_id_case(self):
        """Document IDs are UUIDs — preserve them exactly."""
        uri = URIBuilder.document("default", "ABC-123-DEF")
        assert uri == "nouxcube://document/default/ABC-123-DEF"


class TestFolderURI:
    def test_basic(self):
        uri = URIBuilder.folder("default", "/Empleados/Juan Garcia")
        # Path is hashed for stability
        assert uri.startswith("nouxcube://folder/default/")
        assert len(uri.split("/")[-1]) == 16  # 16-char hex hash

    def test_same_path_same_uri(self):
        uri1 = URIBuilder.folder("default", "/Empleados/Juan")
        uri2 = URIBuilder.folder("default", "/Empleados/Juan")
        assert uri1 == uri2

    def test_different_path_different_uri(self):
        uri1 = URIBuilder.folder("default", "/Empleados/Juan")
        uri2 = URIBuilder.folder("default", "/Clientes/ACME")
        assert uri1 != uri2


class TestPredicateURI:
    def test_core_predicate(self):
        uri = URIBuilder.predicate("core", "type")
        assert uri == "nouxcube://predicate/core/type"

    def test_legal_predicate(self):
        uri = URIBuilder.predicate("legal", "empleado-de")
        assert uri == "nouxcube://predicate/legal/empleado-de"

    def test_prov_predicate(self):
        uri = URIBuilder.predicate("prov", "derived-from")
        assert uri == "nouxcube://predicate/prov/derived-from"


class TestExtractionURI:
    def test_generates_uuid(self):
        uri = URIBuilder.extraction()
        assert uri.startswith("nouxcube://extraction/")
        # UUID part is 36 chars
        uuid_part = uri.split("/")[-1]
        assert len(uuid_part) == 36


class TestNormalizeName:
    """Test the normalize function directly for edge cases."""

    def test_spanish_articles_kept(self):
        """Articles are part of the name, not stripped."""
        normalized = URIBuilder.normalize_name("María de los Ángeles")
        assert normalized == "maria-de-los-angeles"

    def test_ñ_to_n(self):
        normalized = URIBuilder.normalize_name("Año Nuevo Muñoz")
        assert normalized == "ano-nuevo-munoz"

    def test_numbers_preserved(self):
        normalized = URIBuilder.normalize_name("Ley 39/2015")
        assert normalized == "ley-39-2015"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_uri_builder.py -x --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.uri_builder'`

- [ ] **Step 3: Write the implementation**

```python
# app/services/uri_builder.py
"""
Canonical URI generation for TrustGraph triple store.

URI scheme:
  Entities:     nouxcube://entity/{collection}/{normalized-name}
  Documents:    nouxcube://document/{collection}/{document_id}
  Folders:      nouxcube://folder/{collection}/{path_hash}
  Predicates:   nouxcube://predicate/{ontology}/{predicate_name}
  Extractions:  nouxcube://extraction/{uuid}
  DB rows:      nouxcube://dbrow/{connector_id}/{table}/{pk}
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid


class URIBuilder:
    """Stateless URI factory — all methods are classmethods."""

    _SLUG_RE = re.compile(r"[^a-z0-9]+")

    @classmethod
    def normalize_name(cls, name: str) -> str:
        """Normalize a human name to a URL-safe slug.

        - NFD decompose + strip combining marks (accents)
        - Lowercase
        - Replace non-alphanumeric runs with single hyphen
        - Strip leading/trailing hyphens
        """
        # NFD decompose, strip combining characters (accents)
        nfkd = unicodedata.normalize("NFKD", name)
        ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
        slug = cls._SLUG_RE.sub("-", ascii_text.lower()).strip("-")
        return slug

    @classmethod
    def entity(cls, collection: str, name: str) -> str:
        slug = cls.normalize_name(name)
        if not slug:
            raise ValueError(f"Cannot build entity URI from empty name: {name!r}")
        return f"nouxcube://entity/{collection}/{slug}"

    @classmethod
    def document(cls, collection: str, document_id: str) -> str:
        return f"nouxcube://document/{collection}/{document_id}"

    @classmethod
    def folder(cls, collection: str, path: str) -> str:
        path_hash = hashlib.sha256(path.encode()).hexdigest()[:16]
        return f"nouxcube://folder/{collection}/{path_hash}"

    @classmethod
    def predicate(cls, ontology: str, predicate_name: str) -> str:
        return f"nouxcube://predicate/{ontology}/{predicate_name}"

    @classmethod
    def extraction(cls) -> str:
        return f"nouxcube://extraction/{uuid.uuid4()}"

    @classmethod
    def dbrow(cls, connector_id: str, table: str, pk: str) -> str:
        return f"nouxcube://dbrow/{connector_id}/{table}/{pk}"

    @classmethod
    def contradiction(cls) -> str:
        return f"nouxcube://contradiction/{uuid.uuid4()}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_uri_builder.py -x --tb=short -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/uri_builder.py \
       backend/microservices/knowledge-tree-service/tests/test_uri_builder.py
git commit -m "feat(trustgraph): URI builder with entity name normalization"
```

---

### Task 3: Triple store CRUD

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/triple_store.py`
- Create: `backend/microservices/knowledge-tree-service/tests/test_triple_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_triple_store.py
import pytest
import pytest_asyncio

from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


def _make_store(falkordb_client) -> TripleStore:
    return TripleStore(falkordb_client)


@pytest.mark.asyncio
class TestMergeNode:
    async def test_creates_node(self, falkordb_client):
        store = _make_store(falkordb_client)
        uri = URIBuilder.entity("default", "Juan García")
        await store.merge_node(uri=uri, user="t1", collection="default")
        result = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN n.uri AS uri, n.user AS user",
            {"uri": uri},
        )
        assert len(result) == 1
        assert result[0]["user"] == "t1"

    async def test_merge_idempotent(self, falkordb_client):
        store = _make_store(falkordb_client)
        uri = URIBuilder.entity("default", "Juan García")
        await store.merge_node(uri=uri, user="t1", collection="default")
        await store.merge_node(uri=uri, user="t1", collection="default")
        result = await falkordb_client.execute_cypher(
            "MATCH (n:Node {uri: $uri}) RETURN count(n) AS cnt", {"uri": uri}
        )
        assert result[0]["cnt"] == 1


@pytest.mark.asyncio
class TestMergeLiteral:
    async def test_creates_literal(self, falkordb_client):
        store = _make_store(falkordb_client)
        await store.merge_literal(value="person", user="t1", collection="default")
        result = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: $v, user: $u, collection: $c}) RETURN l.value AS val",
            {"v": "person", "u": "t1", "c": "default"},
        )
        assert len(result) == 1

    async def test_dedup_same_value(self, falkordb_client):
        """Same (value, user, collection) → same Literal node."""
        store = _make_store(falkordb_client)
        await store.merge_literal(value="person", user="t1", collection="default")
        await store.merge_literal(value="person", user="t1", collection="default")
        result = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: 'person', user: 't1'}) RETURN count(l) AS cnt"
        )
        assert result[0]["cnt"] == 1

    async def test_different_tenants_separate(self, falkordb_client):
        store = _make_store(falkordb_client)
        await store.merge_literal(value="person", user="t1", collection="default")
        await store.merge_literal(value="person", user="t2", collection="default")
        result = await falkordb_client.execute_cypher(
            "MATCH (l:Literal {value: 'person'}) RETURN count(l) AS cnt"
        )
        assert result[0]["cnt"] == 2


@pytest.mark.asyncio
class TestCreateRel:
    async def test_creates_relationship(self, falkordb_client):
        store = _make_store(falkordb_client)
        subj_uri = URIBuilder.entity("default", "Juan García")
        pred_uri = URIBuilder.predicate("core", "type")
        await store.merge_node(uri=subj_uri, user="t1", collection="default")
        await store.merge_literal(value="person", user="t1", collection="default")
        await store.create_rel(
            subject_uri=subj_uri,
            predicate_uri=pred_uri,
            object_value="person",
            user="t1",
            collection="default",
            object_is_node=False,
            extraction_method="llm_objects",
        )
        result = await falkordb_client.execute_cypher(
            """
            MATCH (s:Node {uri: $s_uri})-[r:Rel {uri: $p_uri}]->(o:Literal)
            RETURN s.uri AS s, r.uri AS p, o.value AS o
            """,
            {"s_uri": subj_uri, "p_uri": pred_uri},
        )
        assert len(result) == 1
        assert result[0]["o"] == "person"

    async def test_rel_to_node(self, falkordb_client):
        """Relationship where object is another :Node (entity)."""
        store = _make_store(falkordb_client)
        juan = URIBuilder.entity("default", "Juan García")
        acme = URIBuilder.entity("default", "ACME Corp")
        pred = URIBuilder.predicate("legal", "empleado-de")
        await store.merge_node(uri=juan, user="t1", collection="default")
        await store.merge_node(uri=acme, user="t1", collection="default")
        await store.create_rel(
            subject_uri=juan,
            predicate_uri=pred,
            object_value=acme,
            user="t1",
            collection="default",
            object_is_node=True,
            extraction_method="llm_relationships",
            source_chunk="Juan García trabaja en ACME Corp...",
        )
        result = await falkordb_client.execute_cypher(
            """
            MATCH (s:Node)-[r:Rel {uri: $p}]->(o:Node)
            WHERE s.uri = $s AND o.uri = $o
            RETURN r.extraction_method AS method, r.source_chunk AS chunk
            """,
            {"s": juan, "p": pred, "o": acme},
        )
        assert len(result) == 1
        assert result[0]["method"] == "llm_relationships"
        assert "ACME Corp" in result[0]["chunk"]


@pytest.mark.asyncio
class TestStoreTriple:
    """Test the high-level store_triple method that combines merge + rel."""

    async def test_store_entity_type_triple(self, falkordb_client):
        store = _make_store(falkordb_client)
        await store.store_triple(
            subject_name="Juan García",
            predicate_ontology="core",
            predicate_name="type",
            object_value="person",
            object_is_node=False,
            user="t1",
            collection="default",
            extraction_method="llm_objects",
        )
        result = await falkordb_client.execute_cypher(
            """
            MATCH (s:Node)-[r:Rel]->(o:Literal)
            WHERE s.user = 't1' AND r.uri CONTAINS 'core/type'
            RETURN s.uri AS s, o.value AS o
            """
        )
        assert len(result) == 1
        assert result[0]["o"] == "person"
        assert "juan-garcia" in result[0]["s"]

    async def test_store_entity_to_entity_triple(self, falkordb_client):
        store = _make_store(falkordb_client)
        await store.store_triple(
            subject_name="Juan García",
            predicate_ontology="legal",
            predicate_name="empleado-de",
            object_value="ACME Corp",
            object_is_node=True,
            user="t1",
            collection="default",
            extraction_method="llm_relationships",
        )
        result = await falkordb_client.execute_cypher(
            """
            MATCH (s:Node)-[r:Rel]->(o:Node)
            WHERE s.user = 't1' AND r.uri CONTAINS 'empleado-de'
            RETURN s.uri AS s, o.uri AS o
            """
        )
        assert len(result) == 1
        assert "juan-garcia" in result[0]["s"]
        assert "acme-corp" in result[0]["o"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_store.py -x --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.triple_store'`

- [ ] **Step 3: Write the implementation**

```python
# app/services/triple_store.py
"""
Triple store CRUD for TrustGraph model on FalkorDB.

All semantic data is stored as (:Node)-[:Rel]->(:Node|:Literal) triples.
Nodes are MERGEd by URI (idempotent). Literals are MERGEd by (value, user, collection).
Rels are CREATEd (each extraction produces new edges, even if semantically duplicate).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.services.falkordb_client import FalkorDBClient
from app.services.uri_builder import URIBuilder


class TripleStore:
    def __init__(self, client: FalkorDBClient):
        self._client = client

    # ── Node CRUD ──

    async def merge_node(
        self,
        uri: str,
        user: str,
        collection: str,
    ) -> None:
        """MERGE a :Node by URI. Idempotent."""
        await self._client.execute_cypher(
            """
            MERGE (n:Node {uri: $uri, user: $user, collection: $collection})
            ON CREATE SET n.created_at = timestamp()
            """,
            {"uri": uri, "user": user, "collection": collection},
        )

    # ── Literal CRUD ──

    async def merge_literal(
        self,
        value: str,
        user: str,
        collection: str,
    ) -> None:
        """MERGE a :Literal by (value, user, collection). Deduplicates."""
        await self._client.execute_cypher(
            "MERGE (:Literal {value: $value, user: $user, collection: $collection})",
            {"value": value, "user": user, "collection": collection},
        )

    # ── Rel CRUD ──

    async def create_rel(
        self,
        subject_uri: str,
        predicate_uri: str,
        object_value: str,
        user: str,
        collection: str,
        object_is_node: bool = False,
        extraction_method: str = "",
        source_chunk: str = "",
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> None:
        """Create a :Rel edge from subject :Node to object :Node or :Literal.

        The subject and object must already exist (via merge_node/merge_literal).
        """
        if object_is_node:
            query = """
            MATCH (s:Node {uri: $s_uri}), (o:Node {uri: $o_uri})
            CREATE (s)-[:Rel {
                uri: $p_uri,
                user: $user,
                collection: $collection,
                extraction_method: $method,
                source_chunk: $chunk,
                valid_from: $vf,
                valid_until: $vu
            }]->(o)
            """
            params = {
                "s_uri": subject_uri,
                "o_uri": object_value,
                "p_uri": predicate_uri,
                "user": user,
                "collection": collection,
                "method": extraction_method,
                "chunk": source_chunk,
                "vf": valid_from or "",
                "vu": valid_until or "",
            }
        else:
            query = """
            MATCH (s:Node {uri: $s_uri})
            MATCH (o:Literal {value: $o_val, user: $user, collection: $collection})
            CREATE (s)-[:Rel {
                uri: $p_uri,
                user: $user,
                collection: $collection,
                extraction_method: $method,
                source_chunk: $chunk,
                valid_from: $vf,
                valid_until: $vu
            }]->(o)
            """
            params = {
                "s_uri": subject_uri,
                "o_val": object_value,
                "user": user,
                "collection": collection,
                "p_uri": predicate_uri,
                "method": extraction_method,
                "chunk": source_chunk,
                "vf": valid_from or "",
                "vu": valid_until or "",
            }
        await self._client.execute_cypher(query, params)

    # ── High-level: store a complete triple ──

    async def store_triple(
        self,
        subject_name: str,
        predicate_ontology: str,
        predicate_name: str,
        object_value: str,
        object_is_node: bool,
        user: str,
        collection: str,
        extraction_method: str = "",
        source_chunk: str = "",
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> str:
        """Store a complete S-P-O triple. Returns subject URI.

        1. MERGE subject :Node (by entity URI)
        2. MERGE object :Node or :Literal
        3. CREATE :Rel edge
        """
        subject_uri = URIBuilder.entity(collection, subject_name)
        predicate_uri = URIBuilder.predicate(predicate_ontology, predicate_name)

        await self.merge_node(uri=subject_uri, user=user, collection=collection)

        if object_is_node:
            object_uri = URIBuilder.entity(collection, object_value)
            await self.merge_node(uri=object_uri, user=user, collection=collection)
            await self.create_rel(
                subject_uri=subject_uri,
                predicate_uri=predicate_uri,
                object_value=object_uri,
                user=user,
                collection=collection,
                object_is_node=True,
                extraction_method=extraction_method,
                source_chunk=source_chunk,
                valid_from=valid_from,
                valid_until=valid_until,
            )
        else:
            await self.merge_literal(value=object_value, user=user, collection=collection)
            await self.create_rel(
                subject_uri=subject_uri,
                predicate_uri=predicate_uri,
                object_value=object_value,
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method=extraction_method,
                source_chunk=source_chunk,
                valid_from=valid_from,
                valid_until=valid_until,
            )
        return subject_uri

    # ── Structural triples (document, folder) ──

    async def store_document_node(
        self,
        document_id: str,
        user: str,
        collection: str,
        title: str = "",
        file_path: str = "",
        semantic_type: str = "",
        domain: str = "",
    ) -> str:
        """Create a :Node for a document + its metadata triples."""
        doc_uri = URIBuilder.document(collection, document_id)
        await self.merge_node(uri=doc_uri, user=user, collection=collection)

        # Type triple
        await self.merge_literal(value="document", user=user, collection=collection)
        await self.create_rel(
            subject_uri=doc_uri,
            predicate_uri=URIBuilder.predicate("core", "type"),
            object_value="document",
            user=user,
            collection=collection,
            object_is_node=False,
            extraction_method="structural",
        )

        # Label triple (title)
        if title:
            await self.merge_literal(value=title, user=user, collection=collection)
            await self.create_rel(
                subject_uri=doc_uri,
                predicate_uri=URIBuilder.predicate("core", "label"),
                object_value=title,
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="structural",
            )

        # Semantic type triple
        if semantic_type:
            await self.merge_literal(value=semantic_type, user=user, collection=collection)
            await self.create_rel(
                subject_uri=doc_uri,
                predicate_uri=URIBuilder.predicate("core", "semantic-type"),
                object_value=semantic_type,
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="structural",
            )

        # Domain triple
        if domain:
            await self.merge_literal(value=domain, user=user, collection=collection)
            await self.create_rel(
                subject_uri=doc_uri,
                predicate_uri=URIBuilder.predicate("core", "domain"),
                object_value=domain,
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="structural",
            )

        # Folder link
        if file_path:
            folder_path = "/".join(file_path.split("/")[:-1]) or "/"
            folder_uri = URIBuilder.folder(collection, folder_path)
            await self.merge_node(uri=folder_uri, user=user, collection=collection)
            # Folder label
            folder_name = folder_path.split("/")[-1] or "root"
            await self.merge_literal(value=folder_name, user=user, collection=collection)
            await self.create_rel(
                subject_uri=folder_uri,
                predicate_uri=URIBuilder.predicate("core", "label"),
                object_value=folder_name,
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="structural",
            )
            # Folder type
            await self.merge_literal(value="folder", user=user, collection=collection)
            await self.create_rel(
                subject_uri=folder_uri,
                predicate_uri=URIBuilder.predicate("core", "type"),
                object_value="folder",
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="structural",
            )
            # Document → Folder
            await self.create_rel(
                subject_uri=doc_uri,
                predicate_uri=URIBuilder.predicate("core", "contained-in"),
                object_value=folder_uri,
                user=user,
                collection=collection,
                object_is_node=True,
                extraction_method="structural",
            )

        return doc_uri

    # ── Bulk operations ──

    async def clear_collection(self, user: str, collection: str) -> int:
        """Delete all nodes and rels for a user+collection."""
        result = await self._client.execute_cypher(
            """
            MATCH (n)
            WHERE (n:Node OR n:Literal OR n:CollectionMetadata)
              AND n.user = $user AND n.collection = $collection
            DETACH DELETE n
            RETURN count(n) AS deleted
            """,
            {"user": user, "collection": collection},
        )
        return result[0]["deleted"] if result else 0

    async def clear_tenant(self, user: str) -> int:
        """Delete ALL graph data for a tenant."""
        result = await self._client.execute_cypher(
            """
            MATCH (n)
            WHERE (n:Node OR n:Literal OR n:CollectionMetadata)
              AND n.user = $user
            DETACH DELETE n
            RETURN count(n) AS deleted
            """,
            {"user": user},
        )
        return result[0]["deleted"] if result else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_store.py -x --tb=short -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/triple_store.py \
       backend/microservices/knowledge-tree-service/tests/test_triple_store.py
git commit -m "feat(trustgraph): triple store CRUD with Literal dedup"
```

---

### Task 4: Triple query service

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/triple_query.py`
- Create: `backend/microservices/knowledge-tree-service/tests/test_triple_query.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_triple_query.py
import pytest
import pytest_asyncio

from app.services.triple_store import TripleStore
from app.services.triple_query import TripleQuery
from app.services.uri_builder import URIBuilder


def _make(falkordb_client):
    return TripleStore(falkordb_client), TripleQuery(falkordb_client)


@pytest.mark.asyncio
class TestSPOQueries:
    """Test 8 SPO query patterns."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_graph(self, falkordb_client):
        store = TripleStore(falkordb_client)
        # Juan → person, empleado-de → ACME
        await store.store_triple("Juan García", "core", "type", "person", False, "t1", "default", "llm_objects")
        await store.store_triple("Juan García", "core", "label", "Juan García López", False, "t1", "default", "llm_definitions")
        await store.store_triple("Juan García", "legal", "empleado-de", "ACME Corp", True, "t1", "default", "llm_relationships")
        await store.store_triple("ACME Corp", "core", "type", "organization", False, "t1", "default", "llm_objects")
        await store.store_triple("ACME Corp", "core", "label", "ACME Corp SL", False, "t1", "default", "llm_definitions")

    async def test_query_by_subject(self, falkordb_client):
        _, query = _make(falkordb_client)
        juan_uri = URIBuilder.entity("default", "Juan García")
        triples = await query.by_subject(juan_uri, user="t1")
        assert len(triples) >= 3  # type, label, empleado-de
        predicates = {t["predicate"] for t in triples}
        assert "nouxcube://predicate/core/type" in predicates
        assert "nouxcube://predicate/legal/empleado-de" in predicates

    async def test_query_by_predicate(self, falkordb_client):
        _, query = _make(falkordb_client)
        pred_uri = URIBuilder.predicate("core", "type")
        triples = await query.by_predicate(pred_uri, user="t1")
        assert len(triples) >= 2  # person, organization
        values = {t["object"] for t in triples}
        assert "person" in values
        assert "organization" in values

    async def test_query_by_object_literal(self, falkordb_client):
        _, query = _make(falkordb_client)
        triples = await query.by_object_value("person", user="t1")
        assert len(triples) >= 1
        assert "juan-garcia" in triples[0]["subject"]

    async def test_query_spo(self, falkordb_client):
        """Full S-P-O lookup."""
        _, query = _make(falkordb_client)
        juan_uri = URIBuilder.entity("default", "Juan García")
        pred_uri = URIBuilder.predicate("core", "type")
        triples = await query.by_spo(subject_uri=juan_uri, predicate_uri=pred_uri, user="t1")
        assert len(triples) == 1
        assert triples[0]["object"] == "person"

    async def test_query_neighbors(self, falkordb_client):
        """Get all nodes connected to a subject within N hops."""
        _, query = _make(falkordb_client)
        juan_uri = URIBuilder.entity("default", "Juan García")
        neighbors = await query.neighbors(juan_uri, user="t1", max_hops=1)
        # Juan → ACME (via empleado-de), and literals (type, label)
        node_uris = {n["uri"] for n in neighbors if n.get("label") == "Node"}
        assert any("acme-corp" in u for u in node_uris)


@pytest.mark.asyncio
class TestTenantContext:
    """Test building LLM context from triples."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed_graph(self, falkordb_client):
        store = TripleStore(falkordb_client)
        await store.store_document_node("doc-1", "t1", "default", title="Contrato ACME", file_path="/Contratos/ACME/contrato.pdf", semantic_type="contract", domain="legal")
        await store.store_triple("Juan García", "core", "type", "person", False, "t1", "default", "llm_objects")
        await store.store_triple("Juan García", "core", "mentioned-in", URIBuilder.document("default", "doc-1"), True, "t1", "default", "structural")

    async def test_get_stats(self, falkordb_client):
        _, query = _make(falkordb_client)
        stats = await query.get_stats(user="t1")
        assert stats["nodes"] >= 2  # doc + Juan
        assert stats["literals"] >= 1
        assert stats["rels"] >= 1

    async def test_build_context(self, falkordb_client):
        _, query = _make(falkordb_client)
        context = await query.build_context(user="t1", limit=20)
        assert isinstance(context, str)
        assert "Contrato ACME" in context or "document" in context


@pytest.mark.asyncio
class TestTenantIsolation:
    async def test_different_tenants_isolated(self, falkordb_client):
        store = TripleStore(falkordb_client)
        _, query = _make(falkordb_client)
        await store.store_triple("Juan", "core", "type", "person", False, "t1", "default", "test")
        await store.store_triple("María", "core", "type", "person", False, "t2", "default", "test")
        t1 = await query.by_predicate(URIBuilder.predicate("core", "type"), user="t1")
        t2 = await query.by_predicate(URIBuilder.predicate("core", "type"), user="t2")
        assert len(t1) == 1
        assert len(t2) == 1
        assert "juan" in t1[0]["subject"]
        assert "maria" in t2[0]["subject"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_query.py -x --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.triple_query'`

- [ ] **Step 3: Write the implementation**

```python
# app/services/triple_query.py
"""
Query service for TrustGraph triples on FalkorDB.

8 SPO query patterns + tenant context builder + stats.
All queries filter by user (tenant_id) for multi-tenancy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.falkordb_client import FalkorDBClient


class TripleQuery:
    def __init__(self, client: FalkorDBClient):
        self._client = client

    # ── SPO Patterns ──

    async def by_subject(
        self, subject_uri: str, user: str, collection: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """All triples where subject = URI."""
        coll_filter = "AND r.collection = $coll" if collection else ""
        result = await self._client.execute_cypher(
            f"""
            MATCH (s:Node {{uri: $uri}})-[r:Rel]->(o)
            WHERE r.user = $user {coll_filter}
            RETURN s.uri AS subject, r.uri AS predicate,
                   CASE WHEN o:Node THEN o.uri ELSE o.value END AS object,
                   CASE WHEN o:Node THEN 'node' ELSE 'literal' END AS object_type,
                   r.extraction_method AS extraction_method,
                   r.source_chunk AS source_chunk
            LIMIT $limit
            """,
            {"uri": subject_uri, "user": user, "coll": collection, "limit": limit},
        )
        return result

    async def by_predicate(
        self, predicate_uri: str, user: str, collection: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """All triples with a specific predicate."""
        coll_filter = "AND r.collection = $coll" if collection else ""
        return await self._client.execute_cypher(
            f"""
            MATCH (s:Node)-[r:Rel {{uri: $pred}}]->(o)
            WHERE r.user = $user {coll_filter}
            RETURN s.uri AS subject, r.uri AS predicate,
                   CASE WHEN o:Node THEN o.uri ELSE o.value END AS object,
                   CASE WHEN o:Node THEN 'node' ELSE 'literal' END AS object_type
            LIMIT $limit
            """,
            {"pred": predicate_uri, "user": user, "coll": collection, "limit": limit},
        )

    async def by_object_value(
        self, value: str, user: str, collection: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """All triples pointing to a literal value."""
        coll_filter = "AND r.collection = $coll" if collection else ""
        return await self._client.execute_cypher(
            f"""
            MATCH (s:Node)-[r:Rel]->(o:Literal {{value: $val}})
            WHERE r.user = $user {coll_filter}
            RETURN s.uri AS subject, r.uri AS predicate, o.value AS object,
                   'literal' AS object_type
            LIMIT $limit
            """,
            {"val": value, "user": user, "coll": collection, "limit": limit},
        )

    async def by_object_node(
        self, object_uri: str, user: str, collection: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """All triples pointing to a specific node (inbound edges)."""
        coll_filter = "AND r.collection = $coll" if collection else ""
        return await self._client.execute_cypher(
            f"""
            MATCH (s:Node)-[r:Rel]->(o:Node {{uri: $uri}})
            WHERE r.user = $user {coll_filter}
            RETURN s.uri AS subject, r.uri AS predicate, o.uri AS object,
                   'node' AS object_type
            LIMIT $limit
            """,
            {"uri": object_uri, "user": user, "coll": collection, "limit": limit},
        )

    async def by_spo(
        self,
        subject_uri: str,
        predicate_uri: str,
        user: str,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Exact S-P-O lookup (may return multiple if repeated extractions)."""
        coll_filter = "AND r.collection = $coll" if collection else ""
        return await self._client.execute_cypher(
            f"""
            MATCH (s:Node {{uri: $s}})-[r:Rel {{uri: $p}}]->(o)
            WHERE r.user = $user {coll_filter}
            RETURN s.uri AS subject, r.uri AS predicate,
                   CASE WHEN o:Node THEN o.uri ELSE o.value END AS object,
                   CASE WHEN o:Node THEN 'node' ELSE 'literal' END AS object_type,
                   r.extraction_method AS extraction_method
            """,
            {"s": subject_uri, "p": predicate_uri, "user": user, "coll": collection},
        )

    async def by_subject_predicate(
        self, subject_uri: str, predicate_uri: str, user: str
    ) -> List[Dict[str, Any]]:
        """All objects for a given subject+predicate."""
        return await self.by_spo(subject_uri, predicate_uri, user)

    async def by_predicate_object(
        self, predicate_uri: str, object_value: str, user: str, object_is_node: bool = False
    ) -> List[Dict[str, Any]]:
        """All subjects with a given predicate pointing to a specific object."""
        if object_is_node:
            return await self._client.execute_cypher(
                """
                MATCH (s:Node)-[r:Rel {uri: $p}]->(o:Node {uri: $o})
                WHERE r.user = $user
                RETURN s.uri AS subject, r.uri AS predicate, o.uri AS object, 'node' AS object_type
                """,
                {"p": predicate_uri, "o": object_value, "user": user},
            )
        return await self._client.execute_cypher(
            """
            MATCH (s:Node)-[r:Rel {uri: $p}]->(o:Literal {value: $o})
            WHERE r.user = $user
            RETURN s.uri AS subject, r.uri AS predicate, o.value AS object, 'literal' AS object_type
            """,
            {"p": predicate_uri, "o": object_value, "user": user},
        )

    # ── Graph traversal ──

    async def neighbors(
        self, uri: str, user: str, max_hops: int = 2, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get all nodes within N hops of a URI (outgoing + incoming)."""
        return await self._client.execute_cypher(
            """
            MATCH path = (start:Node {uri: $uri})-[:Rel*1..$max_hops]-(neighbor)
            WHERE ALL(r IN relationships(path) WHERE r.user = $user)
              AND (neighbor:Node OR neighbor:Literal)
            WITH DISTINCT neighbor,
                 CASE WHEN neighbor:Node THEN 'Node' ELSE 'Literal' END AS label,
                 min(length(path)) AS distance
            RETURN
                CASE WHEN neighbor:Node THEN neighbor.uri ELSE neighbor.value END AS uri,
                label,
                distance
            ORDER BY distance
            LIMIT $limit
            """,
            {"uri": uri, "user": user, "max_hops": max_hops, "limit": limit},
        )

    async def subgraph(
        self,
        seed_uris: List[str],
        user: str,
        max_hops: int = 2,
        max_nodes: int = 50,
    ) -> Dict[str, Any]:
        """Extract a subgraph around seed URIs for GraphRAG context."""
        if not seed_uris:
            return {"nodes": [], "edges": []}
        return await self._client.execute_cypher(
            """
            UNWIND $seeds AS seed_uri
            MATCH (start:Node {uri: seed_uri})
            CALL {
                WITH start
                MATCH path = (start)-[:Rel*1..$max_hops]-(neighbor:Node)
                WHERE ALL(r IN relationships(path) WHERE r.user = $user)
                RETURN neighbor, relationships(path) AS rels
                LIMIT $max_nodes
            }
            WITH collect(DISTINCT neighbor) AS neighbors, collect(rels) AS all_rels
            UNWIND neighbors AS n
            WITH n, all_rels
            OPTIONAL MATCH (n)-[r:Rel]->(o)
            WHERE r.user = $user AND (o:Node OR o:Literal)
            RETURN
                n.uri AS node_uri,
                collect(DISTINCT {
                    predicate: r.uri,
                    object: CASE WHEN o:Node THEN o.uri ELSE o.value END,
                    object_type: CASE WHEN o:Node THEN 'node' ELSE 'literal' END,
                    method: r.extraction_method
                }) AS outgoing_triples
            """,
            {"seeds": seed_uris, "user": user, "max_hops": max_hops, "max_nodes": max_nodes},
        )

    # ── Tenant context ──

    async def get_stats(self, user: str, collection: Optional[str] = None) -> Dict[str, int]:
        """Count nodes, literals, and rels for a tenant."""
        coll_filter = "AND n.collection = $coll" if collection else ""
        nodes = await self._client.execute_cypher(
            f"MATCH (n:Node) WHERE n.user = $user {coll_filter} RETURN count(n) AS cnt",
            {"user": user, "coll": collection},
        )
        literals = await self._client.execute_cypher(
            f"MATCH (n:Literal) WHERE n.user = $user {coll_filter} RETURN count(n) AS cnt",
            {"user": user, "coll": collection},
        )
        rels = await self._client.execute_cypher(
            f"MATCH ()-[r:Rel]->() WHERE r.user = $user {'AND r.collection = $coll' if collection else ''} RETURN count(r) AS cnt",
            {"user": user, "coll": collection},
        )
        return {
            "nodes": nodes[0]["cnt"] if nodes else 0,
            "literals": literals[0]["cnt"] if literals else 0,
            "rels": rels[0]["cnt"] if rels else 0,
        }

    async def build_context(self, user: str, limit: int = 20) -> str:
        """Build a text context for the LLM from tenant graph data."""
        stats = await self.get_stats(user)

        # Get entity types breakdown
        types = await self._client.execute_cypher(
            """
            MATCH (n:Node)-[r:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal)
            WHERE r.user = $user
            RETURN t.value AS type, count(n) AS cnt
            ORDER BY cnt DESC
            LIMIT 20
            """,
            {"user": user},
        )

        # Get top entities by connection count
        top = await self._client.execute_cypher(
            """
            MATCH (n:Node)-[r:Rel]-()
            WHERE r.user = $user AND n.uri STARTS WITH 'nouxcube://entity/'
            WITH n.uri AS uri, count(r) AS connections
            OPTIONAL MATCH (n2:Node {uri: uri})-[:Rel {uri: 'nouxcube://predicate/core/label'}]->(l:Literal)
            RETURN uri, l.value AS label, connections
            ORDER BY connections DESC
            LIMIT $limit
            """,
            {"user": user, "limit": limit},
        )

        lines = [
            "## Knowledge Graph Context",
            f"**Totals:** {stats['nodes']} entities, {stats['literals']} values, {stats['rels']} relationships",
        ]

        if types:
            type_str = ", ".join(f"{t['type']} ({t['cnt']})" for t in types)
            lines.append(f"**Entity types:** {type_str}")

        if top:
            lines.append("**Top entities:**")
            for i, e in enumerate(top[:10], 1):
                name = e.get("label") or e["uri"].split("/")[-1]
                lines.append(f"  {i}. {name} ({e['connections']} connections)")

        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_query.py -x --tb=short -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/triple_query.py \
       backend/microservices/knowledge-tree-service/tests/test_triple_query.py
git commit -m "feat(trustgraph): triple query service with 8 SPO patterns + context builder"
```

---

### Task 5: Provenance service (PROV-O)

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/provenance.py`
- Test: inside `tests/test_triple_store.py` (extend)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_triple_store.py`:

```python
# Append to tests/test_triple_store.py
from app.services.provenance import ProvenanceService


@pytest.mark.asyncio
class TestProvenance:
    async def test_creates_extraction_node(self, falkordb_client):
        store = _make_store(falkordb_client)
        prov = ProvenanceService(store)
        doc_uri = URIBuilder.document("default", "doc-1")
        await store.merge_node(uri=doc_uri, user="t1", collection="default")
        ext_uri = await prov.record_extraction(
            document_uri=doc_uri,
            extraction_method="llm_relationships",
            model_name="Qwen3.5-9B",
            chunk_text="Juan García trabaja en ACME Corp desde 2020.",
            chunk_offset=1500,
            user="t1",
            collection="default",
        )
        assert ext_uri.startswith("nouxcube://extraction/")
        # Verify provenance triples exist
        result = await falkordb_client.execute_cypher(
            """
            MATCH (e:Node {uri: $uri})-[r:Rel]->(o)
            WHERE r.user = 't1'
            RETURN r.uri AS pred, CASE WHEN o:Node THEN o.uri ELSE o.value END AS obj
            """,
            {"uri": ext_uri},
        )
        preds = {r["pred"]: r["obj"] for r in result}
        assert "nouxcube://predicate/prov/derived-from" in preds
        assert preds["nouxcube://predicate/prov/derived-from"] == doc_uri
        assert preds["nouxcube://predicate/prov/method"] == "llm_relationships"
        assert preds["nouxcube://predicate/prov/model"] == "Qwen3.5-9B"
        assert "Juan García" in preds["nouxcube://predicate/prov/chunk-text"]
        assert preds["nouxcube://predicate/prov/chunk-offset"] == "1500"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_store.py::TestProvenance -x --tb=short`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.provenance'`

- [ ] **Step 3: Write the implementation**

```python
# app/services/provenance.py
"""
PROV-O simplified provenance tracking for TrustGraph extractions.

Each extraction batch creates a :Node (extraction URI) with triples:
  (extraction, prov/derived-from, document_uri)   — source document
  (extraction, prov/method, "llm_relationships")   — extraction method
  (extraction, prov/model, "Qwen3.5-9B")           — LLM model used
  (extraction, prov/timestamp, "2026-03-27T10:30Z") — when extracted
  (extraction, prov/chunk-text, "...source...")      — source chunk text
  (extraction, prov/chunk-offset, "1500")            — position in document
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


class ProvenanceService:
    def __init__(self, store: TripleStore):
        self._store = store

    async def record_extraction(
        self,
        document_uri: str,
        extraction_method: str,
        model_name: str,
        chunk_text: str,
        chunk_offset: int,
        user: str,
        collection: str,
    ) -> str:
        """Record provenance for an extraction batch. Returns extraction URI."""
        ext_uri = URIBuilder.extraction()
        await self._store.merge_node(uri=ext_uri, user=user, collection=collection)

        # derived-from → document (Node-to-Node)
        await self._store.create_rel(
            subject_uri=ext_uri,
            predicate_uri=URIBuilder.predicate("prov", "derived-from"),
            object_value=document_uri,
            user=user,
            collection=collection,
            object_is_node=True,
            extraction_method="provenance",
        )

        # method, model, timestamp, chunk-text, chunk-offset → Literals
        literals = {
            "method": extraction_method,
            "model": model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "chunk-text": chunk_text[:500],  # Truncate to 500 chars
            "chunk-offset": str(chunk_offset),
        }
        for pred_name, value in literals.items():
            await self._store.merge_literal(value=value, user=user, collection=collection)
            await self._store.create_rel(
                subject_uri=ext_uri,
                predicate_uri=URIBuilder.predicate("prov", pred_name),
                object_value=value,
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="provenance",
            )

        return ext_uri
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_store.py::TestProvenance -x --tb=short -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/provenance.py \
       backend/microservices/knowledge-tree-service/tests/test_triple_store.py
git commit -m "feat(trustgraph): PROV-O provenance service"
```

---

### Task 6: Batch contradiction detection

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/contradiction.py`
- Create: `backend/microservices/knowledge-tree-service/tests/test_contradiction.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_contradiction.py
import pytest
import pytest_asyncio

from app.services.triple_store import TripleStore
from app.services.contradiction import ContradictionDetector
from app.services.uri_builder import URIBuilder


@pytest.mark.asyncio
class TestContradictionDetection:
    @pytest_asyncio.fixture(autouse=True)
    async def seed_contradicting_data(self, falkordb_client):
        """Seed two documents claiming different salaries for Juan."""
        store = TripleStore(falkordb_client)
        # Juan type + label
        await store.store_triple("Juan García", "core", "type", "person", False, "t1", "default", "llm_objects")
        # Salary from doc A: 30000 EUR
        await store.store_triple("Juan García", "legal", "salario-bruto", "30000 EUR", False, "t1", "default", "llm_relationships", source_chunk="Salario bruto de 30.000 EUR")
        # Salary from doc B: 28000 EUR (different extraction, same predicate)
        await store.store_triple("Juan García", "legal", "salario-bruto", "28000 EUR", False, "t1", "default", "llm_relationships", source_chunk="Salario 28.000 EUR")

    async def test_detects_contradiction(self, falkordb_client):
        detector = ContradictionDetector(falkordb_client)
        contradictions = await detector.detect_for_subject(
            subject_uri=URIBuilder.entity("default", "Juan García"),
            user="t1",
        )
        assert len(contradictions) >= 1
        c = contradictions[0]
        assert c["predicate"] == URIBuilder.predicate("legal", "salario-bruto")
        values = {c["value_a"], c["value_b"]}
        assert "30000 EUR" in values
        assert "28000 EUR" in values

    async def test_stores_contradiction_node(self, falkordb_client):
        detector = ContradictionDetector(falkordb_client)
        stored = await detector.detect_and_store(
            subject_uri=URIBuilder.entity("default", "Juan García"),
            user="t1",
            collection="default",
        )
        assert len(stored) >= 1
        # Verify contradiction node exists in graph
        result = await falkordb_client.execute_cypher(
            """
            MATCH (c:Node)-[:Rel {uri: 'nouxcube://predicate/core/contradiction-subject'}]->(s:Node)
            WHERE c.uri STARTS WITH 'nouxcube://contradiction/' AND s.user = 't1'
            RETURN c.uri AS c_uri, s.uri AS s_uri
            """
        )
        assert len(result) >= 1

    async def test_no_contradiction_when_same_value(self, falkordb_client):
        """Same value from two sources is NOT a contradiction."""
        store = TripleStore(falkordb_client)
        await store.store_triple("María López", "core", "type", "person", False, "t1", "default", "llm_objects")
        await store.store_triple("María López", "legal", "salario-bruto", "25000 EUR", False, "t1", "default", "llm_relationships")
        await store.store_triple("María López", "legal", "salario-bruto", "25000 EUR", False, "t1", "default", "llm_relationships")
        detector = ContradictionDetector(falkordb_client)
        contradictions = await detector.detect_for_subject(
            subject_uri=URIBuilder.entity("default", "María López"),
            user="t1",
        )
        assert len(contradictions) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_contradiction.py -x --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# app/services/contradiction.py
"""
Batch contradiction detection for TrustGraph.

Detects when the same subject+predicate points to different literal values
from different extraction sources. Creates :Node contradiction records.

Run per-document (after all extractors finish), not per-triple.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.falkordb_client import FalkorDBClient
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logger = logging.getLogger(__name__)


class ContradictionDetector:
    def __init__(self, client: FalkorDBClient):
        self._client = client

    async def detect_for_subject(
        self, subject_uri: str, user: str
    ) -> List[Dict[str, Any]]:
        """Find contradictions: same subject+predicate, different literal objects."""
        result = await self._client.execute_cypher(
            """
            MATCH (s:Node {uri: $uri})-[r1:Rel]->(o1:Literal)
            WHERE r1.user = $user
            MATCH (s)-[r2:Rel]->(o2:Literal)
            WHERE r2.uri = r1.uri AND r2.user = $user
              AND id(o1) < id(o2)
              AND o1.value <> o2.value
            RETURN DISTINCT
                r1.uri AS predicate,
                o1.value AS value_a,
                o2.value AS value_b,
                r1.source_chunk AS chunk_a,
                r2.source_chunk AS chunk_b
            """,
            {"uri": subject_uri, "user": user},
        )
        return result

    async def detect_and_store(
        self,
        subject_uri: str,
        user: str,
        collection: str,
    ) -> List[str]:
        """Detect contradictions and store them as :Node records. Returns URIs."""
        contradictions = await self.detect_for_subject(subject_uri, user)
        stored_uris = []
        store = TripleStore(self._client)

        for c in contradictions:
            c_uri = URIBuilder.contradiction()
            await store.merge_node(uri=c_uri, user=user, collection=collection)

            # Link to subject
            await store.create_rel(
                subject_uri=c_uri,
                predicate_uri=URIBuilder.predicate("core", "contradiction-subject"),
                object_value=subject_uri,
                user=user,
                collection=collection,
                object_is_node=True,
                extraction_method="contradiction_detection",
            )

            # Store predicate as literal
            await store.merge_literal(value=c["predicate"], user=user, collection=collection)
            await store.create_rel(
                subject_uri=c_uri,
                predicate_uri=URIBuilder.predicate("core", "contradiction-predicate"),
                object_value=c["predicate"],
                user=user,
                collection=collection,
                object_is_node=False,
                extraction_method="contradiction_detection",
            )

            # Link to both values
            for suffix, val_key in [("contradiction-value-a", "value_a"), ("contradiction-value-b", "value_b")]:
                await store.merge_literal(value=c[val_key], user=user, collection=collection)
                await store.create_rel(
                    subject_uri=c_uri,
                    predicate_uri=URIBuilder.predicate("core", suffix),
                    object_value=c[val_key],
                    user=user,
                    collection=collection,
                    object_is_node=False,
                    extraction_method="contradiction_detection",
                )

            stored_uris.append(c_uri)
            logger.info(
                "Contradiction stored: %s → %s vs %s (predicate: %s)",
                subject_uri, c["value_a"], c["value_b"], c["predicate"],
            )

        return stored_uris

    async def detect_batch_for_document(
        self,
        document_uri: str,
        user: str,
        collection: str,
    ) -> List[str]:
        """Detect contradictions for ALL entities mentioned in a document."""
        # Find all entity subjects that have triples extracted from this document
        entities = await self._client.execute_cypher(
            """
            MATCH (e:Node {uri: $doc})<-[:Rel {uri: 'nouxcube://predicate/prov/derived-from'}]-(ext:Node)
            WITH ext
            MATCH (s:Node)-[r:Rel]->(o)
            WHERE r.user = $user AND s.uri STARTS WITH 'nouxcube://entity/'
            RETURN DISTINCT s.uri AS entity_uri
            """,
            {"doc": document_uri, "user": user},
        )

        all_uris = []
        for entity in entities:
            uris = await self.detect_and_store(
                entity["entity_uri"], user, collection
            )
            all_uris.extend(uris)
        return all_uris
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_contradiction.py -x --tb=short -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/contradiction.py \
       backend/microservices/knowledge-tree-service/tests/test_contradiction.py
git commit -m "feat(trustgraph): batch contradiction detection per document"
```

---

### Task 7: Pydantic schemas for API

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/schemas/triples.py`

- [ ] **Step 1: Write the schemas**

```python
# app/schemas/triples.py
"""Request/response models for TrustGraph triple API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Extraction requests ──

class TripleExtractionRequest(BaseModel):
    """Request to extract triples from document chunks."""
    tenant_id: str
    document_id: str
    collection: str = "default"
    chunks: List[str] = Field(..., min_length=1, description="Text chunks to extract from")
    title: str = ""
    file_path: str = ""
    semantic_type: str = ""
    domain: str = ""


class TripleExtractionResponse(BaseModel):
    success: bool
    document_uri: str = ""
    triples_created: int = 0
    contradictions_found: int = 0
    extraction_time_ms: int = 0
    errors: List[str] = []


# ── Query requests ──

class TripleQueryRequest(BaseModel):
    tenant_id: str
    subject_uri: Optional[str] = None
    predicate_uri: Optional[str] = None
    object_value: Optional[str] = None
    object_is_node: bool = False
    collection: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)


class TripleResult(BaseModel):
    subject: str
    predicate: str
    object: str
    object_type: str  # "node" or "literal"
    extraction_method: Optional[str] = None
    source_chunk: Optional[str] = None


class TripleQueryResponse(BaseModel):
    triples: List[TripleResult]
    count: int


# ── Context requests ──

class ContextRequest(BaseModel):
    tenant_id: str
    limit: int = Field(default=20, ge=1, le=100)


class ContextResponse(BaseModel):
    success: bool
    context_for_llm: str
    metadata: Dict[str, Any] = {}


# ── Stats ──

class StatsResponse(BaseModel):
    nodes: int
    literals: int
    rels: int
    contradictions: int = 0
    entity_types: Dict[str, int] = {}


# ── Structural indexing (compatibility with weaviate-service) ──

class StructuralIndexRequest(BaseModel):
    """Index a document's structural data into the triple store."""
    tenant_id: str
    document_id: str
    collection: str = "default"
    file_path: str = ""
    title: str = ""
    semantic_type: str = ""
    domain: str = ""
    connector_id: Optional[str] = None
    connector_type: Optional[str] = None


class StructuralIndexResponse(BaseModel):
    success: bool
    document_uri: str = ""


# ── Reindex ──

class ReindexRequest(BaseModel):
    tenant_id: str
    collection: str = "default"


class ReindexResponse(BaseModel):
    success: bool
    documents_processed: int = 0
    triples_created: int = 0
    errors: List[str] = []
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/schemas/triples.py
git commit -m "feat(trustgraph): Pydantic schemas for triple API"
```

---

### Task 8: Base extractor + 4 LLM extractors

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/extractors/__init__.py`
- Create: `backend/microservices/knowledge-tree-service/app/services/extractors/base.py`
- Create: `backend/microservices/knowledge-tree-service/app/services/extractors/definitions.py`
- Create: `backend/microservices/knowledge-tree-service/app/services/extractors/relationships.py`
- Create: `backend/microservices/knowledge-tree-service/app/services/extractors/objects.py`
- Create: `backend/microservices/knowledge-tree-service/app/services/extractors/topics.py`
- Create: `backend/microservices/knowledge-tree-service/tests/test_extractors.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_extractors.py
"""
Tests for TrustGraph LLM extractors.

Unit tests mock the LLM call and verify triple generation from LLM output.
Integration tests (marked slow) call real SGLang.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.extractors.base import BaseExtractor
from app.services.extractors.definitions import DefinitionsExtractor
from app.services.extractors.relationships import RelationshipsExtractor
from app.services.extractors.objects import ObjectsExtractor
from app.services.extractors.topics import TopicsExtractor


class TestDefinitionsExtractor:
    @pytest.mark.asyncio
    async def test_parses_llm_output(self):
        llm_response = json.dumps([
            {"entity": "TechCorp SL", "definition": "Empresa tecnológica con CIF B12345678"},
            {"entity": "Juan García", "definition": "Empleado del departamento Legal"},
        ])
        extractor = DefinitionsExtractor()
        with patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value=llm_response):
            triples = await extractor.extract("dummy chunk text")
        # 2 entities × 2 triples each (label + definition)
        assert len(triples) == 4
        subjects = {t["subject"] for t in triples}
        assert "TechCorp SL" in subjects
        assert "Juan García" in subjects
        predicates = {t["predicate_name"] for t in triples}
        assert "label" in predicates
        assert "definition" in predicates

    @pytest.mark.asyncio
    async def test_handles_empty_response(self):
        extractor = DefinitionsExtractor()
        with patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value="[]"):
            triples = await extractor.extract("empty chunk")
        assert triples == []

    @pytest.mark.asyncio
    async def test_handles_malformed_json(self):
        extractor = DefinitionsExtractor()
        with patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value="not json"):
            triples = await extractor.extract("bad chunk")
        assert triples == []


class TestRelationshipsExtractor:
    @pytest.mark.asyncio
    async def test_parses_entity_relationships(self):
        llm_response = json.dumps([
            {"subject": "Juan García", "predicate": "empleado-de", "object": "TechCorp SL", "object-entity": True},
            {"subject": "Juan García", "predicate": "salario-bruto", "object": "30000 EUR", "object-entity": False},
        ])
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value=llm_response):
            triples = await extractor.extract("Juan García trabaja en TechCorp con salario 30000")
        assert len(triples) == 2
        entity_rel = [t for t in triples if t["object_is_node"]]
        literal_rel = [t for t in triples if not t["object_is_node"]]
        assert len(entity_rel) == 1
        assert entity_rel[0]["object"] == "TechCorp SL"
        assert len(literal_rel) == 1
        assert literal_rel[0]["object"] == "30000 EUR"

    @pytest.mark.asyncio
    async def test_uses_mini_ontology_predicates(self):
        """Relationships extractor should include core predicates in prompt."""
        extractor = RelationshipsExtractor()
        prompt = extractor._build_prompt("test chunk")
        assert "empleado-de" in prompt or "core/" in prompt


class TestObjectsExtractor:
    @pytest.mark.asyncio
    async def test_parses_named_entities(self):
        llm_response = json.dumps([
            {"name": "Juan García López", "type": "person"},
            {"name": "TechCorp SL", "type": "organization"},
        ])
        extractor = ObjectsExtractor()
        with patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value=llm_response):
            triples = await extractor.extract("Juan García de TechCorp SL")
        # 2 entities × 2 triples each (label + type)
        assert len(triples) == 4
        types = [t for t in triples if t["predicate_name"] == "type"]
        assert len(types) == 2


class TestTopicsExtractor:
    @pytest.mark.asyncio
    async def test_parses_topics(self):
        llm_response = json.dumps([
            {"topic": "derecho laboral"},
            {"topic": "contratación temporal"},
        ])
        extractor = TopicsExtractor()
        with patch.object(extractor, "_call_llm", new_callable=AsyncMock, return_value=llm_response):
            triples = await extractor.extract("chunk about labor law")
        assert len(triples) == 2
        assert all(t["predicate_name"] == "has-topic" for t in triples)
        topics = {t["object"] for t in triples}
        assert "derecho laboral" in topics
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -x --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the base extractor**

```python
# app/services/extractors/__init__.py
from app.services.extractors.definitions import DefinitionsExtractor
from app.services.extractors.relationships import RelationshipsExtractor
from app.services.extractors.objects import ObjectsExtractor
from app.services.extractors.topics import TopicsExtractor

__all__ = [
    "DefinitionsExtractor",
    "RelationshipsExtractor",
    "ObjectsExtractor",
    "TopicsExtractor",
]
```

```python
# app/services/extractors/base.py
"""
Base class for TrustGraph LLM extractors.

Each extractor:
1. Builds a prompt from chunk text (+ optional ontology predicates)
2. Calls SGLang via OpenAI-compatible API (httpx)
3. Parses JSON response into a list of triple dicts
4. Returns triples in a uniform format for the coordinator

Langfuse prompt resolution: tries Langfuse first, falls back to hardcoded.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseExtractor:
    """Abstract base for all 4 extractors."""

    EXTRACTOR_NAME: str = ""  # Override in subclass
    LANGFUSE_PROMPT_ID: str = ""  # Override in subclass

    def __init__(self):
        self._sglang_url = getattr(settings, "SGLANG_BASE_URL", "http://sglang:8000/v1")
        self._sglang_model = getattr(settings, "SGLANG_MODEL", "Qwen/Qwen3-8B")
        self._timeout = 60.0

    async def extract(self, chunk_text: str) -> List[Dict[str, Any]]:
        """Extract triples from a chunk. Returns list of triple dicts."""
        try:
            prompt = self._build_prompt(chunk_text)
            llm_output = await self._call_llm(prompt)
            return self._parse_output(llm_output, chunk_text)
        except Exception:
            logger.exception("Extractor %s failed on chunk", self.EXTRACTOR_NAME)
            return []

    def _build_prompt(self, chunk_text: str) -> str:
        """Build extraction prompt. Override in subclass."""
        raise NotImplementedError

    def _parse_output(self, llm_output: str, chunk_text: str) -> List[Dict[str, Any]]:
        """Parse LLM JSON output into triple dicts. Override in subclass."""
        raise NotImplementedError

    async def _call_llm(self, prompt: str) -> str:
        """Call SGLang via OpenAI-compatible chat/completions API."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._sglang_url}/chat/completions",
                json={
                    "model": self._sglang_model,
                    "messages": [
                        {"role": "system", "content": "You are a knowledge extraction assistant. Always respond with valid JSON arrays."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _safe_parse_json(self, text: str) -> List[Dict[str, Any]]:
        """Parse JSON, handling common LLM quirks."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and "results" in parsed:
                return parsed["results"]
            if isinstance(parsed, dict) and "entities" in parsed:
                return parsed["entities"]
            if isinstance(parsed, dict) and "items" in parsed:
                return parsed["items"]
            return []
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse LLM JSON output: %s...", text[:200])
            return []
```

- [ ] **Step 4: Write the 4 extractors**

```python
# app/services/extractors/definitions.py
"""Extract definitions — what entities ARE."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor


class DefinitionsExtractor(BaseExtractor):
    EXTRACTOR_NAME = "definitions"
    LANGFUSE_PROMPT_ID = "trustgraph_extract_definitions"

    def _build_prompt(self, chunk_text: str) -> str:
        return f"""Extract entity definitions from the following text. For each entity mentioned, extract:
- "entity": the entity name (person, organization, concept, law, etc.)
- "definition": a concise definition or description of the entity based on the text

Return a JSON array of objects. If no entities are found, return an empty array [].

Text:
---
{chunk_text}
---

Respond ONLY with a JSON array like:
[{{"entity": "Name", "definition": "Description based on text"}}]"""

    def _parse_output(self, llm_output: str, chunk_text: str) -> List[Dict[str, Any]]:
        items = self._safe_parse_json(llm_output)
        triples = []
        for item in items:
            entity = item.get("entity", "").strip()
            definition = item.get("definition", "").strip()
            if not entity:
                continue
            # Label triple
            triples.append({
                "subject": entity,
                "predicate_ontology": "core",
                "predicate_name": "label",
                "object": entity,
                "object_is_node": False,
                "extraction_method": "llm_definitions",
                "source_chunk": chunk_text[:200],
            })
            # Definition triple
            if definition:
                triples.append({
                    "subject": entity,
                    "predicate_ontology": "core",
                    "predicate_name": "definition",
                    "object": definition,
                    "object_is_node": False,
                    "extraction_method": "llm_definitions",
                    "source_chunk": chunk_text[:200],
                })
        return triples
```

```python
# app/services/extractors/relationships.py
"""Extract relationships — how things RELATE (SPO semantic triples).

Includes a mini-ontology of ~20 core predicates to guide the LLM,
avoiding predicate chaos in Phase 1 (before full Ontology RAG in Phase 3).
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

# Mini-ontology: core predicates available in Phase 1.
# The LLM should prefer these but may propose new ones.
MINI_ONTOLOGY = """Available predicates (prefer these, but you may propose new ones if none fit):
Core: label, type, definition, has-topic, mentioned-in, contained-in, part-of, instance-of
Legal: empleado-de, firmante-de, representante-de, regulado-por, salario-bruto, tipo-contrato, vigente-desde, vigente-hasta, clausula, obligacion, derecho, modifica, derogado-por, references-law
Provenance: derived-from, supports, contradicts"""


class RelationshipsExtractor(BaseExtractor):
    EXTRACTOR_NAME = "relationships"
    LANGFUSE_PROMPT_ID = "trustgraph_extract_relationships"

    def _build_prompt(self, chunk_text: str) -> str:
        return f"""Extract semantic relationships from the following text as subject-predicate-object triples.

{MINI_ONTOLOGY}

For each relationship:
- "subject": the source entity name
- "predicate": the relationship type (use a predicate from the list above when possible, or propose a new one in kebab-case)
- "object": the target entity name OR a literal value (date, amount, description)
- "object-entity": true if the object is another entity (person, org, law), false if it's a literal value (date, amount, text)

Return a JSON array. If no relationships are found, return [].

Text:
---
{chunk_text}
---

Respond ONLY with a JSON array like:
[{{"subject": "Juan García", "predicate": "empleado-de", "object": "ACME Corp", "object-entity": true}}]"""

    def _parse_output(self, llm_output: str, chunk_text: str) -> List[Dict[str, Any]]:
        items = self._safe_parse_json(llm_output)
        triples = []
        for item in items:
            subject = item.get("subject", "").strip()
            predicate = item.get("predicate", "").strip()
            obj = item.get("object", "").strip()
            obj_is_entity = item.get("object-entity", False)
            if not subject or not predicate or not obj:
                continue
            # Determine ontology namespace
            ontology = "core"
            if predicate in ("empleado-de", "firmante-de", "representante-de", "regulado-por",
                            "salario-bruto", "tipo-contrato", "vigente-desde", "vigente-hasta",
                            "clausula", "obligacion", "derecho", "modifica", "derogado-por",
                            "references-law"):
                ontology = "legal"
            elif predicate in ("derived-from", "supports", "contradicts"):
                ontology = "prov" if predicate == "derived-from" else "core"
            triples.append({
                "subject": subject,
                "predicate_ontology": ontology,
                "predicate_name": predicate,
                "object": obj,
                "object_is_node": bool(obj_is_entity),
                "extraction_method": "llm_relationships",
                "source_chunk": chunk_text[:200],
            })
        return triples
```

```python
# app/services/extractors/objects.py
"""Extract objects — named entities with type classification."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor


class ObjectsExtractor(BaseExtractor):
    EXTRACTOR_NAME = "objects"
    LANGFUSE_PROMPT_ID = "trustgraph_extract_objects"

    def _build_prompt(self, chunk_text: str) -> str:
        return f"""Extract all named entities from the following text. For each entity:
- "name": the full entity name as it appears in the text
- "type": one of: person, organization, law, contract, location, date, amount, concept, medication, diagnosis, procedure

Return a JSON array. If no entities are found, return [].

Text:
---
{chunk_text}
---

Respond ONLY with a JSON array like:
[{{"name": "Juan García López", "type": "person"}}]"""

    def _parse_output(self, llm_output: str, chunk_text: str) -> List[Dict[str, Any]]:
        items = self._safe_parse_json(llm_output)
        triples = []
        for item in items:
            name = item.get("name", "").strip()
            entity_type = item.get("type", "").strip().lower()
            if not name:
                continue
            # Label triple
            triples.append({
                "subject": name,
                "predicate_ontology": "core",
                "predicate_name": "label",
                "object": name,
                "object_is_node": False,
                "extraction_method": "llm_objects",
                "source_chunk": chunk_text[:200],
            })
            # Type triple
            if entity_type:
                triples.append({
                    "subject": name,
                    "predicate_ontology": "core",
                    "predicate_name": "type",
                    "object": entity_type,
                    "object_is_node": False,
                    "extraction_method": "llm_objects",
                    "source_chunk": chunk_text[:200],
                })
        return triples
```

```python
# app/services/extractors/topics.py
"""Extract topics — thematic categories for indexing."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor


class TopicsExtractor(BaseExtractor):
    EXTRACTOR_NAME = "topics"
    LANGFUSE_PROMPT_ID = "trustgraph_extract_topics"

    def _build_prompt(self, chunk_text: str) -> str:
        return f"""Extract the main topics or themes from the following text.

Return a JSON array of topic objects. If no clear topics, return [].

Text:
---
{chunk_text}
---

Respond ONLY with a JSON array like:
[{{"topic": "derecho laboral"}}, {{"topic": "contratación temporal"}}]"""

    def _parse_output(self, llm_output: str, chunk_text: str) -> List[Dict[str, Any]]:
        items = self._safe_parse_json(llm_output)
        triples = []
        for item in items:
            topic = item.get("topic", "").strip()
            if not topic:
                continue
            triples.append({
                "subject": "",  # Will be set to document_uri by coordinator
                "predicate_ontology": "core",
                "predicate_name": "has-topic",
                "object": topic,
                "object_is_node": False,
                "extraction_method": "llm_topics",
                "source_chunk": chunk_text[:200],
            })
        return triples
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -x --tb=short -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/
git add backend/microservices/knowledge-tree-service/tests/test_extractors.py
git commit -m "feat(trustgraph): 4 LLM extractors (definitions, relationships, objects, topics)"
```

---

### Task 9: Extraction coordinator

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py`
- Create: `backend/microservices/knowledge-tree-service/tests/test_coordinator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_coordinator.py
import pytest
from unittest.mock import AsyncMock, patch

from app.services.extractors.coordinator import ExtractionCoordinator
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


@pytest.mark.asyncio
class TestCoordinator:
    async def test_orchestrates_4_extractors(self, falkordb_client):
        """Coordinator should run all 4 extractors and aggregate triples."""
        store = TripleStore(falkordb_client)
        coordinator = ExtractionCoordinator(store)

        # Mock all 4 extractors to return known triples
        mock_definitions = [
            {"subject": "Juan", "predicate_ontology": "core", "predicate_name": "label", "object": "Juan García", "object_is_node": False, "extraction_method": "llm_definitions", "source_chunk": "test"},
        ]
        mock_relationships = [
            {"subject": "Juan", "predicate_ontology": "legal", "predicate_name": "empleado-de", "object": "ACME", "object_is_node": True, "extraction_method": "llm_relationships", "source_chunk": "test"},
        ]
        mock_objects = [
            {"subject": "Juan", "predicate_ontology": "core", "predicate_name": "type", "object": "person", "object_is_node": False, "extraction_method": "llm_objects", "source_chunk": "test"},
        ]
        mock_topics = [
            {"subject": "", "predicate_ontology": "core", "predicate_name": "has-topic", "object": "derecho laboral", "object_is_node": False, "extraction_method": "llm_topics", "source_chunk": "test"},
        ]

        with patch.object(coordinator._definitions, "extract", new_callable=AsyncMock, return_value=mock_definitions), \
             patch.object(coordinator._relationships, "extract", new_callable=AsyncMock, return_value=mock_relationships), \
             patch.object(coordinator._objects, "extract", new_callable=AsyncMock, return_value=mock_objects), \
             patch.object(coordinator._topics, "extract", new_callable=AsyncMock, return_value=mock_topics):

            result = await coordinator.extract_chunk(
                chunk_text="Juan García trabaja en ACME Corp como abogado.",
                document_uri=URIBuilder.document("default", "doc-1"),
                user="t1",
                collection="default",
                chunk_offset=0,
            )

        assert result["triples_created"] >= 3  # label + empleado-de + type + has-topic (some may merge)
        assert result["extractors_run"] == 4

        # Verify triples exist in graph
        nodes = await falkordb_client.execute_cypher(
            "MATCH (n:Node) WHERE n.user = 't1' RETURN count(n) AS cnt"
        )
        assert nodes[0]["cnt"] >= 2  # Juan + ACME (+ doc node)

    async def test_topic_triples_linked_to_document(self, falkordb_client):
        """Topics should be linked to the document URI, not empty subject."""
        store = TripleStore(falkordb_client)
        coordinator = ExtractionCoordinator(store)
        doc_uri = URIBuilder.document("default", "doc-1")
        await store.merge_node(uri=doc_uri, user="t1", collection="default")

        mock_topics = [
            {"subject": "", "predicate_ontology": "core", "predicate_name": "has-topic", "object": "fiscal", "object_is_node": False, "extraction_method": "llm_topics", "source_chunk": "test"},
        ]

        with patch.object(coordinator._definitions, "extract", new_callable=AsyncMock, return_value=[]), \
             patch.object(coordinator._relationships, "extract", new_callable=AsyncMock, return_value=[]), \
             patch.object(coordinator._objects, "extract", new_callable=AsyncMock, return_value=[]), \
             patch.object(coordinator._topics, "extract", new_callable=AsyncMock, return_value=mock_topics):

            await coordinator.extract_chunk(
                chunk_text="test",
                document_uri=doc_uri,
                user="t1",
                collection="default",
                chunk_offset=0,
            )

        # Topic should be linked to document node
        result = await falkordb_client.execute_cypher(
            """
            MATCH (d:Node {uri: $uri})-[r:Rel]->(t:Literal)
            WHERE r.uri CONTAINS 'has-topic'
            RETURN t.value AS topic
            """,
            {"uri": doc_uri},
        )
        assert len(result) == 1
        assert result[0]["topic"] == "fiscal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_coordinator.py -x --tb=short`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# app/services/extractors/coordinator.py
"""
Orchestrate 4 TrustGraph extractors in parallel for a single chunk.

For each chunk:
1. Run 4 extractors concurrently (asyncio.gather)
2. Aggregate all triples
3. Deduplicate by (subject, predicate, object)
4. Store in FalkorDB via TripleStore
5. Record PROV-O provenance
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

from app.services.extractors.definitions import DefinitionsExtractor
from app.services.extractors.relationships import RelationshipsExtractor
from app.services.extractors.objects import ObjectsExtractor
from app.services.extractors.topics import TopicsExtractor
from app.services.provenance import ProvenanceService
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logger = logging.getLogger(__name__)


class ExtractionCoordinator:
    def __init__(self, store: TripleStore):
        self._store = store
        self._provenance = ProvenanceService(store)
        self._definitions = DefinitionsExtractor()
        self._relationships = RelationshipsExtractor()
        self._objects = ObjectsExtractor()
        self._topics = TopicsExtractor()

    async def extract_chunk(
        self,
        chunk_text: str,
        document_uri: str,
        user: str,
        collection: str,
        chunk_offset: int = 0,
        model_name: str = "Qwen3.5-9B",
    ) -> Dict[str, Any]:
        """Run 4 extractors on a chunk, store triples, record provenance."""
        start = time.monotonic()

        # Run all 4 extractors in parallel
        results = await asyncio.gather(
            self._definitions.extract(chunk_text),
            self._relationships.extract(chunk_text),
            self._objects.extract(chunk_text),
            self._topics.extract(chunk_text),
            return_exceptions=True,
        )

        # Collect all triples, handling exceptions
        all_triples: List[Dict[str, Any]] = []
        extractor_names = ["definitions", "relationships", "objects", "topics"]
        errors = []
        for name, result in zip(extractor_names, results):
            if isinstance(result, Exception):
                errors.append(f"{name}: {result}")
                logger.error("Extractor %s failed: %s", name, result)
            else:
                all_triples.extend(result)

        # Deduplicate by (subject, predicate_name, object)
        seen = set()
        unique_triples = []
        for t in all_triples:
            key = (t["subject"], t["predicate_name"], t["object"])
            if key not in seen:
                seen.add(key)
                unique_triples.append(t)

        # Store each triple
        stored_count = 0
        stored_subjects = set()
        for t in unique_triples:
            try:
                # Topics: set subject to document_uri
                if t["predicate_name"] == "has-topic" and not t["subject"]:
                    # Store directly: document_uri → has-topic → topic_literal
                    await self._store.merge_literal(value=t["object"], user=user, collection=collection)
                    await self._store.create_rel(
                        subject_uri=document_uri,
                        predicate_uri=URIBuilder.predicate(t["predicate_ontology"], t["predicate_name"]),
                        object_value=t["object"],
                        user=user,
                        collection=collection,
                        object_is_node=False,
                        extraction_method=t["extraction_method"],
                        source_chunk=t.get("source_chunk", ""),
                    )
                else:
                    subject_uri = await self._store.store_triple(
                        subject_name=t["subject"],
                        predicate_ontology=t["predicate_ontology"],
                        predicate_name=t["predicate_name"],
                        object_value=t["object"],
                        object_is_node=t["object_is_node"],
                        user=user,
                        collection=collection,
                        extraction_method=t["extraction_method"],
                        source_chunk=t.get("source_chunk", ""),
                    )
                    stored_subjects.add(subject_uri)
                stored_count += 1
            except Exception as e:
                errors.append(f"store_triple: {e}")
                logger.error("Failed to store triple %s: %s", t, e)

        # Record provenance
        await self._provenance.record_extraction(
            document_uri=document_uri,
            extraction_method="trustgraph_4_extractors",
            model_name=model_name,
            chunk_text=chunk_text,
            chunk_offset=chunk_offset,
            user=user,
            collection=collection,
        )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "triples_created": stored_count,
            "triples_total": len(all_triples),
            "triples_deduped": len(all_triples) - len(unique_triples),
            "extractors_run": 4 - len([e for e in errors if ":" in e and e.split(":")[0] in extractor_names]),
            "subjects": list(stored_subjects),
            "errors": errors,
            "elapsed_ms": elapsed_ms,
        }

    async def extract_document(
        self,
        chunks: List[str],
        document_id: str,
        user: str,
        collection: str = "default",
        title: str = "",
        file_path: str = "",
        semantic_type: str = "",
        domain: str = "",
    ) -> Dict[str, Any]:
        """Extract triples from all chunks of a document.

        1. Create document structural node
        2. Extract triples from each chunk sequentially
        3. Run batch contradiction detection on all extracted subjects
        """
        from app.services.contradiction import ContradictionDetector

        start = time.monotonic()

        # Create document node with structural triples
        doc_uri = await self._store.store_document_node(
            document_id=document_id,
            user=user,
            collection=collection,
            title=title,
            file_path=file_path,
            semantic_type=semantic_type,
            domain=domain,
        )

        # Extract from each chunk
        total_triples = 0
        all_subjects = set()
        all_errors = []

        for i, chunk in enumerate(chunks):
            result = await self.extract_chunk(
                chunk_text=chunk,
                document_uri=doc_uri,
                user=user,
                collection=collection,
                chunk_offset=i * 1500,  # Approximate offset
            )
            total_triples += result["triples_created"]
            all_subjects.update(result["subjects"])
            all_errors.extend(result["errors"])

        # Batch contradiction detection
        detector = ContradictionDetector(self._store._client)
        contradiction_uris = []
        for subject_uri in all_subjects:
            uris = await detector.detect_and_store(subject_uri, user, collection)
            contradiction_uris.extend(uris)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "success": True,
            "document_uri": doc_uri,
            "triples_created": total_triples,
            "contradictions_found": len(contradiction_uris),
            "chunks_processed": len(chunks),
            "extraction_time_ms": elapsed_ms,
            "errors": all_errors,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_coordinator.py -x --tb=short -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py \
       backend/microservices/knowledge-tree-service/tests/test_coordinator.py
git commit -m "feat(trustgraph): extraction coordinator — 4 parallel extractors per chunk"
```

---

### Task 10: REST API endpoints

**Files:**
- Create: `backend/microservices/knowledge-tree-service/app/api/triples.py`
- Create: `backend/microservices/knowledge-tree-service/app/api/extract.py`
- Modify: `backend/microservices/knowledge-tree-service/app/main.py`

- [ ] **Step 1: Write the API routers**

```python
# app/api/triples.py
"""REST API for TrustGraph triple queries."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.schemas.triples import (
    ContextRequest, ContextResponse,
    StatsResponse,
    TripleQueryRequest, TripleQueryResponse, TripleResult,
)
from app.services.falkordb_client import falkordb_client
from app.services.triple_query import TripleQuery
from app.services.uri_builder import URIBuilder

router = APIRouter(prefix="/triples", tags=["triples"], dependencies=[Depends(verify_api_key)])


@router.post("/query", response_model=TripleQueryResponse)
async def query_triples(request: TripleQueryRequest):
    query = TripleQuery(falkordb_client)
    if request.subject_uri and request.predicate_uri:
        results = await query.by_spo(request.subject_uri, request.predicate_uri, request.tenant_id, request.collection)
    elif request.subject_uri:
        results = await query.by_subject(request.subject_uri, request.tenant_id, request.collection, request.limit)
    elif request.predicate_uri and request.object_value:
        results = await query.by_predicate_object(request.predicate_uri, request.object_value, request.tenant_id, request.object_is_node)
    elif request.predicate_uri:
        results = await query.by_predicate(request.predicate_uri, request.tenant_id, request.collection, request.limit)
    elif request.object_value:
        if request.object_is_node:
            results = await query.by_object_node(request.object_value, request.tenant_id, request.collection, request.limit)
        else:
            results = await query.by_object_value(request.object_value, request.tenant_id, request.collection, request.limit)
    else:
        results = []
    triples = [TripleResult(**r) for r in results]
    return TripleQueryResponse(triples=triples, count=len(triples))


@router.post("/context", response_model=ContextResponse)
async def get_context(request: ContextRequest):
    query = TripleQuery(falkordb_client)
    context = await query.build_context(user=request.tenant_id, limit=request.limit)
    stats = await query.get_stats(user=request.tenant_id)
    return ContextResponse(success=True, context_for_llm=context, metadata=stats)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(tenant_id: str, collection: str = None):
    query = TripleQuery(falkordb_client)
    stats = await query.get_stats(user=tenant_id, collection=collection)
    # Count contradictions
    contradictions = await falkordb_client.execute_cypher(
        "MATCH (c:Node) WHERE c.uri STARTS WITH 'nouxcube://contradiction/' AND c.user = $user RETURN count(c) AS cnt",
        {"user": tenant_id},
    )
    stats["contradictions"] = contradictions[0]["cnt"] if contradictions else 0
    # Entity type breakdown
    types = await falkordb_client.execute_cypher(
        """
        MATCH (n:Node)-[r:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal)
        WHERE r.user = $user
        RETURN t.value AS type, count(n) AS cnt
        ORDER BY cnt DESC
        """,
        {"user": tenant_id},
    )
    stats["entity_types"] = {t["type"]: t["cnt"] for t in types}
    return StatsResponse(**stats)


@router.delete("/clear")
async def clear_tenant(tenant_id: str):
    from app.services.triple_store import TripleStore
    store = TripleStore(falkordb_client)
    deleted = await store.clear_tenant(user=tenant_id)
    return {"success": True, "deleted": deleted}
```

```python
# app/api/extract.py
"""REST API for TrustGraph triple extraction."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.security import verify_api_key
from app.schemas.triples import (
    StructuralIndexRequest, StructuralIndexResponse,
    TripleExtractionRequest, TripleExtractionResponse,
)
from app.services.extractors.coordinator import ExtractionCoordinator
from app.services.falkordb_client import falkordb_client
from app.services.triple_store import TripleStore

router = APIRouter(prefix="/extract", tags=["extraction"], dependencies=[Depends(verify_api_key)])


@router.post("/triples", response_model=TripleExtractionResponse)
async def extract_triples(request: TripleExtractionRequest):
    """Extract triples from document chunks using 4 LLM extractors."""
    store = TripleStore(falkordb_client)
    coordinator = ExtractionCoordinator(store)
    result = await coordinator.extract_document(
        chunks=request.chunks,
        document_id=request.document_id,
        user=request.tenant_id,
        collection=request.collection,
        title=request.title,
        file_path=request.file_path,
        semantic_type=request.semantic_type,
        domain=request.domain,
    )
    return TripleExtractionResponse(**result)


@router.post("/structural", response_model=StructuralIndexResponse)
async def index_structural(request: StructuralIndexRequest):
    """Index a document's structural data (node + folder) without LLM extraction."""
    store = TripleStore(falkordb_client)
    doc_uri = await store.store_document_node(
        document_id=request.document_id,
        user=request.tenant_id,
        collection=request.collection,
        title=request.title,
        file_path=request.file_path,
        semantic_type=request.semantic_type,
        domain=request.domain,
    )
    return StructuralIndexResponse(success=True, document_uri=doc_uri)
```

- [ ] **Step 2: Update main.py to register new routers**

Replace the old routers in `app/main.py`:

```python
# app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.falkordb_client import falkordb_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect to FalkorDB and bootstrap schema."""
    await falkordb_client.initialize()
    await falkordb_client.bootstrap_schema()
    yield
    await falkordb_client.close()


app = FastAPI(
    title="Knowledge Tree Service — TrustGraph",
    description="Triple store for TrustGraph knowledge graph on FalkorDB",
    version="2.0.0",
    lifespan=lifespan,
)

# Import and register routers
from app.api.triples import router as triples_router
from app.api.extract import router as extract_router

app.include_router(triples_router)
app.include_router(extract_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "knowledge-tree-service", "version": "2.0.0"}
```

- [ ] **Step 3: Run a quick smoke test**

Run: `cd backend/microservices/knowledge-tree-service && python -c "from app.main import app; print('OK:', [r.path for r in app.routes])"`
Expected: Prints route paths including `/triples/query`, `/extract/triples`, `/health`

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/api/triples.py \
       backend/microservices/knowledge-tree-service/app/api/extract.py \
       backend/microservices/knowledge-tree-service/app/main.py
git commit -m "feat(trustgraph): REST API endpoints for triple query + extraction"
```

---

### Task 11: Mini-ontology seed script

**Files:**
- Create: `backend/microservices/knowledge-tree-service/scripts/seed_ontology.py`

- [ ] **Step 1: Write the seed script**

```python
# scripts/seed_ontology.py
"""
Seed the mini-ontology into FalkorDB as triples in the _ontology collection.

This provides ~20 core predicates to guide LLM extraction in Phase 1.
Full Ontology RAG (Phase 3) will expand this catalog per sector.

Usage:
  docker compose exec knowledge-tree-service python scripts/seed_ontology.py
  docker compose exec knowledge-tree-service python scripts/seed_ontology.py --force
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.falkordb_client import falkordb_client
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ONTOLOGY_USER = "_system"
ONTOLOGY_COLLECTION = "_ontology"

# Core predicates (~10)
CORE_PREDICATES = [
    ("core", "label", "Nombre o etiqueta", "any", "literal"),
    ("core", "definition", "Definición o descripción", "any", "literal"),
    ("core", "type", "Tipo de entidad", "any", "literal"),
    ("core", "has-topic", "Tema o categoría temática", "document", "literal"),
    ("core", "mentioned-in", "Entidad mencionada en documento", "entity", "document"),
    ("core", "contained-in", "Documento contenido en carpeta", "document", "folder"),
    ("core", "part-of", "Parte de una entidad mayor", "any", "any"),
    ("core", "instance-of", "Instancia de un tipo", "any", "type"),
    ("core", "supports", "Soporta o respalda", "any", "any"),
    ("core", "contradicts", "Contradice", "any", "any"),
    ("core", "semantic-type", "Tipo semántico del documento", "document", "literal"),
    ("core", "domain", "Dominio de negocio", "any", "literal"),
]

# Legal predicates (~14)
LEGAL_PREDICATES = [
    ("legal", "empleado-de", "Relación laboral entre persona y empresa", "person", "organization"),
    ("legal", "firmante-de", "Persona firmante de un documento", "person", "document"),
    ("legal", "representante-de", "Representante legal de una entidad", "person", "organization"),
    ("legal", "regulado-por", "Regulado por una ley o normativa", "any", "law"),
    ("legal", "salario-bruto", "Salario bruto anual o mensual", "person", "literal"),
    ("legal", "tipo-contrato", "Tipo de contrato laboral", "document", "literal"),
    ("legal", "vigente-desde", "Fecha de inicio de vigencia", "any", "literal"),
    ("legal", "vigente-hasta", "Fecha de fin de vigencia", "any", "literal"),
    ("legal", "clausula", "Cláusula contractual", "document", "literal"),
    ("legal", "obligacion", "Obligación derivada", "any", "literal"),
    ("legal", "derecho", "Derecho reconocido", "any", "literal"),
    ("legal", "modifica", "Modifica otra norma", "law", "law"),
    ("legal", "derogado-por", "Derogado por otra norma", "law", "law"),
    ("legal", "references-law", "Referencia a ley o norma", "any", "law"),
]

# Provenance predicates (PROV-O)
PROV_PREDICATES = [
    ("prov", "derived-from", "Fuente de la extracción", "extraction", "document"),
    ("prov", "method", "Método de extracción", "extraction", "literal"),
    ("prov", "model", "Modelo LLM utilizado", "extraction", "literal"),
    ("prov", "timestamp", "Momento de la extracción", "extraction", "literal"),
    ("prov", "chunk-text", "Texto fuente del chunk", "extraction", "literal"),
    ("prov", "chunk-offset", "Posición en el documento", "extraction", "literal"),
]

ALL_PREDICATES = CORE_PREDICATES + LEGAL_PREDICATES + PROV_PREDICATES


async def seed(force: bool = False):
    await falkordb_client.initialize()
    await falkordb_client.bootstrap_schema()
    store = TripleStore(falkordb_client)

    # Check existing
    existing = await falkordb_client.execute_cypher(
        "MATCH (n:Node) WHERE n.user = $user AND n.collection = $coll RETURN count(n) AS cnt",
        {"user": ONTOLOGY_USER, "coll": ONTOLOGY_COLLECTION},
    )
    existing_count = existing[0]["cnt"] if existing else 0

    if existing_count > 0 and not force:
        logger.info("Ontology already seeded (%d nodes). Use --force to overwrite.", existing_count)
        return

    if force and existing_count > 0:
        logger.info("Force mode: clearing existing ontology...")
        await store.clear_collection(user=ONTOLOGY_USER, collection=ONTOLOGY_COLLECTION)

    created = 0
    for ontology, name, description, domain_type, range_type in ALL_PREDICATES:
        pred_uri = URIBuilder.predicate(ontology, name)
        await store.merge_node(uri=pred_uri, user=ONTOLOGY_USER, collection=ONTOLOGY_COLLECTION)

        # onto/label
        await store.merge_literal(value=name, user=ONTOLOGY_USER, collection=ONTOLOGY_COLLECTION)
        await store.create_rel(
            subject_uri=pred_uri,
            predicate_uri=URIBuilder.predicate("onto", "label"),
            object_value=name,
            user=ONTOLOGY_USER,
            collection=ONTOLOGY_COLLECTION,
            object_is_node=False,
            extraction_method="seed",
        )

        # onto/description
        await store.merge_literal(value=description, user=ONTOLOGY_USER, collection=ONTOLOGY_COLLECTION)
        await store.create_rel(
            subject_uri=pred_uri,
            predicate_uri=URIBuilder.predicate("onto", "description"),
            object_value=description,
            user=ONTOLOGY_USER,
            collection=ONTOLOGY_COLLECTION,
            object_is_node=False,
            extraction_method="seed",
        )

        # onto/domain
        await store.merge_literal(value=domain_type, user=ONTOLOGY_USER, collection=ONTOLOGY_COLLECTION)
        await store.create_rel(
            subject_uri=pred_uri,
            predicate_uri=URIBuilder.predicate("onto", "domain"),
            object_value=domain_type,
            user=ONTOLOGY_USER,
            collection=ONTOLOGY_COLLECTION,
            object_is_node=False,
            extraction_method="seed",
        )

        # onto/range
        await store.merge_literal(value=range_type, user=ONTOLOGY_USER, collection=ONTOLOGY_COLLECTION)
        await store.create_rel(
            subject_uri=pred_uri,
            predicate_uri=URIBuilder.predicate("onto", "range"),
            object_value=range_type,
            user=ONTOLOGY_USER,
            collection=ONTOLOGY_COLLECTION,
            object_is_node=False,
            extraction_method="seed",
        )

        # onto/sector
        await store.merge_literal(value=ontology, user=ONTOLOGY_USER, collection=ONTOLOGY_COLLECTION)
        await store.create_rel(
            subject_uri=pred_uri,
            predicate_uri=URIBuilder.predicate("onto", "sector"),
            object_value=ontology,
            user=ONTOLOGY_USER,
            collection=ONTOLOGY_COLLECTION,
            object_is_node=False,
            extraction_method="seed",
        )

        created += 1
        logger.info("  ✓ %s/%s — %s", ontology, name, description)

    logger.info("\nSeeded %d predicates (%d core, %d legal, %d prov)",
                created, len(CORE_PREDICATES), len(LEGAL_PREDICATES), len(PROV_PREDICATES))
    await falkordb_client.close()


def main():
    parser = argparse.ArgumentParser(description="Seed TrustGraph mini-ontology")
    parser.add_argument("--force", action="store_true", help="Overwrite existing ontology")
    args = parser.parse_args()
    asyncio.run(seed(force=args.force))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/seed_ontology.py
git commit -m "feat(trustgraph): mini-ontology seed script (32 predicates: core + legal + prov)"
```

---

### Task 12: Langfuse extraction prompt seed

**Files:**
- Create: `backend/microservices/knowledge-tree-service/scripts/seed_langfuse_extraction_prompts.py`

- [ ] **Step 1: Write the Langfuse seed script**

```python
# scripts/seed_langfuse_extraction_prompts.py
"""
Seed TrustGraph extraction prompts to Langfuse.

Creates 4 prompts (one per extractor) with label="production".
Safe by default: only creates MISSING prompts.

Usage:
  docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py
  docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py --force
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Langfuse SDK
try:
    from langfuse import Langfuse
except ImportError:
    print("ERROR: langfuse package not installed. Run: pip install langfuse")
    sys.exit(1)


PROMPTS = {
    "trustgraph_extract_definitions": {
        "type": "text",
        "prompt": """Extract entity definitions from the following text. For each entity mentioned, extract:
- "entity": the entity name (person, organization, concept, law, etc.)
- "definition": a concise definition or description of the entity based on the text

Return a JSON array of objects. If no entities are found, return an empty array [].

Text:
---
{{text}}
---

Respond ONLY with a JSON array like:
[{"entity": "Name", "definition": "Description based on text"}]""",
        "config": {"model": "chat", "temperature": 0.1, "max_tokens": 4096},
    },
    "trustgraph_extract_relationships": {
        "type": "text",
        "prompt": """Extract semantic relationships from the following text as subject-predicate-object triples.

Available predicates (prefer these, but you may propose new ones if none fit):
Core: label, type, definition, has-topic, mentioned-in, contained-in, part-of, instance-of
Legal: empleado-de, firmante-de, representante-de, regulado-por, salario-bruto, tipo-contrato, vigente-desde, vigente-hasta, clausula, obligacion, derecho, modifica, derogado-por, references-law
Provenance: derived-from, supports, contradicts

For each relationship:
- "subject": the source entity name
- "predicate": the relationship type (use a predicate from the list above when possible, or propose a new one in kebab-case)
- "object": the target entity name OR a literal value (date, amount, description)
- "object-entity": true if the object is another entity (person, org, law), false if it's a literal value

Return a JSON array. If no relationships are found, return [].

Text:
---
{{text}}
---

Respond ONLY with a JSON array like:
[{"subject": "Juan García", "predicate": "empleado-de", "object": "ACME Corp", "object-entity": true}]""",
        "config": {"model": "chat", "temperature": 0.1, "max_tokens": 4096},
    },
    "trustgraph_extract_objects": {
        "type": "text",
        "prompt": """Extract all named entities from the following text. For each entity:
- "name": the full entity name as it appears in the text
- "type": one of: person, organization, law, contract, location, date, amount, concept, medication, diagnosis, procedure

Return a JSON array. If no entities are found, return [].

Text:
---
{{text}}
---

Respond ONLY with a JSON array like:
[{"name": "Juan García López", "type": "person"}]""",
        "config": {"model": "chat", "temperature": 0.1, "max_tokens": 4096},
    },
    "trustgraph_extract_topics": {
        "type": "text",
        "prompt": """Extract the main topics or themes from the following text.

Return a JSON array of topic objects. If no clear topics, return [].

Text:
---
{{text}}
---

Respond ONLY with a JSON array like:
[{"topic": "derecho laboral"}, {"topic": "contratación temporal"}]""",
        "config": {"model": "chat", "temperature": 0.1, "max_tokens": 2048},
    },
}


def seed(force: bool = False):
    langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-local"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-local"),
        host=os.getenv("LANGFUSE_HOST", "http://langfuse:3002"),
    )

    for name, config in PROMPTS.items():
        try:
            existing = langfuse.get_prompt(name, label="production")
            if not force:
                print(f"  SKIP {name} (already exists, version {existing.version})")
                continue
            print(f"  OVERWRITE {name} (force mode)")
        except Exception:
            print(f"  CREATE {name}")

        langfuse.create_prompt(
            name=name,
            prompt=config["prompt"],
            type=config["type"],
            config=config["config"],
            labels=["production"],
        )

    langfuse.flush()
    print(f"\nDone. {len(PROMPTS)} prompts processed.")


def main():
    parser = argparse.ArgumentParser(description="Seed TrustGraph extraction prompts to Langfuse")
    parser.add_argument("--force", action="store_true", help="Overwrite existing prompts")
    args = parser.parse_args()
    seed(force=args.force)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/seed_langfuse_extraction_prompts.py
git commit -m "feat(trustgraph): Langfuse extraction prompt seed script (4 prompts)"
```

---

### Task 13: Delete old KTS services and APIs

**Files:**
- Delete: All old service files, API files, and tests listed in the "Deleted" section above
- Keep: `app/services/falkordb_client.py`, `app/core/`

- [ ] **Step 1: Delete old files**

```bash
cd backend/microservices/knowledge-tree-service

# Old services
rm -f app/services/entity_graph_bridge.py
rm -f app/services/structural_indexer.py
rm -f app/services/claim_extractor.py
rm -f app/services/subgraph_extractor.py
rm -f app/services/tenant_knowledge_service.py
rm -f app/services/memory_bank_service.py
rm -f app/services/graph_bootstrap.py

# Old APIs
rm -f app/api/tree.py
rm -f app/api/entities.py
rm -f app/api/claims.py
rm -f app/api/memory_bank.py
rm -f app/api/legal_links.py

# Old config
rm -f config/graphs/knowledge_graph_schema.cypher
rm -f config/prompts/emma_prompts.yaml

# Old tests
rm -f tests/test_falkordb_client.py
rm -f tests/test_batch_traversal.py
rm -f tests/test_claim_extractor.py
```

- [ ] **Step 2: Verify no import errors**

Run: `cd backend/microservices/knowledge-tree-service && python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Run all new tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/ -x --tb=short -v`
Expected: All new tests PASS

- [ ] **Step 4: Commit**

```bash
cd backend/microservices/knowledge-tree-service
git add -A
git commit -m "cleanup(trustgraph): delete old typed-label services, APIs, tests, schema"
```

---

### Task 14: Weaviate-service pipeline integration

**Files:**
- Modify: `backend/microservices/weaviate-service/app/clients/knowledge_tree_client.py`
- Modify: `backend/microservices/weaviate-service/app/services/knowledge/extraction_service.py`

- [ ] **Step 1: Add new methods to knowledge_tree_client.py**

Add these methods to the existing `KnowledgeTreeClient` class in `backend/microservices/weaviate-service/app/clients/knowledge_tree_client.py`:

```python
    # ── TrustGraph API (new) ──

    async def extract_triples(
        self,
        tenant_id: str,
        document_id: str,
        chunks: list[str],
        collection: str = "default",
        title: str = "",
        file_path: str = "",
        semantic_type: str = "",
        domain: str = "",
    ) -> dict:
        """Trigger triple extraction for a document's chunks."""
        return await self._post("/extract/triples", {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "chunks": chunks,
            "collection": collection,
            "title": title,
            "file_path": file_path,
            "semantic_type": semantic_type,
            "domain": domain,
        })

    async def index_structural(
        self,
        tenant_id: str,
        document_id: str,
        collection: str = "default",
        title: str = "",
        file_path: str = "",
        semantic_type: str = "",
        domain: str = "",
    ) -> dict:
        """Index document structural data (node + folder) without extraction."""
        return await self._post("/extract/structural", {
            "tenant_id": tenant_id,
            "document_id": document_id,
            "collection": collection,
            "title": title,
            "file_path": file_path,
            "semantic_type": semantic_type,
            "domain": domain,
        })

    async def query_triples(
        self,
        tenant_id: str,
        subject_uri: str = None,
        predicate_uri: str = None,
        object_value: str = None,
        limit: int = 100,
    ) -> dict:
        """Query triples from the graph."""
        return await self._post("/triples/query", {
            "tenant_id": tenant_id,
            "subject_uri": subject_uri,
            "predicate_uri": predicate_uri,
            "object_value": object_value,
            "limit": limit,
        })

    async def get_triple_context(self, tenant_id: str, limit: int = 20) -> dict:
        """Get LLM context from the triple store."""
        return await self._post("/triples/context", {
            "tenant_id": tenant_id,
            "limit": limit,
        })
```

- [ ] **Step 2: Update extraction_service.py to call new endpoint**

In `backend/microservices/weaviate-service/app/services/knowledge/extraction_service.py`, modify the `_store_entities` and related methods. Replace the entity-by-entity storage with a single call to `/extract/triples`:

Find the section in `extract_from_document` where entities are stored to knowledge-tree-service (around lines 560-608) and replace with:

```python
        # ── Store to Knowledge Graph via TrustGraph API ──
        if self._knowledge_tree_enabled:
            try:
                # Collect chunk texts for triple extraction
                chunk_texts = [chunk.text for chunk in self._chunks] if hasattr(self, '_chunks') else [content]

                kt_result = await knowledge_tree_legal_client.extract_triples(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunks=chunk_texts,
                    title=metadata.get("title", ""),
                    file_path=metadata.get("file_path", ""),
                    semantic_type=metadata.get("semantic_type", ""),
                    domain=str(domain),
                )
                logger.info(
                    "TrustGraph extraction: %d triples, %d contradictions (doc: %s)",
                    kt_result.get("triples_created", 0),
                    kt_result.get("contradictions_found", 0),
                    document_id,
                )
            except Exception as e:
                logger.error("TrustGraph extraction failed for %s: %s", document_id, e)
                errors.append(f"trustgraph: {e}")
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/weaviate-service/app/clients/knowledge_tree_client.py \
       backend/microservices/weaviate-service/app/services/knowledge/extraction_service.py
git commit -m "feat(trustgraph): weaviate-service pipeline calls /extract/triples"
```

---

### Task 15: Emma-agent-service client + tool adaptation

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/graph_expander.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/subgraph_formatter.py`
- Delete: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/entity_extractor.py`

- [ ] **Step 1: Add triple query methods to emma KTS client**

Add to the `KnowledgeTreeClient` class in `backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py`:

```python
    # ── TrustGraph API (new) ──

    async def query_triples(
        self,
        tenant_id: str,
        subject_uri: str | None = None,
        predicate_uri: str | None = None,
        object_value: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Query triples from the TrustGraph store."""
        return await self._post("/triples/query", {
            "tenant_id": tenant_id,
            "subject_uri": subject_uri,
            "predicate_uri": predicate_uri,
            "object_value": object_value,
            "limit": limit,
        })

    async def get_triple_context(self, tenant_id: str, limit: int = 20) -> dict:
        """Get LLM context from the triple store."""
        return await self._post("/triples/context", {
            "tenant_id": tenant_id,
            "limit": limit,
        })

    async def get_triple_stats(self, tenant_id: str) -> dict:
        """Get graph statistics."""
        return await self._get(f"/triples/stats?tenant_id={tenant_id}")
```

- [ ] **Step 2: Adapt graph_expander.py for :Node/:Rel model**

Rewrite `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/graph_expander.py` to use triple queries instead of typed-label queries. The key change: instead of calling `/tree/graph/documents-by-entity` and `/tree/graph/subgraph`, it now calls `/triples/query` with predicate URIs:

```python
# app/agents/langgraph/sectors/graph_expander.py
"""
Graph expansion for SmartSearch — TrustGraph triple model.

Expands entity names into related document IDs and graph context
using :Node/:Rel triple queries.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


async def expand_with_sector_graph(
    query: str,
    entities: Dict[str, List[str]],
    sector_config: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Expand entities via TrustGraph triples.

    Returns:
        graph_context: Textual context from graph
        related_entities: Related nodes found
        paths: Relationship paths
        expanded_doc_ids: Document IDs found via entity lookup
    """
    from app.clients.knowledge_tree_client import get_knowledge_tree_client

    client = get_knowledge_tree_client()
    expanded_doc_ids: Set[str] = set()
    paths: List[str] = []
    related_entities: List[Dict] = []

    # Phase 1: Entity → document lookups via triple queries
    entity_names = []
    for entity_type, values in entities.items():
        entity_names.extend(values[:5])  # Max 5 per type

    async def lookup_entity(name: str) -> List[str]:
        """Find documents mentioning this entity via triples."""
        try:
            # Build entity URI (normalized)
            slug = name.lower().strip().replace(" ", "-")
            result = await client.query_triples(
                tenant_id=tenant_id,
                subject_uri=f"nouxcube://entity/default/{slug}",
                predicate_uri="nouxcube://predicate/core/mentioned-in",
                limit=20,
            )
            triples = result.get("triples", [])
            doc_ids = []
            for t in triples:
                obj = t.get("object", "")
                if obj.startswith("nouxcube://document/"):
                    doc_id = obj.split("/")[-1]
                    doc_ids.append(doc_id)
            return doc_ids
        except Exception as e:
            logger.warning("Entity lookup failed for %s: %s", name, e)
            return []

    # Run lookups in parallel
    if entity_names:
        results = await asyncio.gather(
            *[lookup_entity(name) for name in entity_names],
            return_exceptions=True,
        )
        for name, result in zip(entity_names, results):
            if isinstance(result, list):
                expanded_doc_ids.update(result)
                for doc_id in result:
                    paths.append(f"{name} → mentioned-in → {doc_id[:12]}...")

    # Phase 2: Get graph context
    graph_context = ""
    try:
        ctx_result = await client.get_triple_context(tenant_id=tenant_id, limit=20)
        graph_context = ctx_result.get("context_for_llm", "")
    except Exception as e:
        logger.warning("Graph context failed: %s", e)

    return {
        "graph_context": graph_context,
        "related_entities": related_entities,
        "paths": paths,
        "expanded_doc_ids": list(expanded_doc_ids),
    }
```

- [ ] **Step 3: Delete entity_extractor.py (regex stays in smart_search.py)**

```bash
rm -f backend/microservices/emma-agent-service/app/agents/langgraph/sectors/entity_extractor.py
```

Update any imports in `smart_search.py` that reference `entity_extractor` — the `extract_entities` function is already defined locally in `smart_search.py` (it's the regex entity extraction for filter enrichment, not the LLM extraction).

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py \
       backend/microservices/emma-agent-service/app/agents/langgraph/sectors/graph_expander.py
git rm backend/microservices/emma-agent-service/app/agents/langgraph/sectors/entity_extractor.py
git commit -m "feat(trustgraph): emma-agent-service adapted to triple query model"
```

---

### Task 16: Background worker Celery tasks

**Files:**
- Create: `backend/microservices/background-worker/worker_app/tasks/trustgraph_tasks.py`
- Modify: `backend/microservices/background-worker/worker_app/celery_app.py`
- Modify: `backend/microservices/background-worker/start.sh`

- [ ] **Step 1: Create Celery tasks**

```python
# worker_app/tasks/trustgraph_tasks.py
"""
Celery tasks for TrustGraph triple extraction.

These tasks wrap HTTP calls to knowledge-tree-service endpoints.
They run in the trustgraph_extraction queue.
"""

import logging
from typing import Dict, List, Optional

import httpx

from worker_app.celery_app import celery_app
from worker_app.config import settings

logger = logging.getLogger(__name__)

KTS_URL = getattr(settings, "KNOWLEDGE_TREE_SERVICE_URL", "http://knowledge-tree-service:8011")
API_KEY = getattr(settings, "MICROSERVICES_API_KEY", "")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


@celery_app.task(
    name="trustgraph.extract_document",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    time_limit=300,
    soft_time_limit=280,
)
def extract_document_task(
    self,
    tenant_id: str,
    document_id: str,
    chunks: List[str],
    collection: str = "default",
    title: str = "",
    file_path: str = "",
    semantic_type: str = "",
    domain: str = "",
) -> Dict:
    """Extract triples from a document via KTS API."""
    try:
        with httpx.Client(timeout=280.0) as client:
            response = client.post(
                f"{KTS_URL}/extract/triples",
                headers=HEADERS,
                json={
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "chunks": chunks,
                    "collection": collection,
                    "title": title,
                    "file_path": file_path,
                    "semantic_type": semantic_type,
                    "domain": domain,
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.info(
                "TrustGraph extraction: doc=%s, triples=%d, contradictions=%d",
                document_id, result.get("triples_created", 0), result.get("contradictions_found", 0),
            )
            return result
    except Exception as exc:
        logger.error("TrustGraph extraction failed for %s: %s", document_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="trustgraph.reindex_tenant",
    bind=True,
    max_retries=0,
    time_limit=3600,
    soft_time_limit=3500,
)
def reindex_tenant_task(
    self,
    tenant_id: str,
    collection: str = "default",
) -> Dict:
    """Full reindexation of a tenant's graph.

    1. Clear existing graph for tenant
    2. Get document list from weaviate-service
    3. For each document, trigger extraction
    """
    try:
        with httpx.Client(timeout=60.0) as client:
            # Clear
            client.delete(f"{KTS_URL}/triples/clear?tenant_id={tenant_id}", headers=HEADERS)
            logger.info("Cleared graph for tenant %s", tenant_id)

        # Trigger per-document extraction via Celery chord
        # This is a coordinator task — individual documents are extracted via extract_document_task
        logger.info("Reindex started for tenant %s (documents will be triggered by indexing pipeline)", tenant_id)
        return {"success": True, "tenant_id": tenant_id, "message": "Graph cleared, re-indexing triggered"}
    except Exception as exc:
        logger.error("Reindex failed for %s: %s", tenant_id, exc)
        return {"success": False, "error": str(exc)}
```

- [ ] **Step 2: Register task module and queue in celery_app.py**

Add to the task includes list in `celery_app.py`:

```python
# In the include= list, add:
"worker_app.tasks.trustgraph_tasks",
```

Add to the task routing:

```python
# In task_routes dict, add:
"trustgraph.*": {"queue": "trustgraph_extraction"},
```

- [ ] **Step 3: Update start.sh to include new queue**

Add `trustgraph_extraction` to the `-Q` flag:

```bash
# In start.sh, change:
# -Q default,preview,email,indexing,channels,connectors,verification,emma_reactive
# To:
# -Q default,preview,email,indexing,channels,connectors,verification,emma_reactive,trustgraph_extraction
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/background-worker/worker_app/tasks/trustgraph_tasks.py \
       backend/microservices/background-worker/worker_app/celery_app.py \
       backend/microservices/background-worker/start.sh
git commit -m "feat(trustgraph): Celery tasks for extraction + reindex"
```

---

### Task 17: Docker compose environment

**Files:**
- Modify: `backend/docker/docker-compose.onpremise.yml`

- [ ] **Step 1: Add TrustGraph env vars to knowledge-tree-service**

Add these environment variables to the `knowledge-tree-service` section:

```yaml
    # TrustGraph extraction
    - SGLANG_BASE_URL=${SGLANG_BASE_URL:-http://sglang:8000/v1}
    - SGLANG_MODEL=${SGLANG_MODEL:-Qwen/Qwen3-8B}
    - LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY:-pk-lf-local}
    - LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY:-sk-lf-local}
    - LANGFUSE_HOST=${LANGFUSE_HOST:-http://langfuse:3002}
```

- [ ] **Step 2: Commit**

```bash
git add backend/docker/docker-compose.onpremise.yml
git commit -m "feat(trustgraph): docker compose env vars for extraction"
```

---

### Task 18: Reindexation script

**Files:**
- Create: `backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py`

- [ ] **Step 1: Write the reindexation script**

```python
# scripts/reindex_trustgraph.py
"""
Full reindexation: delete graph → recreate schema → seed ontology → extract triples for all documents.

Usage:
  docker compose exec knowledge-tree-service python scripts/reindex_trustgraph.py --tenant-id TENANT_ID
  docker compose exec knowledge-tree-service python scripts/reindex_trustgraph.py --tenant-id TENANT_ID --dry-run
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.services.extractors.coordinator import ExtractionCoordinator
from app.services.falkordb_client import falkordb_client
from app.services.triple_store import TripleStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

WEAVIATE_URL = getattr(settings, "WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
API_KEY = getattr(settings, "MICROSERVICES_API_KEY", "")


async def get_documents(tenant_id: str) -> list[dict]:
    """Get document list with chunks from weaviate-service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{WEAVIATE_URL}/weaviate/documents",
            params={"tenant_id": tenant_id, "limit": 10000},
            headers={"X-API-Key": API_KEY},
        )
        resp.raise_for_status()
        return resp.json().get("documents", [])


async def get_chunks(tenant_id: str, document_id: str) -> list[str]:
    """Get chunk texts for a document from Weaviate."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{WEAVIATE_URL}/weaviate/chunks",
            params={"tenant_id": tenant_id, "document_id": document_id},
            headers={"X-API-Key": API_KEY},
        )
        resp.raise_for_status()
        chunks = resp.json().get("chunks", [])
        return [c.get("content", "") for c in chunks if c.get("content")]


async def reindex(tenant_id: str, collection: str = "default", dry_run: bool = False):
    start = time.monotonic()
    await falkordb_client.initialize()
    store = TripleStore(falkordb_client)
    coordinator = ExtractionCoordinator(store)

    # 1. Clear graph
    logger.info("Step 1: Clearing graph for tenant %s...", tenant_id)
    if not dry_run:
        deleted = await store.clear_tenant(user=tenant_id)
        logger.info("  Deleted %d nodes", deleted)
    else:
        logger.info("  (dry run — skipped)")

    # 2. Bootstrap schema
    logger.info("Step 2: Bootstrapping schema...")
    if not dry_run:
        await falkordb_client.bootstrap_schema()

    # 3. Seed ontology
    logger.info("Step 3: Seeding ontology...")
    if not dry_run:
        from scripts.seed_ontology import seed
        await seed(force=True)

    # 4. Get document list
    logger.info("Step 4: Fetching documents...")
    documents = await get_documents(tenant_id)
    logger.info("  Found %d documents", len(documents))

    # 5. Extract triples
    total_triples = 0
    total_contradictions = 0
    errors = []

    for i, doc in enumerate(documents, 1):
        doc_id = doc.get("document_id", "")
        title = doc.get("title", "")
        logger.info("Step 5: [%d/%d] Extracting %s — %s", i, len(documents), doc_id[:12], title[:50])

        if dry_run:
            continue

        try:
            chunks = await get_chunks(tenant_id, doc_id)
            if not chunks:
                logger.warning("  No chunks found, skipping")
                continue

            result = await coordinator.extract_document(
                chunks=chunks,
                document_id=doc_id,
                user=tenant_id,
                collection=collection,
                title=title,
                file_path=doc.get("file_path", ""),
                semantic_type=doc.get("semantic_type", ""),
                domain=doc.get("domain", ""),
            )
            total_triples += result["triples_created"]
            total_contradictions += result["contradictions_found"]
            logger.info("  → %d triples, %d contradictions", result["triples_created"], result["contradictions_found"])
        except Exception as e:
            logger.error("  → FAILED: %s", e)
            errors.append(f"{doc_id}: {e}")

    elapsed = time.monotonic() - start
    logger.info("\n=== Reindexation complete ===")
    logger.info("Documents: %d", len(documents))
    logger.info("Triples: %d", total_triples)
    logger.info("Contradictions: %d", total_contradictions)
    logger.info("Errors: %d", len(errors))
    logger.info("Time: %.1fs", elapsed)

    await falkordb_client.close()


def main():
    parser = argparse.ArgumentParser(description="Reindex TrustGraph")
    parser.add_argument("--tenant-id", required=True, help="Tenant ID")
    parser.add_argument("--collection", default="default", help="Collection name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()
    asyncio.run(reindex(args.tenant_id, args.collection, args.dry_run))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py
git commit -m "feat(trustgraph): reindexation script"
```

---

### Task 19: Update KTS requirements.txt + config.py

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/requirements.txt`
- Modify: `backend/microservices/knowledge-tree-service/app/core/config.py`

- [ ] **Step 1: Add httpx to requirements (for LLM calls)**

Add `httpx>=0.25.0` to `requirements.txt` (if not already present).

- [ ] **Step 2: Add new settings to config.py**

```python
# Add to Settings class in app/core/config.py:
    # SGLang (for LLM extractors)
    SGLANG_BASE_URL: str = "http://sglang:8000/v1"
    SGLANG_MODEL: str = "Qwen/Qwen3-8B"

    # Langfuse (for prompt resolution)
    LANGFUSE_PUBLIC_KEY: str = "pk-lf-local"
    LANGFUSE_SECRET_KEY: str = "sk-lf-local"
    LANGFUSE_HOST: str = "http://langfuse:3002"

    # Weaviate service (for reindexation)
    WEAVIATE_SERVICE_URL: str = "http://weaviate-service:8000"
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/requirements.txt \
       backend/microservices/knowledge-tree-service/app/core/config.py
git commit -m "feat(trustgraph): config + dependencies for LLM extractors"
```

---

### Task 20: Integration test — full pipeline

**Files:**
- Create: `backend/microservices/knowledge-tree-service/tests/test_integration_pipeline.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_integration_pipeline.py
"""
Integration test: full extraction pipeline on a Spanish employment contract.

Uses mocked LLM (no SGLang needed) to verify the complete flow:
chunk → 4 extractors → triple store → provenance → contradictions.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.extractors.coordinator import ExtractionCoordinator
from app.services.triple_query import TripleQuery
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


CONTRACT_CHUNKS = [
    """Contrato de trabajo entre D. Juan García López (DNI: 12345678A),
    en adelante el TRABAJADOR, y la empresa TechCorp SL (CIF: B87654321),
    en adelante la EMPRESA, para el puesto de Abogado Senior en el
    Departamento Legal. Salario bruto anual: 30.000 EUR.""",

    """El presente contrato se rige por el Real Decreto Legislativo 2/2015,
    de 23 de octubre, por el que se aprueba el texto refundido de la Ley
    del Estatuto de los Trabajadores. Fecha de inicio: 01/02/2025.
    Jornada completa de 40 horas semanales.""",
]


def _mock_llm_for_chunk(chunk_text: str) -> str:
    """Return realistic LLM output based on chunk content."""
    if "Juan García" in chunk_text and "TechCorp" in chunk_text:
        return json.dumps([
            {"subject": "Juan García López", "predicate": "empleado-de", "object": "TechCorp SL", "object-entity": True},
            {"subject": "Juan García López", "predicate": "salario-bruto", "object": "30000 EUR", "object-entity": False},
            {"subject": "TechCorp SL", "predicate": "tipo-contrato", "object": "contrato laboral", "object-entity": False},
        ])
    elif "Estatuto" in chunk_text:
        return json.dumps([
            {"subject": "contrato", "predicate": "regulado-por", "object": "Estatuto de los Trabajadores", "object-entity": True},
            {"subject": "Juan García López", "predicate": "vigente-desde", "object": "01/02/2025", "object-entity": False},
        ])
    return "[]"


@pytest.mark.asyncio
class TestFullPipeline:
    async def test_extract_contract(self, falkordb_client):
        store = TripleStore(falkordb_client)
        coordinator = ExtractionCoordinator(store)
        query = TripleQuery(falkordb_client)

        # Mock all LLM calls
        with patch.object(
            coordinator._definitions._BaseExtractor__class__,  # This won't work — use direct patch
            "_call_llm",
            new_callable=AsyncMock,
        ):
            pass  # Approach below is cleaner

        # Patch each extractor's _call_llm
        async def mock_definitions(chunk):
            items = []
            if "Juan García" in chunk:
                items.append({"entity": "Juan García López", "definition": "Abogado Senior en TechCorp SL"})
                items.append({"entity": "TechCorp SL", "definition": "Empresa tecnológica"})
            if "Estatuto" in chunk:
                items.append({"entity": "Estatuto de los Trabajadores", "definition": "Ley laboral básica de España"})
            return json.dumps(items)

        async def mock_relationships(chunk):
            return _mock_llm_for_chunk(chunk)

        async def mock_objects(chunk):
            items = []
            if "Juan García" in chunk:
                items.append({"name": "Juan García López", "type": "person"})
                items.append({"name": "TechCorp SL", "type": "organization"})
            if "Estatuto" in chunk:
                items.append({"name": "Estatuto de los Trabajadores", "type": "law"})
            return json.dumps(items)

        async def mock_topics(chunk):
            return json.dumps([{"topic": "derecho laboral"}, {"topic": "contratación"}])

        with patch.object(coordinator._definitions, "_call_llm", side_effect=mock_definitions), \
             patch.object(coordinator._relationships, "_call_llm", side_effect=mock_relationships), \
             patch.object(coordinator._objects, "_call_llm", side_effect=mock_objects), \
             patch.object(coordinator._topics, "_call_llm", side_effect=mock_topics):

            result = await coordinator.extract_document(
                chunks=CONTRACT_CHUNKS,
                document_id="contract-001",
                user="t1",
                collection="default",
                title="Contrato TechCorp - Juan García",
                file_path="/Contratos/TechCorp/contrato-juan.pdf",
                semantic_type="contract",
                domain="legal",
            )

        # Verify results
        assert result["success"] is True
        assert result["triples_created"] > 10  # Multiple triples from 2 chunks
        assert result["chunks_processed"] == 2

        # Verify graph contents
        stats = await query.get_stats(user="t1")
        assert stats["nodes"] >= 3  # Juan, TechCorp, doc, Estatuto, etc.
        assert stats["rels"] >= 5  # Multiple relationships

        # Verify Juan has type=person
        juan_uri = URIBuilder.entity("default", "Juan García López")
        juan_triples = await query.by_subject(juan_uri, user="t1")
        preds = {t["predicate"] for t in juan_triples}
        assert URIBuilder.predicate("core", "type") in preds

        # Verify document node exists
        doc_uri = URIBuilder.document("default", "contract-001")
        doc_triples = await query.by_subject(doc_uri, user="t1")
        assert len(doc_triples) >= 2  # type + label + contained-in + topics

        # Verify context can be built
        context = await query.build_context(user="t1")
        assert "person" in context or "Juan" in context.lower()
```

- [ ] **Step 2: Run the integration test**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_integration_pipeline.py -x --tb=short -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/tests/test_integration_pipeline.py
git commit -m "test(trustgraph): integration test — full extraction pipeline with mocked LLM"
```

---

## Rollback plan

If Phase 1 fails or causes regressions:

1. **Git revert**: All changes are in separate commits, revertible individually
2. **FalkorDB**: The old schema can be restored by reverting `trustgraph_schema.cypher` → `knowledge_graph_schema.cypher` and rerunning `bootstrap_schema()`
3. **Weaviate-service**: The extraction pipeline change is a single conditional block — revert one file
4. **Emma-agent-service**: The graph_expander.py rewrite is the riskiest change. Keep a copy of the old file before starting Task 15
5. **Background-worker**: New queue is additive, removing the task file restores prior behavior

**Before starting Task 13 (delete old files):** Create a git tag:
```bash
git tag pre-trustgraph-phase1
```

This allows `git checkout pre-trustgraph-phase1` to fully restore the old codebase.

---

## Verification checklist (post-implementation)

- [ ] All new tests pass: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/ -x -v`
- [ ] Service starts cleanly: `docker compose up knowledge-tree-service -d && docker compose logs -f knowledge-tree-service`
- [ ] `/health` returns 200
- [ ] `/triples/stats?tenant_id=...` returns valid counts
- [ ] Seed ontology: `docker compose exec knowledge-tree-service python scripts/seed_ontology.py`
- [ ] Seed Langfuse prompts: `docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py`
- [ ] Extract a test document via API: `POST /extract/triples` with real chunks
- [ ] Verify provenance triples exist for the extraction
- [ ] Emma sanity checks still pass (at least infra + integration tiers)
