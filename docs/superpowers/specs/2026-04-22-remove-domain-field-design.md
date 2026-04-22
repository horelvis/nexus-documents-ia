# Remove `domain` Field — Design Spec

**Date:** 2026-04-22
**Status:** Draft (pending user review)
**Author:** H Castillo / Claude
**Related:** User Agents Roadmap (Fase 0 blocker); Sectors Removal (completed 2026-03-31)

---

## 1. Purpose

Eliminate the `domain` field across the entire stack. It duplicates information already present in `document_type`, has three parallel detection systems that can disagree with each other, and blocks the User Agents roadmap where custom agents define their scope dynamically rather than via a fixed `domain` taxonomy.

## 2. Motivation

`domain` is a legacy artifact from the pre-2026-03-31 multi-sector architecture (legal, fiscal, medical, etc.). When sectors were unified, `domain` remained as an "enrichment property" on documents, but:

1. **It is redundant with `document_type`.** The classifier in `intelligence-docs-service` produces both values from the same regex patterns (`FILENAME_PATTERNS` is `list[tuple[regex, doc_type, domain]]`). If you know `document_type="contrato"`, you already know the area is legal.
2. **There are three parallel detectors with different outputs.**
    - `intelligence-docs-service/pipeline/classifier.py` → `ClassificationResult.domain: str`
    - `weaviate-service/rag/contextual_retrieval.py` → `LegalDomain` enum via keyword scoring
    - `weaviate-service/knowledge/extraction_service.py` → `DomainType` enum via a third keyword map
   These can produce inconsistent labels for the same document.
3. **User Agents roadmap requires data-first scope filters** (per user feedback: "agent builder is data-first, scope filters define behavior"). Custom agents should define scope as `semantic_type IN [contrato, sentencia, …]` or via TrustGraph queries, not via a hardcoded `domain` enum.
4. **Weaviate is currently empty.** `Nouxcube_documents` has 0 objects — ideal moment for schema change without migration.

## 3. Target State

### 3.1 `document_type` is the sole taxonomy

`document_type` remains the single source of truth for what a document is. Possible values (current regex set): `factura`, `contrato`, `nomina`, `modelo_fiscal`, `sentencia`, `convenio`, `estatuto`, `informe`, `acta`, `escritura`, `poliza`, `contable`, `certificado`, `demanda`, `general`.

### 3.2 Area grouping is a frontend concern

If a UI needs to display "Documentos Legales" as a grouping, it uses a frontend helper `group_of(doc_type)` with a mapping table. This lives in presentation code, never persisted as a field.

### 3.3 `analyze_document()` simplified

Before:
```python
domain_result = self.detect_domain(text, metadata)
context_prefix = self.generate_context_prefix(domain_result, document_type=...)
applicable_laws = self._get_applicable_laws(domain_result.primary_domain, ...)
```

After:
```python
document_type = metadata.get("document_type", "general")
context_prefix = generate_context_prefix(document_type, entities=key_entities)
# applicable_laws: removed — agent queries TrustGraph JIT via graph_rag when needed
```

### 3.4 `applicable_laws` moves from push to pull

Currently `detect_domain` precomputes applicable laws per document during indexing. After refactor, the ReAct agent queries TrustGraph on demand via `graph_rag` or the existing `knowledge_tree_client.get_applicable_laws` lookup when the user's question warrants it. This is cheaper (no work per indexed doc) and more accurate (laws match the question, not the document).

## 4. Scope

### 4.1 In scope

| # | Component | Change |
|---|---|---|
| 1 | `intelligence-docs-service/pipeline/classifier.py` | Remove `domain` from `FILENAME_PATTERNS` tuple; classifier returns only `document_type` |
| 2 | `intelligence-docs-service/providers/base.py` | Remove `domain` from `ClassificationResult` dataclass |
| 3 | `intelligence-docs-service/tests/test_classifier.py` | Update assertions |
| 4 | `weaviate-service/rag/contextual_retrieval.py` | Delete `LegalDomain` enum, `DomainDetectionResult`, `detect_domain()`, `_get_applicable_laws()`, `_extract_key_entities` domain param; refactor `analyze_document()` and `generate_context_prefix()` to use `document_type` only |
| 5 | `weaviate-service/knowledge/extraction_service.py` | Delete `DomainType` enum, `_domain_keywords`, `_detect_domain()`; remove `domain` from entity schemas; stop propagating `domain` to entities |
| 6 | `weaviate-service/schemas/weaviate.py` | Remove `domain` from `Nouxcube_documents` schema and request/response Pydantic models (`domain`, `domain_filter`) |
| 7 | `weaviate-service/services/weaviate_service.py` | Remove `domain` from indexing writes (L 976), remove `domain_filter` branch from search (L 1264-1268), update module docstring |
| 8 | `weaviate-service/api/weaviate.py` | Remove `domain_filter` from request params |
| 9 | `weaviate-service/services/rag/indexing_pipeline.py` | Remove `contextual_domain` propagation; remove `"labor"` sample metadata in `context_enricher.py` |
| 10 | `emma-agent-service/langgraph/tools/smart_search.py` | Remove `domain_filter` param from tool schema; remove `enriched_domain` logic; remove `"domain"` from result metadata |
| 11 | `emma-agent-service/sectors/config.py` | Remove `"domain"` from graph search properties list (L 96); update docstring |
| 12 | `emma-agent-service/workers/event_listener.py`, `services/memorag/service.py`, `services/memory/memory_generator.py`, `services/rule_engine.py`, `services/few_shot_retriever.py`, `services/predictive_analysis/*`, `schemas/predictive_analysis.py`, `schemas/prompts.py`, `api/emma.py`, `api/explainability.py`, `clients/weaviate_client.py`, `clients/knowledge_tree_client.py`, `agents/langgraph/tools/specialists.py`, `agents/langgraph/sectors/predictive_config.py`, `agents/langgraph/sectors/registry.py`, `core/config.py`, `core/langfuse_config.py`, `services/guardrail_registry.py` | Audit each; remove `domain` field/param references |
| 13 | `knowledge-tree-service/schemas/triples.py`, `services/extractors/coordinator.py`, `services/triple_store.py`, `tests/*` | Remove `domain` from entity/triple schemas where it's decorative (not structural for TrustGraph) |
| 14 | `background-worker/worker_app/tasks/trustgraph_tasks.py` | Remove `domain` from task payloads |
| 15 | `backend/app/services/weaviate_client.py`, `backend/app/api/v1/weaviate.py`, `backend/app/services/unified_indexing_service.py`, `backend/app/services/data_learning/*`, `backend/app/schemas/connector.py`, `backend/app/schemas/data_learning.py`, `backend/app/db/models.py` | Audit and remove `domain` field / param references. **Skip archived Alembic migrations.** |
| 16 | `core/connectors/adapters/base.py`, `google_drive.py`, `alfresco.py`, `metadata_schema.py` | Remove `domain` from connector metadata schema |
| 17 | `frontend/src/lib/services/data-learning.service.ts` | Remove `domain` from TypeScript types and any UI that displays/filters by it |
| 18 | `backend/scripts/contextualize_chunks.py` | **Delete entire script** (depended on `applicable_laws`/`detect_domain` which are removed) |
| 19 | `backend/docker/.env` | Delete `ACTIVE_SECTOR=documental` (already ignored since 2026-03-31) |
| 20 | `backend/microservices/emma-agent-service/scripts/migrate_retrieval_intelligence_prompts.py` | Audit — may reference domain in historical prompts |
| 21 | `CLAUDE.md` | Update "Enrichment Properties" section — remove `domain` row; remove SmartSearch `domain_filter` reference |
| 22 | `docs/architecture/EMMA_AI.md`, `docs/architecture/SIL.md`, `docs/architecture/SLM_ROUTER.md` | Replace `domain` references with `document_type` or remove |
| 23 | `backend/docker/docker-compose.yml.saas`, `backend/docker/docker-compose.onpremise.yml` | Remove `ACTIVE_SECTOR` / `DOMAIN_*` env vars if present |

### 4.2 Out of scope

- Historical Alembic migrations in `backend/alembic/versions/_archived/**` — preserved verbatim
- Historical specs/plans in `docs/superpowers/specs/**` and `docs/superpowers/plans/**` — preserved as historical record
- The `DOMAIN=nouxcube.com` variable in `.env.example`, `deployment/gcp/.env.pre`, `deployment/gcp/.env.prod` — this is **URL domain**, a completely unrelated concept; do not touch
- Langfuse prompt `emma_react_system` content — **cannot be edited automatically by code**; we provide the corrected prompt text and the user promotes it via Langfuse UI after deploy

### 4.3 External coordination required

- **Langfuse**: after merging, the user must update `emma_react_system` prompt in Langfuse UI to remove any mention of `domain_filter` tool parameter. Failure to do so will cause the ReAct agent to emit `domain_filter=...` in tool calls, which the tool will reject with a schema validation error.

## 5. Data Flow (post-refactor)

```
Indexing:
  User upload / connector sync
    → intelligence-docs-service.classify_document(text, filename)
      → ClassificationResult(document_type, confidence, provider)   [domain removed]
    → weaviate-service.indexing_pipeline
      → ContextualRetrieval.analyze_document(text, {document_type})
        → context_prefix = generate_context_prefix(document_type, entities)
      → Weaviate write: Nouxcube_documents{document_type, semantic_type, roles, …}   [domain removed]
      → knowledge-tree-service.extract_triples(text, metadata)
        → FalkorDB nodes/rels                                        [domain field removed from entity metadata]

Query:
  User question
    → emma-agent-service.react_loop
      → LLM calls smart_search(query, semantic_type_filter?, person_filter?, folder_filter?)   [domain_filter removed]
      → weaviate-service.hybrid_search(filters without domain)
      → If legal context needed:
        → LLM calls graph_rag(entities, expansion) or knowledge_tree_client.get_applicable_laws(entities)
```

## 6. Error Handling

- **Orphaned references at runtime**: if any code path still reads `metadata["domain"]`, it will return `None` (no KeyError because `.get()` with default is the pattern). We audit all `.get("domain")` and `[:, "domain"]` access points explicitly during execution.
- **LLM tool-calling domain_filter**: prompts are updated pre-deploy; post-deploy, if the LLM still calls `domain_filter=...` from cache/habit, the tool schema validator rejects with clear error → LLM retries without the param on next iteration.
- **Tests**: any test asserting `.domain == "legal"` or `"domain" in result` is rewritten to assert on `document_type`.

## 7. Testing Strategy

1. **Unit**
    - `test_classifier.py`: verify `ClassificationResult` has no `domain` attribute
    - Weaviate schema tests: verify `Nouxcube_documents` collection has no `domain` property
    - SmartSearch tool schema test: verify `domain_filter` is not a valid parameter
2. **Integration**
    - Lightweight import check after each phase (`docker exec <container> python -c "from app.main import app"`)
    - After all phases: `docker compose restart api weaviate-service emma-agent-service intelligence-docs-service knowledge-tree-service` and verify healthy
3. **E2E**
    - `scripts/test_e2e_graph_rag.py`: run and verify ReAct agent still returns relevant results without `domain_filter`
    - Manual: upload a document via UI, run Emma query ("¿qué contratos tengo?"), verify `smart_search` is called with `semantic_type_filter=["contrato"]` (or similar) and not `domain_filter`

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Frontend shows `null` or `undefined` for removed `domain` field in a doc detail view | Medium | Low (visual glitch) | Remove the display during Phase 6 (frontend) |
| Connector metadata payloads still include `domain`, causing downstream confusion | Low | Low | Adapters updated in Phase 2 to stop emitting `domain`; backend accepts and ignores if present (backwards compat for externally-produced data) |
| Langfuse prompt not updated in time → agent tool-call validation errors for a window | Low | Medium | Provide the exact updated prompt text in PR description; ask user to promote in Langfuse immediately after merge |
| A `_detect_domain` / `detect_domain` caller we missed breaks at runtime | Low | Medium | Grep recursively for `detect_domain` as penultimate check before final commit |
| `contextualize_chunks.py` is actually used in some cron/scheduled job | Very Low | Medium | Confirmed standalone CLI script, no schedule reference in docker-compose.*.yml; safe to delete |

## 9. Success Criteria

- `git grep -l "domain" backend/ frontend/src/ docs/architecture/ CLAUDE.md README*.md | grep -v superpowers | grep -v alembic/versions/_archived` returns only legitimate occurrences (URL domain, DomainError exceptions, docstrings mentioning "business domain" in general).
- All 5 services import `app.main` without error (api, weaviate-service, emma-agent-service, intelligence-docs-service, knowledge-tree-service).
- `python -c "from app.services.rag.contextual_retrieval import *"` does not expose `LegalDomain`, `DomainDetectionResult`, or `detect_domain`.
- `smart_search` tool JSON schema has no `domain_filter` key.
- Nouxcube_documents Weaviate collection, recreated fresh, has no `domain` property.
- `analyze_document()` returns a `ContextGenerationResult` whose `context_prefix` mentions `document_type` and is generated from `document_type` + entities (no reference to domain).
- `backend/scripts/contextualize_chunks.py` deleted.
- `ACTIVE_SECTOR` removed from `backend/docker/.env` and compose files.
- CLAUDE.md "Enrichment Properties" section no longer lists `domain` as a first-class property.
- Langfuse `emma_react_system` promoted to new label version without `domain_filter` mention (tracked separately, out of this PR).

## 10. Implementation Phases (preview — detailed plan in separate doc)

1. **Phase 1** — Classifier (source of truth): `classifier.py`, `ClassificationResult`, `test_classifier.py` (components #1-3)
2. **Phase 2** — Contextual retrieval: `contextual_retrieval.py` (biggest change), `indexing_pipeline.py`, `context_enricher.py` (components #4, #9)
3. **Phase 3** — Entity extraction + TrustGraph entity schema: `weaviate-service/extraction_service.py`, `knowledge-tree-service/schemas/triples.py`, `extractors/coordinator.py`, `triple_store.py`, relevant tests, `background-worker/trustgraph_tasks.py` (components #5, #13, #14)
4. **Phase 4** — Weaviate schema + indexing + search: `schemas/weaviate.py`, `weaviate_service.py`, `api/weaviate.py` (components #6-8)
5. **Phase 5** — Emma agent: `smart_search.py`, `sectors/config.py`, other emma service refs, `migrate_retrieval_intelligence_prompts.py` audit (components #10-12, #20)
6. **Phase 6** — Backend API + connectors: `backend/app/**`, `core/connectors/**` (components #15-16)
7. **Phase 7** — Frontend + scripts cleanup: `data-learning.service.ts`, delete `contextualize_chunks.py`, cleanup `ACTIVE_SECTOR` in `.env` + compose files (components #17-19, #23)
8. **Phase 8** — Docs: CLAUDE.md, architecture docs (components #21-22)
9. **Phase 9** — Final verification + Langfuse prompt handoff note

Each phase ends with a lightweight verification (import check + grep) and optionally a commit (or a single consolidated commit at the end, per user preference established for PublicKnowledge cleanup).

## 11. Open Questions

None. Defaults adopted from user's PublicKnowledge-cleanup preferences:
- Work directly on `development` branch (no feature branch)
- Lightweight verification between phases (import check + grep)
- Single consolidated commit at the end (vs. one-per-phase) — confirm at commit time
