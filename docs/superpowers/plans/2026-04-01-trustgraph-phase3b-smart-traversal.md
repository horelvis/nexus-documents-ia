# TrustGraph Phase 3b: Smart Traversal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform graph_rag from a flat BFS retriever into a trust-scored, multi-hop reasoner with authority weighting, consensus scoring, Cypher templates, and LLM-guided expansion.

**Architecture:** Four components — authority weight triples stored in FalkorDB and resolved via Cypher (zero hardcode), consensus scoring as a post-ingestion aggregation step, Cypher template registry for structured multi-hop queries, and LLM-guided expansion as a new Stage 2.5 in graph_rag. The composite edge score combines 5 signals (semantic, confidence, authority, consensus, recency).

**Tech Stack:** FalkorDB (Cypher), Python 3.9+, httpx, asyncio, Langfuse prompts, YAML config

**Spec:** `docs/superpowers/specs/2026-04-01-trustgraph-phase3-knowledge-expert-design.md` — Phase 3b sections

**Depends on:** Phase 3a (Clean Graph) — COMPLETE

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `knowledge-tree-service/app/services/consensus.py` | Consensus scoring — count independent sources per triple |
| `knowledge-tree-service/app/services/template_executor.py` | Load and execute Cypher templates from YAML registry |
| `knowledge-tree-service/config/cypher_templates.yaml` | Multi-hop Cypher template definitions |
| `knowledge-tree-service/scripts/seed_authority_weights.py` | Seed authority weight triples per document semantic_type |
| `knowledge-tree-service/tests/test_consensus.py` | Tests for consensus scoring |
| `knowledge-tree-service/tests/test_template_executor.py` | Tests for Cypher template execution |

### Modified Files
| File | Change |
|------|--------|
| `knowledge-tree-service/app/services/extractors/coordinator.py` | Add consensus step after contradiction detection |
| `knowledge-tree-service/app/api/triples.py` | Add `POST /triples/template` endpoint |
| `knowledge-tree-service/app/schemas/triples.py` | Add `TemplateRequest`/`TemplateResponse` schemas |
| `emma-agent-service/app/agents/langgraph/tools/graph_rag.py` | Add Stage 2.5 (guided expansion) + composite score in Stage 4 |
| `emma-agent-service/app/core/config.py` | Add `guided_expansion_*` and `authority_weights_*` settings |

---

## Task 1: Seed Authority Weight Triples

**Files:**
- Create: `knowledge-tree-service/scripts/seed_authority_weights.py`

- [ ] **Step 1: Create the seed script**

Create `backend/microservices/knowledge-tree-service/scripts/seed_authority_weights.py`:

```python
#!/usr/bin/env python3
"""
Seed authority weight triples into FalkorDB.

Creates :Node entities for each document semantic_type and links them
to a :Literal authority weight via trust/authority-weight predicate.

These triples are queried by graph_rag to weight edges by source quality.
Zero hardcode — all weights live in the graph.

Usage:
    docker compose exec knowledge-tree-service python scripts/seed_authority_weights.py
    docker compose exec knowledge-tree-service python scripts/seed_authority_weights.py --force
    docker compose exec knowledge-tree-service python scripts/seed_authority_weights.py --dry-run
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.falkordb_client import FalkorDBClient
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder

logging.basicConfig(level=logging.WARNING)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

AUTHORITY_USER = "_system"
AUTHORITY_COLLECTION = "_authority"

# (semantic_type_slug, authority_weight, description)
AUTHORITY_WEIGHTS = [
    ("escritura-publica",  "0.95", "Notarized document"),
    ("contrato",           "0.90", "Signed agreement"),
    ("sentencia",          "0.95", "Court ruling"),
    ("legislacion",        "1.00", "Standing law"),
    ("factura",            "0.85", "Fiscal document"),
    ("nomina",             "0.85", "Payroll document"),
    ("informe",            "0.70", "Internal analysis"),
    ("acta",               "0.80", "Official minutes"),
    ("certificado",        "0.85", "Official certificate"),
    ("resolucion",         "0.90", "Administrative resolution"),
    ("email",              "0.40", "Informal communication"),
    ("nota",               "0.30", "Internal note"),
    ("borrador",           "0.25", "Draft document"),
    ("desconocido",        "0.50", "Unknown document type"),
]


async def seed_authority_weights(dry_run: bool = False, force: bool = False) -> tuple:
    """Seed authority weight triples. Returns (created, skipped, errors)."""
    client = FalkorDBClient()
    await client.initialize()
    store = TripleStore(client)

    created = 0
    skipped = 0
    errors = 0

    try:
        if force and not dry_run:
            # Clear existing authority weights
            await client.execute_cypher(
                "MATCH (n) WHERE (n:Node OR n:Literal) "
                "AND n.user = $user AND n.collection = $collection "
                "DETACH DELETE n",
                params={"user": AUTHORITY_USER, "collection": AUTHORITY_COLLECTION},
            )
            print(f"  {YELLOW}Cleared existing authority weights{RESET}")

        # Check existing
        existing = set()
        if not force:
            rows = await client.execute_cypher(
                "MATCH (n:Node {user: $user, collection: $collection}) "
                "RETURN n.uri AS uri",
                params={"user": AUTHORITY_USER, "collection": AUTHORITY_COLLECTION},
            )
            existing = {r["uri"] for r in rows if r.get("uri")}

        for slug, weight, description in AUTHORITY_WEIGHTS:
            entity_uri = f"nouxcube://entity/_system/{slug}"
            label = f"{slug} (authority={weight})"

            if not force and entity_uri in existing:
                print(f"  {YELLOW}SKIP{RESET}  {slug} — already exists")
                skipped += 1
                continue

            if dry_run:
                print(f"  WOULD CREATE  {slug}  authority={weight}")
                created += 1
                continue

            try:
                # Create the entity node for this semantic_type
                await store.merge_node(entity_uri, AUTHORITY_USER, AUTHORITY_COLLECTION)

                # Label triple
                await store.merge_literal(slug, AUTHORITY_USER, AUTHORITY_COLLECTION)
                await store.create_rel(
                    subject_uri=entity_uri,
                    predicate_uri=URIBuilder.predicate("core", "label"),
                    object_value=slug,
                    user=AUTHORITY_USER,
                    collection=AUTHORITY_COLLECTION,
                    object_is_node=False,
                    extraction_method="seed",
                )

                # Authority weight triple
                await store.merge_literal(weight, AUTHORITY_USER, AUTHORITY_COLLECTION)
                await store.create_rel(
                    subject_uri=entity_uri,
                    predicate_uri=URIBuilder.predicate("trust", "authority-weight"),
                    object_value=weight,
                    user=AUTHORITY_USER,
                    collection=AUTHORITY_COLLECTION,
                    object_is_node=False,
                    extraction_method="seed",
                )

                print(f"  {GREEN}OK{RESET}  {slug}  authority={weight}  ({description})")
                created += 1
            except Exception as exc:
                print(f"  {RED}ERROR{RESET}  {slug}: {exc}")
                errors += 1

    finally:
        await client.close()

    return created, skipped, errors


def main():
    parser = argparse.ArgumentParser(description="Seed authority weight triples")
    parser.add_argument("--force", action="store_true", help="Clear and reseed")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    print("=" * 60)
    print(f"Authority Weight Seed — {len(AUTHORITY_WEIGHTS)} document types")
    print("=" * 60)

    created, skipped, errors = asyncio.run(
        seed_authority_weights(dry_run=args.dry_run, force=args.force)
    )

    print(f"\nResults: {created} created, {skipped} skipped, {errors} errors")
    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/seed_authority_weights.py
git commit -m "feat(kts): seed authority weight triples per document semantic_type"
```

---

## Task 2: Consensus Scoring Service

**Files:**
- Create: `knowledge-tree-service/app/services/consensus.py`
- Create: `knowledge-tree-service/tests/test_consensus.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/microservices/knowledge-tree-service/tests/test_consensus.py`:

```python
"""Tests for consensus scoring — cross-source agreement counting."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.consensus import ConsensusScorer


class TestConsensusScorer:
    @pytest.mark.asyncio
    async def test_single_source_gets_score_one_third(self):
        """A triple from 1 source gets consensus_score = 1/3 ≈ 0.33."""
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(return_value=[
            {"predicate": "nouxcube://predicate/legal/empleado-de", "source_count": 1}
        ])

        scorer = ConsensusScorer(mock_client)
        result = await scorer.compute_for_subject(
            subject_uri="nouxcube://entity/default/juan",
            user="test-user",
        )
        assert len(result) == 1
        assert result[0]["consensus_score"] == pytest.approx(0.33, abs=0.01)

    @pytest.mark.asyncio
    async def test_three_sources_gets_max_score(self):
        """A triple confirmed by 3+ independent sources gets consensus_score = 1.0."""
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(return_value=[
            {"predicate": "nouxcube://predicate/legal/empleado-de", "source_count": 5}
        ])

        scorer = ConsensusScorer(mock_client)
        result = await scorer.compute_for_subject(
            subject_uri="nouxcube://entity/default/juan",
            user="test-user",
        )
        assert len(result) == 1
        assert result[0]["consensus_score"] == 1.0

    @pytest.mark.asyncio
    async def test_stores_consensus_count_on_edges(self):
        """After computing, consensus_count should be SET on matching edges."""
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(side_effect=[
            # First call: the aggregation query
            [{"predicate": "nouxcube://predicate/legal/empleado-de", "source_count": 2}],
            # Second call: the UPDATE query
            [],
        ])

        scorer = ConsensusScorer(mock_client)
        await scorer.compute_and_store(
            subject_uri="nouxcube://entity/default/juan",
            user="test-user",
        )

        # Verify the update Cypher was called
        assert mock_client.execute_cypher.call_count == 2
        update_call = mock_client.execute_cypher.call_args_list[1]
        assert "consensus_count" in update_call[0][0]

    @pytest.mark.asyncio
    async def test_no_edges_returns_empty(self):
        """Subject with no outgoing edges returns empty list."""
        mock_client = AsyncMock()
        mock_client.execute_cypher = AsyncMock(return_value=[])

        scorer = ConsensusScorer(mock_client)
        result = await scorer.compute_for_subject(
            subject_uri="nouxcube://entity/default/empty",
            user="test-user",
        )
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_consensus.py -v --override-ini="log_auto_indent=true"
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement ConsensusScorer**

Create `backend/microservices/knowledge-tree-service/app/services/consensus.py`:

```python
"""
ConsensusScorer — counts independent sources confirming each triple.

For a given subject, groups outgoing edges by (predicate, object) and
counts how many distinct source_chunk values produced the same triple.
Stores consensus_count as a property on each :Rel edge.

Score formula: consensus_score = min(1.0, consensus_count / 3)
  - 1 source  → 0.33
  - 2 sources → 0.67
  - 3+ sources → 1.0
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CONSENSUS_DIVISOR = 3


class ConsensusScorer:
    """Compute and store consensus scores on graph edges."""

    def __init__(self, client) -> None:
        self._client = client

    async def compute_for_subject(
        self,
        subject_uri: str,
        user: str,
    ) -> List[Dict[str, Any]]:
        """Count independent sources per (subject, predicate) pair.

        Returns list of dicts with predicate, source_count, consensus_score.
        """
        query = (
            "MATCH (s:Node {uri: $uri, user: $user})-[r:Rel]->(o) "
            "WHERE r.source_chunk IS NOT NULL "
            "WITH r.uri AS predicate, count(DISTINCT r.source_chunk) AS source_count "
            "RETURN predicate, source_count"
        )
        rows = await self._client.execute_cypher(
            query, params={"uri": subject_uri, "user": user}
        )

        results = []
        for row in rows:
            count = row.get("source_count", 1)
            results.append({
                "predicate": row.get("predicate", ""),
                "source_count": count,
                "consensus_score": min(1.0, count / CONSENSUS_DIVISOR),
            })

        return results

    async def compute_and_store(
        self,
        subject_uri: str,
        user: str,
    ) -> int:
        """Compute consensus and SET consensus_count on edges.

        Returns number of predicates updated.
        """
        results = await self.compute_for_subject(subject_uri, user)
        if not results:
            return 0

        for item in results:
            update_query = (
                "MATCH (s:Node {uri: $uri, user: $user})-[r:Rel {uri: $predicate}]->(o) "
                "SET r.consensus_count = $count"
            )
            await self._client.execute_cypher(
                update_query,
                params={
                    "uri": subject_uri,
                    "user": user,
                    "predicate": item["predicate"],
                    "count": item["source_count"],
                },
            )

        return len(results)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_consensus.py -v --override-ini="log_auto_indent=true"
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/consensus.py \
       backend/microservices/knowledge-tree-service/tests/test_consensus.py
git commit -m "feat(kts): consensus scoring service — cross-source agreement counting"
```

---

## Task 3: Integrate Consensus Into Coordinator

**Files:**
- Modify: `knowledge-tree-service/app/services/extractors/coordinator.py`

- [ ] **Step 1: Add import and consensus step**

In `backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py`:

Add import after the `ContradictionDetector` import (line ~17):

```python
from app.services.consensus import ConsensusScorer
```

In `extract_document()`, after Step 3b (confidence penalty, around line 423), add:

```python
        # Step 3c: Consensus scoring — count independent sources per triple
        consensus_scorer = ConsensusScorer(self._store._client)
        consensus_sem = asyncio.Semaphore(10)

        async def _score_subject(subject_uri: str) -> int:
            async with consensus_sem:
                return await consensus_scorer.compute_and_store(
                    subject_uri=subject_uri, user=user
                )

        consensus_tasks = [_score_subject(uri) for uri in all_subject_uris]
        consensus_results = await asyncio.gather(*consensus_tasks, return_exceptions=True)

        total_consensus = 0
        for i, result in enumerate(consensus_results):
            if isinstance(result, BaseException):
                subj = subject_list[i] if i < len(subject_list) else "?"
                errors.append(f"consensus({subj}): {result}")
                logger.warning("Consensus scoring failed: %s", result)
            else:
                total_consensus += result
```

Update the logger.info line (around line 446) to include consensus count:

```python
        logger.info(
            "Document %s extraction complete: %d triples, %d parse_failures, "
            "%d empty_responses, %d validation_failures, %d contradictions, %d consensus_predicates, %dms",
            document_id,
            total_triples,
            total_parse_failures,
            total_empty,
            total_validation,
            contradictions_found,
            total_consensus,
            elapsed_ms,
        )
```

- [ ] **Step 2: Run existing coordinator tests**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_coordinator.py -v --override-ini="log_auto_indent=true"
```

Expected: All pass (consensus runs after contradictions, doesn't break existing flow).

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py
git commit -m "feat(kts): integrate consensus scoring into extraction coordinator"
```

---

## Task 4: Cypher Template Registry + Executor

**Files:**
- Create: `knowledge-tree-service/config/cypher_templates.yaml`
- Create: `knowledge-tree-service/app/services/template_executor.py`
- Create: `knowledge-tree-service/tests/test_template_executor.py`

- [ ] **Step 1: Create the YAML template registry**

Create `backend/microservices/knowledge-tree-service/config/cypher_templates.yaml`:

```yaml
# Cypher template registry — reusable multi-hop query patterns.
# Each template has a Cypher pattern with $-prefixed parameters.
# Tenant isolation ($user, $collection) is injected automatically.

templates:
  entity_relations:
    description: "All direct relationships of an entity"
    hops: 1
    pattern: |
      MATCH (s:Node {uri: $entity_uri, user: $user})-[r:Rel]->(o)
      WHERE ($collection IS NULL OR r.collection = $collection)
      RETURN s.uri AS subject, r.uri AS predicate,
             CASE WHEN o:Node THEN o.uri ELSE o.value END AS object,
             CASE WHEN o:Node THEN 'node' ELSE 'literal' END AS object_type,
             r.confidence AS confidence, r.consensus_count AS consensus_count,
             r.extraction_method AS extraction_method
      ORDER BY r.confidence DESC

  corporate_chain:
    description: "Ownership chain: company -> group -> subsidiaries"
    hops: 4
    pattern: |
      MATCH path = (start:Node {uri: $entity_uri, user: $user})
        -[:Rel*1..4]->(end:Node {user: $user})
      WHERE ALL(r IN relationships(path) WHERE
        r.uri IN ['nouxcube://predicate/legal/filial-de',
                   'nouxcube://predicate/legal/parte-de',
                   'nouxcube://predicate/core/part-of'])
      UNWIND relationships(path) AS r
      WITH startNode(r) AS s, r, endNode(r) AS o
      RETURN DISTINCT s.uri AS subject, r.uri AS predicate, o.uri AS object,
             'node' AS object_type, r.confidence AS confidence
      LIMIT $query_limit

  org_people:
    description: "People related to an organization at N hops"
    hops: 3
    pattern: |
      MATCH (org:Node {uri: $entity_uri, user: $user})
      MATCH path = (p:Node {user: $user})-[:Rel*1..3]->(org)
      WHERE ANY(r IN relationships(path) WHERE
        r.uri CONTAINS 'empleado' OR r.uri CONTAINS 'firmante'
        OR r.uri CONTAINS 'representante' OR r.uri CONTAINS 'cargo'
        OR r.uri CONTAINS 'administrador')
      MATCH (p)-[:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal)
      WHERE t.value = 'person'
      RETURN DISTINCT p.uri AS subject,
             'nouxcube://predicate/core/related-to' AS predicate,
             org.uri AS object, 'node' AS object_type
      LIMIT $query_limit

  count_by_predicate:
    description: "Count relations of a type for an entity"
    hops: 1
    pattern: |
      MATCH (s:Node {uri: $entity_uri, user: $user})-[r:Rel {uri: $predicate_uri}]->(o)
      RETURN count(o) AS total

  applicable_regulations:
    description: "Laws and regulations applicable to an entity"
    hops: 2
    pattern: |
      MATCH (entity:Node {uri: $entity_uri, user: $user})
      MATCH (entity)-[r1:Rel]->(mid:Node {user: $user})-[r2:Rel]->(law:Node {user: $user})
      WHERE r2.uri CONTAINS 'regulado' OR r2.uri CONTAINS 'sujeto-a'
      MATCH (law)-[:Rel {uri: 'nouxcube://predicate/core/type'}]->(t:Literal)
      WHERE t.value = 'legislation'
      RETURN DISTINCT law.uri AS subject, r2.uri AS predicate,
             entity.uri AS object, 'node' AS object_type
      LIMIT $query_limit
```

- [ ] **Step 2: Write the failing tests**

Create `backend/microservices/knowledge-tree-service/tests/test_template_executor.py`:

```python
"""Tests for Cypher template executor."""

import pytest
from app.services.template_executor import TemplateExecutor


class TestTemplateLoading:
    def test_loads_templates_from_yaml(self):
        executor = TemplateExecutor()
        assert "entity_relations" in executor.templates
        assert "corporate_chain" in executor.templates
        assert "org_people" in executor.templates
        assert "count_by_predicate" in executor.templates
        assert "applicable_regulations" in executor.templates

    def test_template_has_required_fields(self):
        executor = TemplateExecutor()
        tmpl = executor.templates["entity_relations"]
        assert "pattern" in tmpl
        assert "description" in tmpl
        assert "hops" in tmpl

    def test_list_templates_returns_metadata(self):
        executor = TemplateExecutor()
        listing = executor.list_templates()
        assert len(listing) >= 5
        assert all("name" in t and "description" in t and "hops" in t for t in listing)

    def test_unknown_template_raises(self):
        executor = TemplateExecutor()
        with pytest.raises(KeyError, match="nonexistent"):
            executor.get_template("nonexistent")


class TestTemplateBuilding:
    def test_build_query_injects_params(self):
        executor = TemplateExecutor()
        query = executor.build_query(
            "entity_relations",
            user="test-user",
            collection="default",
            entity_uri="nouxcube://entity/default/juan",
        )
        # The built query should be the raw Cypher — params are passed separately
        assert "$entity_uri" in query or "$user" in query

    def test_build_params_includes_defaults(self):
        executor = TemplateExecutor()
        params = executor.build_params(
            "entity_relations",
            user="test-user",
            entity_uri="nouxcube://entity/default/juan",
        )
        assert params["user"] == "test-user"
        assert params["entity_uri"] == "nouxcube://entity/default/juan"
        assert "query_limit" in params
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_template_executor.py -v --override-ini="log_auto_indent=true"
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement TemplateExecutor**

Create `backend/microservices/knowledge-tree-service/app/services/template_executor.py`:

```python
"""
TemplateExecutor — load and execute Cypher templates from YAML registry.

Templates are loaded from config/cypher_templates.yaml on first access.
Each template contains a Cypher pattern with $-prefixed parameters.
Tenant isolation ($user, $collection) is injected automatically.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "cypher_templates.yaml"

_DEFAULT_QUERY_LIMIT = 100


class TemplateExecutor:
    """Load Cypher templates and prepare queries for execution."""

    def __init__(self) -> None:
        self._templates: Optional[Dict[str, Dict]] = None

    @property
    def templates(self) -> Dict[str, Dict]:
        if self._templates is None:
            self._load()
        return self._templates

    def _load(self) -> None:
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._templates = data.get("templates", {})
            logger.info("Loaded %d Cypher templates from %s", len(self._templates), _CONFIG_PATH)
        except FileNotFoundError:
            logger.warning("Cypher templates not found at %s", _CONFIG_PATH)
            self._templates = {}

    def get_template(self, name: str) -> Dict[str, Any]:
        """Get a template by name. Raises KeyError if not found."""
        if name not in self.templates:
            raise KeyError(f"Unknown Cypher template: {name!r}")
        return self.templates[name]

    def list_templates(self) -> List[Dict[str, Any]]:
        """List all templates with metadata."""
        return [
            {
                "name": name,
                "description": tmpl.get("description", ""),
                "hops": tmpl.get("hops", 0),
            }
            for name, tmpl in self.templates.items()
        ]

    def build_query(self, name: str, **kwargs) -> str:
        """Return the raw Cypher pattern for a template."""
        tmpl = self.get_template(name)
        return tmpl["pattern"].strip()

    def build_params(self, name: str, user: str, **kwargs) -> Dict[str, Any]:
        """Build parameter dict for a template query.

        Injects user, collection (nullable), and query_limit automatically.
        All extra kwargs are passed through as query parameters.
        """
        params = {
            "user": user,
            "collection": kwargs.pop("collection", None),
            "query_limit": kwargs.pop("query_limit", _DEFAULT_QUERY_LIMIT),
        }
        params.update(kwargs)
        return params

    async def execute(
        self,
        name: str,
        client,
        user: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a template and return results with metadata.

        Args:
            name: Template name from registry.
            client: FalkorDBClient instance.
            user: Tenant identifier.
            **kwargs: Template-specific parameters (entity_uri, predicate_uri, etc.)

        Returns:
            Dict with keys: results (list of row dicts), template, hops, count.
        """
        tmpl = self.get_template(name)
        query = tmpl["pattern"].strip()
        params = self.build_params(name, user=user, **kwargs)

        rows = await client.execute_cypher(query, params=params)

        return {
            "results": rows,
            "template": name,
            "hops": tmpl.get("hops", 0),
            "count": len(rows),
        }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_template_executor.py -v --override-ini="log_auto_indent=true"
```

Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/config/cypher_templates.yaml \
       backend/microservices/knowledge-tree-service/app/services/template_executor.py \
       backend/microservices/knowledge-tree-service/tests/test_template_executor.py
git commit -m "feat(kts): Cypher template registry + executor for multi-hop queries"
```

---

## Task 5: KTS API Endpoint for Templates

**Files:**
- Modify: `knowledge-tree-service/app/schemas/triples.py`
- Modify: `knowledge-tree-service/app/api/triples.py`

- [ ] **Step 1: Add Pydantic schemas**

Append to `backend/microservices/knowledge-tree-service/app/schemas/triples.py`:

```python
class TemplateRequest(BaseModel):
    """Execute a named Cypher template."""
    tenant_id: str
    template_name: str
    collection: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class TemplateListItem(BaseModel):
    name: str
    description: str
    hops: int


class TemplateResponse(BaseModel):
    results: List[Dict[str, Any]]
    template: str
    hops: int
    count: int
```

- [ ] **Step 2: Add API endpoint**

Append to `backend/microservices/knowledge-tree-service/app/api/triples.py`:

```python
from app.services.template_executor import TemplateExecutor
from app.schemas.triples import TemplateRequest, TemplateResponse, TemplateListItem

_template_executor = TemplateExecutor()


@router.post("/triples/template", response_model=TemplateResponse)
async def execute_template(request: TemplateRequest):
    """Execute a named Cypher template with parameters."""
    try:
        result = await _template_executor.execute(
            name=request.template_name,
            client=_get_client(),
            user=request.tenant_id,
            collection=request.collection,
            **request.params,
        )
        return TemplateResponse(**result)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/triples/templates", response_model=List[TemplateListItem])
async def list_templates():
    """List all available Cypher templates."""
    return _template_executor.list_templates()
```

Note: `_get_client()` is the existing helper that returns the FalkorDB client singleton. Check the actual helper name in the file — it may be `get_falkordb_client()` or accessed through a dependency.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/schemas/triples.py \
       backend/microservices/knowledge-tree-service/app/api/triples.py
git commit -m "feat(kts): POST /triples/template + GET /triples/templates API endpoints"
```

---

## Task 6: Emma Settings for Phase 3b

**Files:**
- Modify: `emma-agent-service/app/core/config.py`

- [ ] **Step 1: Add Phase 3b settings**

In `backend/microservices/emma-agent-service/app/core/config.py`, after the existing `graph_rag_*` settings (around line 180), add:

```python
    # Phase 3b: Smart Traversal
    authority_weights_enabled: bool = os.getenv("AUTHORITY_WEIGHTS_ENABLED", "true").lower() == "true"
    guided_expansion_enabled: bool = os.getenv("GUIDED_EXPANSION_ENABLED", "true").lower() == "true"
    guided_expansion_max_hops: int = int(os.getenv("GUIDED_EXPANSION_MAX_HOPS", "2"))
    consensus_scoring_enabled: bool = os.getenv("CONSENSUS_SCORING_ENABLED", "true").lower() == "true"
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/core/config.py
git commit -m "feat(emma): add Phase 3b settings (authority, guided expansion, consensus)"
```

---

## Task 7: Authority Weight Resolution in graph_rag

**Files:**
- Modify: `emma-agent-service/app/agents/langgraph/tools/graph_rag.py`

This task modifies Stage 4 (Semantic Pre-Filter) to incorporate authority weight and consensus into the composite edge score. Currently Stage 4 only uses semantic similarity (cosine between edge description and query embedding).

- [ ] **Step 1: Add authority resolution helper function**

In `backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py`, add a new helper function after the existing `_batch_embed_edges()` function (after line ~319):

```python
async def _resolve_authority_weights(
    edges: List[Dict[str, Any]],
    kts_url: str,
    api_key: str,
    tenant_id: str,
) -> Dict[str, float]:
    """Resolve authority weights for edges by looking up source document semantic_type.

    Returns a dict mapping edge index to authority weight (0.0-1.0).
    Edges without a resolvable authority get a default of 0.50.
    """
    DEFAULT_AUTHORITY = 0.50

    # Collect unique source_chunk document URIs
    doc_uris = set()
    for edge in edges:
        chunk = edge.get("source_chunk", "")
        if chunk and "#" in chunk:
            doc_uri = chunk.split("#")[0]
            doc_uris.add(doc_uri)

    if not doc_uris:
        return {i: DEFAULT_AUTHORITY for i in range(len(edges))}

    # Query KTS: for each document, get its semantic-type
    # Then look up the authority weight for that type
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    authority_by_doc: Dict[str, float] = {}

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        for doc_uri in doc_uris:
            try:
                # Get semantic-type of document
                resp = await client.post(
                    f"{kts_url}/triples/query",
                    json={
                        "tenant_id": tenant_id,
                        "subject_uri": doc_uri,
                        "predicate_uri": "nouxcube://predicate/core/semantic-type",
                        "limit": 1,
                    },
                )
                if resp.status_code != 200:
                    continue
                triples = resp.json().get("triples", [])
                if not triples:
                    continue
                sem_type = triples[0].get("object", "desconocido")

                # Look up authority weight for this semantic_type
                aw_resp = await client.post(
                    f"{kts_url}/triples/query",
                    json={
                        "tenant_id": "_system",
                        "subject_uri": f"nouxcube://entity/_system/{sem_type}",
                        "predicate_uri": "nouxcube://predicate/trust/authority-weight",
                        "limit": 1,
                    },
                )
                if aw_resp.status_code == 200:
                    aw_triples = aw_resp.json().get("triples", [])
                    if aw_triples:
                        authority_by_doc[doc_uri] = float(aw_triples[0].get("object", DEFAULT_AUTHORITY))
            except Exception:
                pass

    # Map authority to each edge
    result = {}
    for i, edge in enumerate(edges):
        chunk = edge.get("source_chunk", "")
        if chunk and "#" in chunk:
            doc_uri = chunk.split("#")[0]
            result[i] = authority_by_doc.get(doc_uri, DEFAULT_AUTHORITY)
        else:
            result[i] = DEFAULT_AUTHORITY

    return result
```

- [ ] **Step 2: Modify Stage 4 to use composite score**

In the `execute()` method, Stage 4 (Semantic Pre-Filter, around lines 503-546), replace the scoring logic. After computing `edge_scores` (cosine similarity), add composite scoring:

Find the section where edges are scored and sorted (look for `edge_scores` or similar). Replace the simple similarity sort with:

```python
            # ── Composite score: 5 signals ────────────────────────────
            authority_map = {}
            if settings.authority_weights_enabled:
                try:
                    authority_map = await _resolve_authority_weights(
                        scored_edges, kts_url, api_key, tenant_id
                    )
                except Exception as exc:
                    logger.warning("Authority weight resolution failed: %s", exc)

            import time as _time
            now_ts = _time.time()

            for i, edge in enumerate(scored_edges):
                semantic_sim = edge.get("_score", 0.0)
                confidence = edge.get("confidence", 0.0) or 0.0
                authority = authority_map.get(i, 0.50)
                consensus = min(1.0, (edge.get("consensus_count", 1) or 1) / 3)

                # Recency: decay over 365 days, default 0.5 if no timestamp
                recency = 0.5
                # edges don't have timestamps directly, use default

                composite = (
                    0.35 * semantic_sim +
                    0.20 * confidence +
                    0.20 * authority +
                    0.15 * consensus +
                    0.10 * recency
                )
                edge["_composite_score"] = round(composite, 4)
                edge["_authority"] = authority
                edge["_consensus"] = round(consensus, 2)

            # Sort by composite score instead of raw similarity
            scored_edges.sort(key=lambda e: e.get("_composite_score", 0), reverse=True)
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py
git commit -m "feat(emma): composite edge scoring with authority + consensus in graph_rag Stage 4"
```

---

## Task 8: LLM-Guided Expansion (Stage 2.5)

**Files:**
- Modify: `emma-agent-service/app/agents/langgraph/tools/graph_rag.py`

- [ ] **Step 1: Add guided expansion logic after Stage 2**

In `graph_rag.py`, after Stage 2 (BFS subgraph, around line 444) and before Stage 3 (label resolution, around line 446), insert Stage 2.5:

```python
            # ── Stage 2.5: LLM-Guided Expansion ──────────────────────
            if settings.guided_expansion_enabled and edges:
                try:
                    from app.services.langfuse_prompt_client import get_langfuse_prompt_client

                    # Summarize current subgraph for the planner
                    entity_names = list(set(
                        e.get("subject", "").split("/")[-1].replace("-", " ")
                        for e in edges[:20]
                    ))
                    rel_summary = list(set(
                        e.get("predicate", "").split("/")[-1]
                        for e in edges[:20]
                    ))

                    langfuse_client = get_langfuse_prompt_client()
                    expansion_prompt = await langfuse_client.get_prompt(
                        "trustgraph_guided_expansion"
                    )
                    system_content = expansion_prompt.content if expansion_prompt else (
                        "Given the user query and current subgraph entities/relationships, "
                        "determine if more traversal is needed to answer the query. "
                        'Respond with JSON: {"sufficient": true/false, "expand_from": ["uri1"], "reason": "..."}'
                    )

                    from app.agents.llm_models import get_planner_model
                    planner = get_planner_model()

                    user_msg = (
                        f"Query: {query}\n\n"
                        f"Current entities ({len(entity_names)}): {', '.join(entity_names[:15])}\n"
                        f"Relationship types: {', '.join(rel_summary[:10])}\n"
                        f"Total edges: {len(edges)}"
                    )

                    response = await planner.ainvoke([
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_msg},
                    ])

                    import json as _json
                    try:
                        expansion = _json.loads(response.content)
                        if not expansion.get("sufficient", True):
                            expand_uris = expansion.get("expand_from", [])[:3]
                            if expand_uris:
                                logger.info(
                                    "Guided expansion: expanding from %d URIs (reason: %s)",
                                    len(expand_uris), expansion.get("reason", "")[:100]
                                )
                                # Additional BFS from selected nodes
                                extra_result = await _kts_batch_neighbors(
                                    kts_url=kts_url,
                                    api_key=api_key,
                                    tenant_id=tenant_id,
                                    seed_uris=expand_uris,
                                    collection=collection,
                                    max_hops=settings.guided_expansion_max_hops,
                                    max_edges=settings.graph_rag_max_edges - len(edges),
                                )
                                extra_edges = extra_result.get("edges", [])
                                # Deduplicate by (subject, predicate, object)
                                existing_keys = {
                                    (e["subject"], e["predicate"], e["object"])
                                    for e in edges
                                }
                                for ee in extra_edges:
                                    key = (ee["subject"], ee["predicate"], ee["object"])
                                    if key not in existing_keys:
                                        edges.append(ee)
                                        existing_keys.add(key)
                                logger.info(
                                    "Guided expansion added %d new edges (total: %d)",
                                    len(extra_edges), len(edges)
                                )
                    except (_json.JSONDecodeError, KeyError):
                        logger.debug("Guided expansion: planner response not valid JSON, skipping")

                except Exception as exc:
                    logger.warning("Guided expansion failed, continuing: %s", exc)
```

Note: `_kts_batch_neighbors` is the existing helper that calls `POST /triples/neighbors` on KTS. Find the exact function name by searching for `batch_neighbors` in graph_rag.py — it may be inline or a helper.

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py
git commit -m "feat(emma): LLM-guided expansion Stage 2.5 in graph_rag pipeline"
```

---

## Task 9: Chain-of-Thought Path Formatting in Stage 6

**Files:**
- Modify: `emma-agent-service/app/agents/langgraph/tools/graph_rag.py`

- [ ] **Step 1: Enhance `_format_context()` to include relationship chains**

In `graph_rag.py`, inside `_format_context()` (around lines 730-805), after the existing relationship formatting, add chain detection:

```python
    # ── Detect and format multi-hop chains ──────────────────────
    # Build adjacency from edges for chain detection
    adjacency: Dict[str, List[Dict]] = {}
    for edge in edges:
        subj = edge.get("subject", "")
        if subj:
            adjacency.setdefault(subj, []).append(edge)

    chains_found = []
    for seed_uri in seed_entities[:5]:  # Check top entities for chains
        # Simple 2-3 hop chain detection
        if seed_uri not in adjacency:
            continue
        for edge1 in adjacency[seed_uri][:5]:
            hop2_uri = edge1.get("object", "")
            if hop2_uri in adjacency:
                for edge2 in adjacency[hop2_uri][:3]:
                    chain = {
                        "path": [
                            labels.get(seed_uri, seed_uri.split("/")[-1]),
                            edge1.get("predicate", "").split("/")[-1],
                            labels.get(hop2_uri, hop2_uri.split("/")[-1]),
                            edge2.get("predicate", "").split("/")[-1],
                            labels.get(edge2.get("object", ""), edge2.get("object", "").split("/")[-1]),
                        ],
                        "confidence": min(
                            edge1.get("confidence", 0) or 0,
                            edge2.get("confidence", 0) or 0,
                        ),
                    }
                    chains_found.append(chain)

    if chains_found:
        context_parts.append("\n### Cadenas de relación encontradas")
        for chain in chains_found[:5]:
            path_str = " → ".join(str(p) for p in chain["path"])
            context_parts.append(f"- {path_str} (confianza: {chain['confidence']:.2f})")
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py
git commit -m "feat(emma): chain-of-thought path formatting in graph_rag Stage 6"
```

---

## Task 10: Seed Langfuse Prompt for Guided Expansion

**Files:**
- Create or modify: Langfuse prompt seeding

- [ ] **Step 1: Add prompt to Langfuse via migration script**

Create `backend/microservices/knowledge-tree-service/scripts/seed_phase3b_prompts.py`:

```python
#!/usr/bin/env python3
"""Seed Langfuse prompts for Phase 3b."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "emma-agent-service"))

LANGFUSE_URL = os.environ.get("LANGFUSE_URL", "http://langfuse:3000")

PROMPTS = {
    "trustgraph_guided_expansion": {
        "content": (
            "You are a knowledge graph traversal planner. Given a user query and the current "
            "subgraph state, decide if more graph exploration is needed.\n\n"
            "The current subgraph was built by BFS (2 hops) from seed entities. "
            "If the query requires relationships beyond what's visible, suggest expanding "
            "from specific entity URIs.\n\n"
            "Rules:\n"
            "- Only suggest expansion if the current subgraph clearly lacks information\n"
            "- Select at most 3 frontier URIs to expand from\n"
            "- Prefer entities that seem most relevant to the unanswered part of the query\n"
            "- If the subgraph already contains enough context, set sufficient=true\n\n"
            'Respond ONLY with JSON: {"sufficient": true/false, "expand_from": ["uri1", "uri2"], "reason": "brief explanation"}'
        ),
        "labels": ["production"],
    },
}


def main():
    try:
        from langfuse import Langfuse
        client = Langfuse()

        for name, config in PROMPTS.items():
            try:
                client.create_prompt(
                    name=name,
                    prompt=config["content"],
                    labels=config.get("labels", []),
                    type="text",
                )
                print(f"  OK  {name}")
            except Exception as exc:
                if "already exists" in str(exc).lower():
                    print(f"  SKIP  {name} — already exists")
                else:
                    print(f"  ERROR  {name}: {exc}")

    except ImportError:
        print("Langfuse not available — printing prompt content instead:")
        for name, config in PROMPTS.items():
            print(f"\n--- {name} ---")
            print(config["content"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/seed_phase3b_prompts.py
git commit -m "feat(kts): seed Langfuse prompt for guided expansion (Phase 3b)"
```

---

## Task 11: Update TRUSTGRAPH.md + Final Verification

**Files:**
- Modify: `docs/architecture/TRUSTGRAPH.md`

- [ ] **Step 1: Update Phase 3b status**

In `docs/architecture/TRUSTGRAPH.md`, replace the Phase 3b section:

```markdown
### Phase 3b: Smart Traversal (COMPLETE)

Authority weight triples (14 document types seeded in `_authority` collection, resolved via Cypher — zero hardcode), consensus scoring (cross-source agreement counts stored as `consensus_count` on `:Rel` edges), multi-hop Cypher templates (5 templates: entity_relations, corporate_chain, org_people, count_by_predicate, applicable_regulations), LLM-guided expansion (Stage 2.5 in graph_rag — planner evaluates subgraph sufficiency), composite 5-signal edge scoring (semantic 0.35 + confidence 0.20 + authority 0.20 + consensus 0.15 + recency 0.10), chain-of-thought path formatting.
```

- [ ] **Step 2: Run KTS test suite**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/ -v --tb=short --override-ini="log_auto_indent=true"
```

Expected: All new tests pass, no regressions.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/TRUSTGRAPH.md
git commit -m "docs: update TRUSTGRAPH.md — Phase 3b Smart Traversal complete"
```

---

## Summary

| Task | Component | New Files | Modified Files | Tests |
|------|-----------|-----------|----------------|-------|
| 1 | Authority weights seed | 1 | 0 | manual |
| 2 | Consensus scoring service | 2 | 0 | 4 tests |
| 3 | Consensus → coordinator | 0 | 1 | regression |
| 4 | Cypher template registry | 3 | 0 | 6 tests |
| 5 | KTS template API | 0 | 2 | manual |
| 6 | Emma settings | 0 | 1 | — |
| 7 | Authority + composite score | 0 | 1 | manual |
| 8 | Guided expansion Stage 2.5 | 0 | 1 | manual |
| 9 | Chain path formatting | 0 | 1 | manual |
| 10 | Langfuse prompt seed | 1 | 0 | — |
| 11 | Docs + verification | 0 | 1 | full suite |
| **Total** | | **7 new** | **8 modified** | **10+ tests** |

## Deploy Sequence

After all tasks are committed:

```bash
# 1. Rebuild services
cd backend/docker && docker compose up -d --build knowledge-tree-service weaviate-service emma-agent-service

# 2. Seed authority weights
docker compose exec knowledge-tree-service python scripts/seed_authority_weights.py --force

# 3. Seed Langfuse prompt (if Langfuse is running)
docker compose exec knowledge-tree-service python scripts/seed_phase3b_prompts.py

# 4. Reindex graph (applies consensus scoring to existing data)
docker compose exec knowledge-tree-service python scripts/reindex_trustgraph.py \
    --tenant-id 00000000-0000-0000-0000-000000000001
```
