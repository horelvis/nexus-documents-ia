# Extraction Performance Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce TrustGraph extraction time from ~8-9 min/doc to ~1-2 min/doc by eliminating 4 I/O bottlenecks.

**Architecture:** Fix connection pooling (shared httpx client), use existing batch_store_triples() in coordinator, batch provenance recording, and parallelize contradiction detection. No new services or architectural changes — pure I/O optimization.

**Tech Stack:** Python 3.12, asyncio, httpx, FalkorDB (Cypher UNWIND)

**Base path:** `backend/microservices/knowledge-tree-service`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/services/extractors/base.py` | Modify | Shared httpx.AsyncClient (connection pooling) |
| `app/services/extractors/coordinator.py` | Modify | Batch triple storage, parallel contradiction detection |
| `app/services/provenance.py` | Modify | Batch provenance recording via UNWIND |
| `app/services/triple_store.py` | Modify | Add `batch_store_provenance()` method |
| `tests/test_extractors.py` | Modify | Test shared client lifecycle |

---

### Task 1: Shared httpx.AsyncClient in BaseExtractor

**Files:**
- Modify: `app/services/extractors/base.py`
- Test: `tests/test_extractors.py`

Currently, `_call_llm()` creates a NEW `httpx.AsyncClient` per call (line 228). For 200+ LLM calls per document, this wastes ~1-2 min on TCP/TLS setup. Fix: use a class-level shared client.

- [ ] **Step 1: Add shared client class variable and initialization**

In `base.py`, add a class-level client and methods to manage it. Replace the `_call_llm` method and add client management:

```python
# Add to class variables (after RESPONSE_SCHEMA):
    _shared_client: ClassVar[Optional[httpx.AsyncClient]] = None

    @classmethod
    def get_shared_client(cls) -> httpx.AsyncClient:
        """Get or create a shared httpx.AsyncClient for all extractors."""
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                ),
            )
        return cls._shared_client

    @classmethod
    async def close_shared_client(cls) -> None:
        """Close the shared client. Call at shutdown or after reindex."""
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None
```

Then update `_call_llm()` to use the shared client instead of creating a new one:

```python
    async def _call_llm(self, prompt: str) -> str:
        """POST to SGLang /chat/completions and return the message content."""
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4096,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        client = self.get_shared_client()
        resp = await client.post(
            f"{self._sglang_url}/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content")
        if content is None:
            content = msg.get("reasoning_content", "")
        return content or ""
```

Import `ClassVar` and `Optional` should already be at the top from previous work.

- [ ] **Step 2: Add close_shared_client call in reindex script**

In `scripts/reindex_trustgraph.py`, after the main extraction loop completes (in the `finally` block around line 698), add:

```python
        # Close shared HTTP client
        from app.services.extractors.base import BaseExtractor
        await BaseExtractor.close_shared_client()
```

- [ ] **Step 3: Add test for shared client**

Add to `tests/test_extractors.py`:

```python
class TestSharedClient:
    """Tests for BaseExtractor shared httpx client."""

    def test_shared_client_singleton(self):
        """get_shared_client returns the same instance."""
        ext = self._make_extractor()
        c1 = BaseExtractor.get_shared_client()
        c2 = BaseExtractor.get_shared_client()
        assert c1 is c2
        # Cleanup
        BaseExtractor._shared_client = None

    def _make_extractor(self):
        class StubExtractor(BaseExtractor):
            EXTRACTOR_NAME = "stub"
            RESPONSE_SCHEMA = {}
            def _build_prompt(self, chunk_text): return ""
            def _parse_output(self, llm_output, chunk_text): return []
        return StubExtractor()

    @pytest.mark.asyncio
    async def test_close_shared_client(self):
        """close_shared_client closes and clears the client."""
        _ = BaseExtractor.get_shared_client()
        assert BaseExtractor._shared_client is not None
        await BaseExtractor.close_shared_client()
        assert BaseExtractor._shared_client is None
```

- [ ] **Step 4: Run tests**

Run: `cd backend/microservices/knowledge-tree-service && python3 -m pytest tests/test_extractors.py::TestSharedClient -v --no-header --override-ini="log_auto_indent=true" -p no:cacheprovider`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/base.py \
        backend/microservices/knowledge-tree-service/tests/test_extractors.py \
        backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py
git commit -m "perf(trustgraph): shared httpx.AsyncClient for LLM calls (connection pooling)"
```

---

### Task 2: Use batch_store_triples in extract_chunk

**Files:**
- Modify: `app/services/extractors/coordinator.py`

Currently `extract_chunk()` stores each triple individually (3-4 Cypher calls per triple). `batch_store_triples()` already exists but is never called. Fix: collect triples and call batch at the end.

- [ ] **Step 1: Replace the triple storage loop in extract_chunk**

In `coordinator.py`, replace the triple storage loop (the `for triple in deduped_triples:` block, lines ~172-223) with batch storage. The new code collects triples into batch format, handles topics separately (they have empty subject), then calls `batch_store_triples()` once:

```python
        # ── Batch-store triples ──────────────────────────────────────────
        source_chunk_id = f"{document_uri}#offset={chunk_offset}"
        batch_triples: List[Dict[str, Any]] = []
        topic_triples: List[Dict[str, Any]] = []

        for triple in deduped_triples:
            subject = triple.get("subject", "")
            predicate_ontology = triple.get("predicate_ontology", "core")
            predicate_name = triple.get("predicate_name", "")
            obj = triple.get("object", "")
            object_is_node = triple.get("object_is_node", False)
            extraction_method = triple.get("extraction_method", "llm")

            if not predicate_name:
                continue

            predicate_uri = URIBuilder.predicate(predicate_ontology, predicate_name)

            # Topic triples: subject="" → link document_uri → topic literal
            if predicate_name == "has-topic" and subject == "":
                topic_triples.append({
                    "s_uri": document_uri,
                    "p_uri": predicate_uri,
                    "o_val": obj,
                    "object_is_entity": False,
                    "method": extraction_method,
                    "chunk": source_chunk_id,
                })
                if document_uri not in subject_uris:
                    subject_uris.append(document_uri)
            elif object_is_node:
                subject_uri = URIBuilder.entity(collection, subject)
                object_uri = URIBuilder.entity(collection, obj)
                batch_triples.append({
                    "s_uri": subject_uri,
                    "o_uri": object_uri,
                    "p_uri": predicate_uri,
                    "object_is_entity": True,
                    "method": extraction_method,
                    "chunk": source_chunk_id,
                })
                if subject_uri not in subject_uris:
                    subject_uris.append(subject_uri)
            else:
                subject_uri = URIBuilder.entity(collection, subject)
                batch_triples.append({
                    "s_uri": subject_uri,
                    "o_val": obj.strip() if obj else obj,
                    "p_uri": predicate_uri,
                    "object_is_entity": False,
                    "method": extraction_method,
                    "chunk": source_chunk_id,
                })
                if subject_uri not in subject_uris:
                    subject_uris.append(subject_uri)

        # Store all triples in 1-2 batch Cypher calls instead of N individual calls
        try:
            all_batch = batch_triples + topic_triples
            triples_created = await self._store.batch_store_triples(
                all_batch, user=user, collection=collection
            )
        except Exception as exc:
            errors.append(f"batch_store: {exc}")
            logger.warning("Batch store failed, falling back to individual: %s", exc)
            triples_created = 0
```

Also change the `subject_uris` variable declaration from `List[str]` to just `list`:

```python
        subject_uris: list = []
```

And remove the old `triples_created = 0` counter since `batch_store_triples` returns the count.

- [ ] **Step 2: Verify import**

Run: `cd backend/microservices/knowledge-tree-service && python3 -c "from app.services.extractors.coordinator import ExtractionCoordinator; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py
git commit -m "perf(trustgraph): use batch_store_triples in extract_chunk (~10x fewer Cypher calls)"
```

---

### Task 3: Batch provenance recording

**Files:**
- Modify: `app/services/provenance.py`
- Modify: `app/services/triple_store.py`
- Modify: `app/services/extractors/coordinator.py`

Currently provenance creates 11 Cypher transactions per chunk (1 merge_node + 1 create_rel for derived-from + 5×(merge_literal + create_rel) for metadata). For 50 chunks = 550 transactions. Fix: single UNWIND batch.

- [ ] **Step 1: Add batch_store_provenance to TripleStore**

In `app/services/triple_store.py`, add after `batch_store_triples()`:

```python
    async def batch_store_provenance(
        self, records: list, user: str, collection: str
    ) -> int:
        """Store multiple provenance extraction records in a single UNWIND query.

        Each record dict must have:
          extraction_uri, document_uri, method, model, timestamp,
          chunk_text, chunk_offset

        Creates the extraction :Node, prov/derived-from edge to document,
        and 5 literal metadata triples — all in 2 UNWIND queries.
        """
        if not records:
            return 0

        # Query 1: Create extraction nodes and derived-from edges to documents
        await self._client.execute_cypher(
            "UNWIND $records AS r "
            "MERGE (e:Node {uri: r.extraction_uri, user: $user, collection: $col}) "
            "ON CREATE SET e.created_at = timestamp() "
            "WITH e, r "
            "MATCH (d:Node {uri: r.document_uri, user: $user, collection: $col}) "
            "MERGE (e)-[rel:Rel {uri: r.derived_from_uri, user: $user, collection: $col}]->(d) "
            "ON CREATE SET rel.extraction_method = 'system'",
            {"records": records, "user": user, "col": collection},
        )

        # Query 2: Create all literal metadata triples
        # Flatten: each record produces 5 literals
        flat_literals = []
        for r in records:
            base = r["extraction_uri"]
            for pred_name, value in [
                ("method", r["method"]),
                ("model", r["model"]),
                ("timestamp", r["timestamp"]),
                ("chunk-text", r["chunk_text"]),
                ("chunk-offset", r["chunk_offset"]),
            ]:
                flat_literals.append({
                    "e_uri": base,
                    "p_uri": f"nouxcube://predicate/prov/{pred_name}",
                    "val": value,
                })

        if flat_literals:
            await self._client.execute_cypher(
                "UNWIND $lits AS l "
                "MATCH (e:Node {uri: l.e_uri, user: $user, collection: $col}) "
                "MERGE (lit:Literal {value: l.val, user: $user, collection: $col}) "
                "MERGE (e)-[r:Rel {uri: l.p_uri, user: $user, collection: $col}]->(lit) "
                "ON CREATE SET r.extraction_method = 'system'",
                {"lits": flat_literals, "user": user, "col": collection},
            )

        return len(records)
```

- [ ] **Step 2: Add batch method to ProvenanceService**

In `app/services/provenance.py`, add after the existing `record_extraction()` method:

```python
    async def batch_record_extractions(
        self,
        document_uri: str,
        chunks_metadata: list,
        user: str,
        collection: str,
    ) -> int:
        """Record provenance for multiple chunks in batch.

        Args:
            document_uri:    URI of the source document :Node.
            chunks_metadata: List of dicts with keys:
                extraction_method, model_name, chunk_text, chunk_offset
            user:           Tenant/user identifier.
            collection:     Collection scope.

        Returns:
            Number of provenance records created.
        """
        if not chunks_metadata:
            return 0

        derived_from_uri = URIBuilder.predicate(_PROV, "derived-from")

        records = []
        for meta in chunks_metadata:
            records.append({
                "extraction_uri": URIBuilder.extraction(),
                "document_uri": document_uri,
                "derived_from_uri": derived_from_uri,
                "method": meta.get("extraction_method", "llm_coordinator"),
                "model": meta.get("model_name", "unknown"),
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "chunk_text": meta.get("chunk_text", "")[:_MAX_CHUNK_TEXT],
                "chunk_offset": str(meta.get("chunk_offset", 0)),
            })

        return await self._store.batch_store_provenance(
            records, user=user, collection=collection
        )
```

- [ ] **Step 3: Use batch provenance in coordinator**

In `coordinator.py`, modify `extract_document()` to collect provenance data during chunk processing and record it in one batch at the end (before contradiction detection).

Add provenance collection in the chunk processing results loop:

```python
        # Collect provenance metadata for batch recording
        provenance_metadata: List[Dict[str, Any]] = []
```

Then inside the results loop, where each successful chunk result is processed, add:

```python
                provenance_metadata.append({
                    "extraction_method": "llm_coordinator",
                    "model_name": "Qwen3.5-27B-AWQ",
                    "chunk_text": chunks[i],
                    "chunk_offset": i,
                })
```

And add batch provenance recording before contradiction detection:

```python
        # Batch record provenance for all processed chunks
        try:
            await self._provenance.batch_record_extractions(
                document_uri=document_uri,
                chunks_metadata=provenance_metadata,
                user=user,
                collection=collection,
            )
        except Exception as exc:
            errors.append(f"batch_provenance: {exc}")
            logger.warning("Batch provenance recording failed: %s", exc)
```

Also **remove** the per-chunk provenance call from `extract_chunk()` (lines ~225-238, the `self._provenance.record_extraction(...)` block). This moves provenance from per-chunk to per-document batched.

- [ ] **Step 4: Verify import**

Run: `cd backend/microservices/knowledge-tree-service && python3 -c "from app.services.provenance import ProvenanceService; print(hasattr(ProvenanceService, 'batch_record_extractions'))"`

Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/triple_store.py \
        backend/microservices/knowledge-tree-service/app/services/provenance.py \
        backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py
git commit -m "perf(trustgraph): batch provenance recording (550 txns → 2 UNWIND queries per doc)"
```

---

### Task 4: Parallelize contradiction detection

**Files:**
- Modify: `app/services/extractors/coordinator.py`

Currently contradiction detection loops sequentially over all unique subjects. Fix: use `asyncio.gather` with a semaphore.

- [ ] **Step 1: Replace sequential contradiction loop in extract_document**

In `coordinator.py`, replace the sequential contradiction loop:

```python
        # Step 3: Batch contradiction detection (edge metadata) — parallelized
        contradictions_found = 0
        detector = ContradictionDetector(self._store._client)
        contra_sem = asyncio.Semaphore(10)

        async def _detect_subject(subject_uri: str) -> int:
            async with contra_sem:
                return await detector.detect_and_mark(
                    subject_uri=subject_uri, user=user
                )

        contra_tasks = [_detect_subject(uri) for uri in all_subject_uris]
        contra_results = await asyncio.gather(*contra_tasks, return_exceptions=True)

        for i, result in enumerate(contra_results):
            if isinstance(result, BaseException):
                subj = list(all_subject_uris)[i] if i < len(all_subject_uris) else "?"
                errors.append(f"contradiction({subj}): {result}")
                logger.warning("Contradiction detection failed: %s", result)
            else:
                contradictions_found += result
```

- [ ] **Step 2: Verify import**

Run: `cd backend/microservices/knowledge-tree-service && python3 -c "from app.services.extractors.coordinator import ExtractionCoordinator; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py
git commit -m "perf(trustgraph): parallelize contradiction detection (semaphore=10)"
```

---

### Task 5: Increase chunk parallelism and rebuild

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Increase default parallel chunks from 3 to 5**

In `app/core/config.py`, change:

```python
    extraction_parallel_chunks: int = int(os.getenv("EXTRACTION_PARALLEL_CHUNKS", "5"))
```

This sends 5 chunks × 4 extractors = 20 concurrent LLM requests, which the shared httpx client handles efficiently with connection pooling.

- [ ] **Step 2: Rebuild and test**

```bash
cd backend/docker && docker compose up -d --build knowledge-tree-service
```

Wait for the service to start, then run a quick dry-run reindex to verify everything compiles:

```bash
docker compose exec -T knowledge-tree-service python scripts/reindex_trustgraph.py \
    --tenant-id 00000000-0000-0000-0000-000000000001 --dry-run
```

Expected: Lists 28 documents without errors.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/core/config.py
git commit -m "perf(trustgraph): increase default parallel chunks from 3 to 5"
```

---

### Task 6: Full reindex benchmark

This is the validation task. Run after all optimizations are deployed.

- [ ] **Step 1: Stop any running reindex**

If the old reindex is still running, let it finish or cancel it.

- [ ] **Step 2: Run optimized reindex**

```bash
cd backend/docker && docker compose exec -T knowledge-tree-service \
    python scripts/reindex_trustgraph.py \
    --tenant-id 00000000-0000-0000-0000-000000000001
```

- [ ] **Step 3: Compare results**

Target metrics:
- Time per document: <2 min (was ~8-9 min)
- Total time: <1 hour (was ~3-4 hours)
- Triples per doc: >75 (unchanged from Phase 3-PREREQ)
- Parse failures: <5%
- Contradiction :Nodes: 0 (edge metadata only)

## Expected Impact Summary

| Bottleneck | Before | After | Savings |
|---|---|---|---|
| HTTP client per-call | 200+ new connections/doc | 1 shared pool | ~60-120s |
| Individual triple storage | 5,000+ Cypher txns/doc | ~50 batch calls | ~60-240s |
| Per-chunk provenance | 550 Cypher txns/doc | 2 UNWIND queries | ~210-420s |
| Sequential contradictions | Sequential loop | Parallel (sem=10) | ~60-180s |
| Chunk parallelism | 3 concurrent | 5 concurrent | ~20% throughput |
| **Total** | **~500s/doc** | **~60-120s/doc** | **~4-8x faster** |
