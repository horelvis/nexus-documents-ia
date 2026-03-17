# ReAct Retrieval Intelligence — Design Spec

**Date:** 2026-03-17
**Status:** Approved (v2 — post-review)
**Scope:** Three incremental improvements to ReAct agent retrieval behavior

---

## Context

After consolidating Emma into a single LangGraph engine (ReAct agent with 13 tools, -9,170 lines cleanup), the retrieval pipeline is the next quality bottleneck. Emma already implements the major RAG patterns from the literature. The remaining issues are:

1. The LLM doesn't use existing temporal/entity filters in `smart_search` (params exist but unused)
2. The agent doesn't learn from bad search results until it tries to terminate
3. Complex multi-faceted queries produce diluted results

---

## Phase 1: Prompt-Driven Filter Guidance

### Problem

SmartSearch already has `date_from`, `date_to`, `person_filter`, `domain_filter`, `semantic_type_filter` as tool parameters. The LLM simply doesn't use them — it sends the full query as a keyword search and ignores the filter fields.

### Solution — Prompt First (Zero Code)

**Step 1: Improve the ReAct system prompt** (Langfuse `emma_react_system`). Add explicit guidance:

```
### Filtros de búsqueda (IMPORTANTE)
Cuando el usuario mencione fechas, períodos, personas, empresas o tipos de documento,
SIEMPRE usa los parámetros de filtro de smart_search:
- date_from / date_to: Fechas ISO (ej: "facturas de 2024" → date_from="2024-01-01", date_to="2024-12-31")
- person_filter: Nombre de persona o empresa (ej: "contratos de ACME" → person_filter="ACME")
- semantic_type_filter: Tipo de documento (ej: "facturas" → semantic_type_filter="factura")
- domain_filter: Dominio (ej: "documentos laborales" → domain_filter="laboral")

Hoy es {current_date}. Para fechas relativas:
- "último mes" → date_from del mes anterior, date_to fin del mes anterior
- "este año" → date_from="2026-01-01"
- "últimos 3 meses" → date_from = hace 3 meses desde hoy
```

**Step 2: Inject `current_date` into the system prompt** — the rewrite/react_loop already has access to datetime. Add `{current_date}` as a template variable for relative date resolution.

**Step 3: Verify with sanity check** — test "facturas de 2024" and confirm the LLM passes `date_from`/`date_to`.

**Step 4: Only if prompt fails** — add a lightweight PLANNER call (~100ms) in `classify_node` for structured filter extraction. This is the fallback, not the default approach.

### Files

| File | Change |
|------|--------|
| Langfuse `emma_react_system` prompt | Add filter guidance section + `{current_date}` variable |
| `nodes/react_loop.py` | Inject `current_date` into system prompt variables |
| `app/core/config.py` | Feature flag `SMART_SEARCH_FILTER_GUIDANCE_ENABLED` (default true) |

### Edge Cases

- **Temporal on legislation:** `date_from`/`date_to` should NOT apply when `scope=legislation` (BOE legislation has no meaningful `created_at`). Add note in the prompt: "No uses filtros temporales para búsquedas de legislación."
- **Relative dates:** LLM needs `current_date` in prompt to resolve "último mes", "hace 2 meses", etc.
- **Multi-language:** ReAct prompt is in Spanish but users may write in English. The LLM handles both natively — the filter fields are language-agnostic (ISO dates, entity names).
- **Entity vs person:** `person_filter` is used for both people and companies. The description already says "persona o empresa". Works as-is.

---

## Phase 2: Retrieval Feedback Loop

### Problem

When SmartSearch returns bad results, the agent doesn't know until it tries to terminate. `retrieval_guard` injects warnings post-search, and `quality_gate` catches bad answers — but both are reactive (1-2 wasted ReAct steps).

### Solution

Move result evaluation **inside the `smart_search` tool output**, so the agent sees feedback immediately.

**Output today:**
```
Se encontraron 5 documentos relevantes:
[1] Contrato ACME 2022 (score: 0.85)
...
```

**Output after:**
```
Se encontraron 5 documentos relevantes:
[1] Contrato ACME 2022 (score: 0.85)
...

⚠️ EVALUACIÓN:
- Temporal: Pediste "2024" pero los resultados son de 2021-2022. Usa date_from/date_to.
- Entidades: "ACME" encontrado en 5/5 resultados ✓
- Relevancia: promedio 0.72 (aceptable)
```

### Implementation

Heuristic evaluation block at end of `SmartSearchTool.execute()`, ~0ms:

1. **Temporal check** — If `date_from`/`date_to` was passed, verify result dates fall within range. If not passed but query mentions years/dates (simple keyword check), flag the mismatch.
2. **Entity coverage** — Check if query entities appear in result titles/content. Flag low coverage.
3. **Relevance distribution** — All results below 0.5 → "low relevance". All from same doc → "single source".
4. **Filter drop notice** — SmartSearch already drops filters progressively. When it drops, report which filter.

**Relationship with retrieval_guard.py:** The guard checks 3 things (no results, low top_score, single source). Phase 2 subsumes all 3 plus adds temporal and entity checks. After Phase 2:
- `retrieval_guard.py` deprecated — its inline warnings in `_format_results()` replaced by the structured evaluation block
- Quality Gate 4 (`last_retrieval_quality` in metadata) — populated by the new evaluation block instead of retrieval_guard. Same metadata key, same consumer.

### Files

| File | Change |
|------|--------|
| `tools/smart_search.py` | Add `_evaluate_results()` method, call at end of `execute()` |
| `retrieval_guard.py` | Deprecate (keep for backwards compat, no functional changes) |
| `quality_gate.py` | Read evaluation from tool result metadata instead of `last_retrieval_quality` |
| `app/core/config.py` | Feature flag `SMART_SEARCH_FEEDBACK_ENABLED` (default true) |

---

## Phase 3: Query Decomposition for Retrieval

### Problem

"Compara las cláusulas de penalización en los contratos de ACME con lo que dice el Estatuto de Trabajadores sobre indemnización" is sent as one query. SmartSearch tries to detect scope but a mixed query produces confused results.

### Solution

When SmartSearch receives a complex query, use a **PLANNER LLM call** (~100ms) to decompose into independent sub-queries executed in parallel.

**Why LLM, not heuristic:** Conjunction splitting ("y", "con") produces malformed sub-queries. "Compara X con Y" requires semantic understanding to extract X and Y correctly. "Facturas y nóminas de enero" needs shared context ("de enero") preserved in both sub-queries. The PLANNER handles this natively.

### Implementation

```python
# Inside SmartSearchTool.execute():
if self._is_complex_query(query):
    sub_queries = await self._decompose_query(query)  # PLANNER LLM ~100ms
    if sub_queries and len(sub_queries) > 1:
        results = await asyncio.gather(*[self._search_single(sq) for sq in sub_queries])
        merged = self._merge_and_dedup(results)
        # Compare: if merged is worse than single query, use single
        single_result = await self._search_single(query)
        return self._pick_better(merged, single_result)
    # Fallback: single query
```

**Complexity detection** (heuristic, no LLM):
- Scope mixing: document keywords + legislation keywords in same query
- Multiple distinct entity names (regex: 2+ capitalized multi-word sequences)
- Query length > 100 chars with conjunction keywords

**Decomposition** (PLANNER LLM):
```
Descompón esta búsqueda en sub-consultas independientes.
Preserva el contexto compartido (fechas, filtros) en cada sub-consulta.
Responde JSON: [{"query": "...", "scope": "documents|legislation|auto"}, ...]
O [] si no necesita descomposición.

Búsqueda: "{query}"
```

**Fallback:** If decomposed results are worse (lower avg relevance, fewer total), use single query result. The Phase 2 evaluation block scores both and picks the better one.

### Files

| File | Change |
|------|--------|
| `tools/smart_search.py` | Add `_is_complex_query()`, `_decompose_query()`, `_merge_and_dedup()` |
| Langfuse prompt | New `emma_smart_search_decompose` prompt |
| `app/core/config.py` | Feature flag `SMART_SEARCH_DECOMPOSE_ENABLED` (default false — opt-in) |
| `app/services/prompt_registry.py` | Register new prompt |

---

## Implementation Order

```
Phase 1 (Prompt guidance)  →  Phase 2 (Feedback loop)  →  Phase 3 (Decomposition)
   ~0ms, prompt only           ~0ms, heuristics            ~100ms, PLANNER LLM
   Langfuse edit               smart_search.py             smart_search.py + Langfuse
```

Phase 1 is prompt-only (can be done and tested in minutes). Phase 2 is the main code change. Phase 3 is opt-in (feature flag off by default).

---

## Files Summary

| Phase | Files |
|-------|-------|
| 1 | Langfuse `emma_react_system`, `nodes/react_loop.py`, `config.py` |
| 2 | `tools/smart_search.py`, `retrieval_guard.py`, `quality_gate.py`, `config.py` |
| 3 | `tools/smart_search.py`, Langfuse new prompt, `prompt_registry.py`, `config.py` |

**Total unique files:** 7 + 2 Langfuse prompts

---

## What We're NOT Doing

- No new tools — improvements inside existing `smart_search` + prompts
- No new graph nodes — no topology changes
- No MemoRAG integration — existing retrieval stack is sufficient
- No new infrastructure — uses existing Weaviate filters + enrichment properties
- Phase 3 decomposition uses PLANNER LLM (not fragile regex heuristics)

---

## Verification

After each phase:
```bash
cd backend/docker && bash sanity-check.sh all
```

| Phase | Test | Expected |
|-------|------|----------|
| 1 | "facturas de 2024" | LLM passes `date_from=2024-01-01, date_to=2024-12-31` to smart_search |
| 1 | "contratos de ACME del último trimestre" | `person_filter=ACME` + temporal filter |
| 1 | "legislación laboral vigente" | No temporal filter (legislation scope) |
| 2 | Search returns wrong dates | Feedback: "Temporal mismatch" in tool output |
| 2 | Search returns 0 results | Feedback: "Sin resultados, reformula" |
| 3 | "compara contratos ACME con ET sobre indemnización" | Decomposed into 2 sub-queries, merged results |
| 3 | Simple query "busca facturas" | No decomposition (complexity check fails) |
