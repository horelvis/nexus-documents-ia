# Phase 3a: Confidence Scoring + Source Pinpointing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pre-computed confidence scores to graph edges and inline source citations in graph_rag/SmartSearch context, improving retrieval quality and enabling the LLM to cite sources.

**Architecture:** Confidence calculated during extraction (coordinator), stored as `:Rel` property in FalkorDB, returned by `batch_neighbors`, consumed by graph_rag (pre-filter + enriched descriptions) and SmartSearch (avg confidence as graph_score). Source pinpointing via inline `[fuente: doc#chunk]` in context text.

**Tech Stack:** Python 3.12, FalkorDB (Cypher), asyncio

**Spec:** `docs/superpowers/specs/2026-03-30-trustgraph-phase3a-confidence-scoring-design.md`

**Base paths:**
- KTS: `backend/microservices/knowledge-tree-service`
- Emma: `backend/microservices/emma-agent-service`

---

## File Map

| File | Service | Change |
|------|---------|--------|
| `KTS/app/services/extractors/coordinator.py` | KTS | Calculate confidence per triple |
| `KTS/app/services/triple_store.py` | KTS | `batch_store_triples` stores confidence |
| `KTS/app/services/contradiction.py` | KTS | Batch penalty on contradicted edges |
| `KTS/app/services/triple_query.py` | KTS | Return confidence in batch_neighbors |
| `KTS/app/core/config.py` | KTS | Confidence threshold setting |
| `Emma/app/agents/langgraph/tools/graph_rag.py` | Emma | Pre-filter + enriched context + inline sources |
| `Emma/app/agents/langgraph/tools/smart_search.py` | Emma | graph_score uses avg confidence |
| `Emma/app/core/config.py` | Emma | Confidence threshold setting |

---

### Task 1: Confidence calculation in coordinator + batch_store

**Files:**
- Modify: `KTS/app/services/extractors/coordinator.py`
- Modify: `KTS/app/services/triple_store.py`

- [ ] **Step 1: Add confidence mapping to coordinator**

In `coordinator.py`, add a module-level dict after the imports:

```python
# Confidence base scores by extraction method
_CONFIDENCE_BASE: Dict[str, float] = {
    "system": 1.00,
    "llm_definitions": 0.90,
    "llm_topics": 0.85,
    "llm_objects": 0.85,
    "llm_relationships": 0.90,
    "llm_relationships_fuzzy": 0.75,
    "llm_relationships_freeform": 0.60,
}
_DEFAULT_CONFIDENCE = 0.70
```

- [ ] **Step 2: Add confidence to batch triple builder in extract_chunk**

In the `extract_chunk` method, inside the loop that builds `batch_triples`, add a `confidence` field to each triple dict. After the line that sets `extraction_method`:

```python
            confidence = _CONFIDENCE_BASE.get(extraction_method, _DEFAULT_CONFIDENCE)
```

Then include `"confidence": confidence` in each dict appended to `batch_triples`. For topic triples (the `has-topic` branch) and entity triples (both `object_is_entity` branches), add the field:

```python
                batch_triples.append({
                    "s_uri": ...,
                    "p_uri": ...,
                    # ... existing fields ...
                    "confidence": confidence,
                })
```

- [ ] **Step 3: Update batch_store_triples to store confidence**

In `triple_store.py`, modify the `batch_store_triples` method's two UNWIND queries to include confidence in the ON CREATE SET clause.

For node_triples query, change:
```python
"ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk",
```
to:
```python
"ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk, r.confidence = t.confidence",
```

Same change for the literal_triples query.

- [ ] **Step 4: Verify imports**

Run: `cd backend/microservices/knowledge-tree-service && python3 -c "from app.services.extractors.coordinator import ExtractionCoordinator; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py \
        backend/microservices/knowledge-tree-service/app/services/triple_store.py
git commit -m "feat(trustgraph): pre-computed confidence score per triple (stored on :Rel edges)"
```

---

### Task 2: Contradiction penalty batch update

**Files:**
- Modify: `KTS/app/services/contradiction.py`

- [ ] **Step 1: Add batch penalty method**

In `contradiction.py`, add a method to `ContradictionDetector` after `detect_and_mark`:

```python
    async def apply_confidence_penalty(self, user: str) -> int:
        """Batch-reduce confidence on all edges marked has_contradiction=true.

        Sets confidence = max(confidence - 0.25, 0.10) for contradicted edges.
        Returns the number of edges updated.
        """
        query = (
            "MATCH ()-[r:Rel]->() "
            "WHERE r.user = $user AND r.has_contradiction = true "
            "AND r.confidence IS NOT NULL "
            "SET r.confidence = CASE "
            "  WHEN r.confidence - 0.25 < 0.10 THEN 0.10 "
            "  ELSE r.confidence - 0.25 "
            "END "
            "RETURN count(r) AS updated"
        )
        rows = await self._client.execute_cypher(query, params={"user": user})
        count = rows[0]["updated"] if rows else 0
        if count:
            logger.info("Applied confidence penalty to %d contradicted edges", count)
        return count
```

- [ ] **Step 2: Call penalty after detect_and_mark in coordinator**

In `coordinator.py`, in the `extract_document` method, after the contradiction detection loop completes and before the summary logging, add:

```python
        # Apply confidence penalty to contradicted edges
        try:
            await detector.apply_confidence_penalty(user=user)
        except Exception as exc:
            errors.append(f"confidence_penalty: {exc}")
            logger.warning("Confidence penalty failed: %s", exc)
```

- [ ] **Step 3: Verify import**

Run: `cd backend/microservices/knowledge-tree-service && python3 -c "from app.services.contradiction import ContradictionDetector; print(hasattr(ContradictionDetector, 'apply_confidence_penalty'))"`

Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/contradiction.py \
        backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py
git commit -m "feat(trustgraph): contradiction confidence penalty (-0.25 on contradicted edges)"
```

---

### Task 3: Return confidence in batch_neighbors

**Files:**
- Modify: `KTS/app/services/triple_query.py`

- [ ] **Step 1: Add confidence to BFS RETURN clause**

In `triple_query.py`, in the `batch_neighbors` method (around line 354-362), modify the RETURN clause to include `r.confidence`:

Change:
```python
                "RETURN s.uri AS subject, r.uri AS predicate, "
                "o.uri AS object, 'node' AS object_type, "
                "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk "
```

To:
```python
                "RETURN s.uri AS subject, r.uri AS predicate, "
                "o.uri AS object, 'node' AS object_type, "
                "r.extraction_method AS extraction_method, r.source_chunk AS source_chunk, "
                "r.confidence AS confidence "
```

- [ ] **Step 2: Include confidence in _row_to_triple**

Check if `_row_to_triple` passes through unknown keys. If it only maps specific keys, add `confidence` to it. Search for the method and update.

The `_row_to_triple` helper (find it in the file) likely does:
```python
def _row_to_triple(self, row: Dict) -> Dict:
    return {
        "subject_uri": row.get("subject", ""),
        "predicate_uri": row.get("predicate", ""),
        "object_uri": row.get("object", ""),
        "object_type": row.get("object_type", "node"),
        "extraction_method": row.get("extraction_method", ""),
        "source_chunk": row.get("source_chunk", ""),
    }
```

Add:
```python
        "confidence": row.get("confidence"),
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/triple_query.py
git commit -m "feat(trustgraph): return confidence in batch_neighbors BFS results"
```

---

### Task 4: graph_rag confidence pre-filter + enriched context + inline sources

**Files:**
- Modify: `Emma/app/agents/langgraph/tools/graph_rag.py`
- Modify: `Emma/app/core/config.py`

This is the main consumer task. Three changes in graph_rag.py:

- [ ] **Step 1: Add config setting**

In `Emma/app/core/config.py`, find the `graph_rag_*` settings block and add:

```python
    graph_rag_confidence_threshold: float = float(
        os.getenv("GRAPH_RAG_CONFIDENCE_THRESHOLD", "0.30")
    )
```

- [ ] **Step 2: Add confidence pre-filter in graph_rag Stage 4**

In `graph_rag.py`, in the `execute` method, after Stage 2 (BFS subgraph) gets the `edges` list and before Stage 3 (label resolution), add a confidence pre-filter:

```python
        # ── Stage 2b: Confidence pre-filter ─────────────────────────────
        confidence_threshold = settings.graph_rag_confidence_threshold
        if confidence_threshold > 0:
            edges = [
                e for e in edges
                if (e.get("confidence") or 1.0) >= confidence_threshold
            ]
            if not edges:
                return _format_entities_only(top_entities)
```

Note: `or 1.0` handles edges without confidence (legacy data) — they pass the filter.

- [ ] **Step 3: Enrich edge descriptions with confidence + source**

In the `_build_edge_description` function, add confidence and source parameters:

```python
def _build_edge_description(
    subject_label: str,
    predicate_name: str,
    object_label: str,
    confidence: Optional[float] = None,
    source_chunk: Optional[str] = None,
) -> str:
    """Build a human-readable edge description for embedding / LLM scoring."""
    desc = f"{subject_label}, {predicate_name}, {object_label}"
    if confidence is not None:
        desc += f" [conf: {confidence:.2f}]"
    if source_chunk:
        # Extract doc_id and chunk offset from source_chunk URI
        # Format: nouxcube://document/{collection}/{doc_id}#offset={n}
        doc_part = source_chunk.split("#")[0].rsplit("/", 1)[-1] if source_chunk else ""
        offset_part = source_chunk.split("offset=")[-1] if "offset=" in source_chunk else ""
        if doc_part:
            desc += f" [fuente: {doc_part}#{offset_part}]"
    return desc
```

Then update the Stage 4 loop that calls `_build_edge_description` to pass the new fields:

```python
        for edge in edges:
            s_uri = edge.get("subject_uri", "")
            p_uri = edge.get("predicate_uri", "")
            o_uri = edge.get("object_uri", "")
            s_label = labels.get(s_uri, _humanize_uri(s_uri))
            p_name = _extract_predicate_name(p_uri)
            o_label = labels.get(o_uri, _humanize_uri(o_uri))
            edge_descriptions.append(_build_edge_description(
                s_label, p_name, o_label,
                confidence=edge.get("confidence"),
                source_chunk=edge.get("source_chunk"),
            ))
```

- [ ] **Step 4: Enrich Stage 6 context formatting with sources**

In `_format_context`, modify the relationship_list builder to include confidence and source:

```python
        for edge in scored_edges:
            s_uri = edge.get("subject_uri", "")
            p_uri = edge.get("predicate_uri", "")
            o_uri = edge.get("object_uri", "")
            score = edge.get("_llm_score", 0.5)
            confidence = edge.get("confidence")
            source = edge.get("source_chunk", "")

            s_label = labels.get(s_uri, _humanize_uri(s_uri))
            p_name = _extract_predicate_name(p_uri)
            o_label = labels.get(o_uri, _humanize_uri(o_uri))

            # Parse source for human-readable citation
            doc_id = source.split("#")[0].rsplit("/", 1)[-1] if source else ""
            chunk_offset = source.split("offset=")[-1] if source and "offset=" in source else ""

            rel = {
                "subject": s_label,
                "predicate": p_name,
                "object": o_label,
                "score": round(score, 4),
            }
            if confidence is not None:
                rel["confidence"] = round(confidence, 2)
            if doc_id:
                rel["source"] = f"{doc_id}#{chunk_offset}"

            relationship_list.append(rel)
            scores.append(score)
```

- [ ] **Step 5: Verify imports**

Run: `cd backend/microservices/emma-agent-service && python3 -c "from app.agents.langgraph.tools.graph_rag import GraphRAGTool; print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py \
        backend/microservices/emma-agent-service/app/core/config.py
git commit -m "feat(trustgraph): graph_rag confidence pre-filter + inline source citations"
```

---

### Task 5: SmartSearch graph_score uses avg confidence

**Files:**
- Modify: `Emma/app/agents/langgraph/tools/smart_search.py`

- [ ] **Step 1: Update graph_score calculation**

In `smart_search.py`, find the graph_score section (around line 1449-1459). Currently:

```python
            if doc_id in graph_doc_set:
                graph_score = graph_avg
            elif doc_id in graph_document_ids:
                graph_score = 1.0
            else:
                graph_score = 0.0
```

The `graph_avg` comes from the graph_rag tool's `avg_score` in the data dict. This already uses LLM scores. To incorporate confidence, we need to check if the graph_rag_data includes confidence info.

The change is in how `graph_avg` is calculated upstream (graph_rag already includes confidence in edges). But for SmartSearch's own graph expansion (which uses `knowledge_tree_client.query_triples`), we should use confidence if available.

Find the section where `graph_document_ids` is populated from graph expansion results. Where individual entity triples are queried, the response may now include `confidence`. Update the `graph_score` to use it:

```python
            if graph_rag_data:
                graph_doc_set = set(graph_rag_data.get("expanded_doc_ids", []))
                if doc_id in graph_doc_set:
                    graph_score = graph_avg
                elif doc_id in graph_document_ids:
                    graph_score = 1.0
                else:
                    graph_score = 0.0
            else:
                graph_score = 1.0 if doc_id in graph_document_ids else 0.0
```

The avg_score from graph_rag already incorporates confidence (since edges with low confidence are pre-filtered and scored edges carry confidence). No further change needed here — the graph_rag changes in Task 4 flow through automatically via the `avg_score` field.

**However**, add a comment for clarity:

```python
            # graph_score: avg LLM score from graph_rag (already confidence-aware via pre-filter)
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/smart_search.py
git commit -m "feat(trustgraph): SmartSearch graph_score benefits from confidence-filtered graph_rag"
```

---

### Task 6: Rebuild + reindex validation

- [ ] **Step 1: Rebuild both services**

```bash
cd backend/docker
docker compose up -d --build knowledge-tree-service emma-agent-service
```

- [ ] **Step 2: Run reindex**

```bash
docker compose exec -T knowledge-tree-service python scripts/reindex_trustgraph.py \
    --tenant-id 00000000-0000-0000-0000-000000000001
```

- [ ] **Step 3: Verify confidence distribution**

```bash
docker compose exec -T knowledge-tree-service python -c "
import asyncio
from app.services.falkordb_client import FalkorDBClient

async def check():
    c = FalkorDBClient()
    await c.initialize()
    rows = await c.execute_cypher(
        'MATCH ()-[r:Rel]->() WHERE r.confidence IS NOT NULL '
        'RETURN r.extraction_method AS method, avg(r.confidence) AS avg_conf, count(r) AS cnt '
        'ORDER BY avg_conf DESC'
    )
    for r in rows:
        print(f'{r[\"method\"]:30s}  avg={r[\"avg_conf\"]:.3f}  count={r[\"cnt\"]}')

    # Check contradiction penalty
    contra = await c.execute_cypher(
        'MATCH ()-[r:Rel]->() WHERE r.has_contradiction = true AND r.confidence IS NOT NULL '
        'RETURN avg(r.confidence) AS avg_conf, count(r) AS cnt'
    )
    if contra:
        print(f'Contradicted edges: avg={contra[0][\"avg_conf\"]:.3f} count={contra[0][\"cnt\"]}')
    await c.close()

asyncio.run(check())
"
```

Expected:
- `system` → avg ~1.00
- `llm_relationships` → avg ~0.90
- `llm_relationships_fuzzy` → avg ~0.75
- `llm_relationships_freeform` → avg ~0.60
- Contradicted edges → avg < 0.65
