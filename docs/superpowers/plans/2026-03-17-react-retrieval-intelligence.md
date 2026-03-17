# ReAct Retrieval Intelligence — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ReAct agent smarter about retrieval — use existing filters, get immediate feedback on search quality, and decompose complex queries.

**Architecture:** Three phases, each building on the previous. Phase 1 is prompt-only (zero code). Phase 2 adds heuristic evaluation inline in smart_search output. Phase 3 adds PLANNER LLM decomposition for complex queries.

**Tech Stack:** Langfuse prompts, SmartSearch tool (Weaviate hybrid), PLANNER LLM (Qwen3.5-9B), existing enrichment filters (date_from, date_to, person_filter, domain_filter, semantic_type_filter)

**Spec:** `docs/superpowers/specs/2026-03-17-react-retrieval-intelligence-design.md`

---

## File Structure

### Files to Modify

```
config/prompts/emma_prompts.yaml                    # Phase 1: add filter guidance to react_agent.system
agents/langgraph/nodes/react_loop.py                # Phase 1: inject current_date into system prompt
agents/langgraph/tools/smart_search.py              # Phase 2+3: feedback eval + decomposition
agents/langgraph/retrieval_guard.py                  # Phase 2: deprecate (subsumed by inline eval)
agents/langgraph/quality_gate.py                     # Phase 2: read eval from tool output metadata
app/core/config.py                                   # All phases: feature flags
app/services/prompt_registry.py                      # Phase 3: register decompose prompt
app/api/diagnostics.py                               # Phase 1: add filter E2E checks (DONE)
```

### Langfuse Prompts

```
emma_react_system                                    # Phase 1: add filter guidance section
emma_smart_search_decompose (NEW)                    # Phase 3: query decomposition prompt
```

---

## Chunk 1: Phase 1 — Prompt-Driven Filter Guidance

### Task 1: Add current_date to ReAct system prompt

**Files:**
- Modify: `app/agents/langgraph/nodes/react_loop.py`

- [ ] **Step 1: Read how system prompt is built in react_loop**

The `_load_react_system_prompt()` function loads from Langfuse. The prompt is injected with `{tools_description}` placeholder. We need to also inject `{current_date}`.

Read `react_loop.py` to find where the system prompt is formatted with tools_description.

- [ ] **Step 2: Add current_date injection**

In `react_loop_node()`, where the system prompt is formatted with `tools_description`, also inject `current_date`:

```python
from datetime import date

system_prompt = raw_prompt.replace("{tools_description}", tools_desc)
system_prompt = system_prompt.replace("{current_date}", date.today().isoformat())
```

- [ ] **Step 3: Verify syntax**

```bash
cd backend/microservices/emma-agent-service && python3 -c "import ast; ast.parse(open('app/agents/langgraph/nodes/react_loop.py').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add app/agents/langgraph/nodes/react_loop.py
git commit -m "feat(react): inject current_date into ReAct system prompt"
```

---

### Task 2: Update ReAct system prompt with filter guidance

**Files:**
- Modify: `config/prompts/emma_prompts.yaml` — `react_agent.system` section
- Modify: Langfuse prompt `emma_react_system` (via seed script)

- [ ] **Step 1: Add filter guidance to YAML prompt**

In `emma_prompts.yaml` under `react_agent: system:`, add after the "Paso 2: BUSCAR" section:

```yaml
    ### Filtros de búsqueda (IMPORTANTE)
    Cuando el usuario mencione fechas, períodos, personas, empresas o tipos de documento,
    SIEMPRE usa los parámetros de filtro de smart_search:
    - date_from / date_to: Fechas ISO 8601 (ej: "facturas de 2024" → date_from="2024-01-01", date_to="2024-12-31")
    - person_filter: Nombre de persona o empresa (ej: "contratos de ACME" → person_filter="ACME")
    - semantic_type_filter: Tipo de documento (ej: "facturas" → semantic_type_filter="factura")
    - domain_filter: Dominio (ej: "documentos laborales" → domain_filter="laboral")

    Hoy es {current_date}. Para fechas relativas:
    - "último mes" → date_from/date_to del mes anterior completo
    - "este año" → date_from del 1 de enero del año actual
    - "últimos 3 meses" → date_from = hace 3 meses desde hoy
    - "del primer trimestre" → date_from enero, date_to marzo

    ⚠️ NO uses filtros temporales para búsquedas de legislación (scope=legislation).
    La legislación no tiene fecha de creación en el sistema.
```

- [ ] **Step 2: Seed to Langfuse**

```bash
docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --force --section react
```

- [ ] **Step 3: Verify prompt loads with current_date**

```bash
docker compose exec emma-agent-service python -c "
import asyncio
from app.services.langfuse_prompt_client import get_langfuse_prompt_client
async def test():
    client = get_langfuse_prompt_client()
    p = await client.get_prompt('emma_react_system')
    print('Has current_date placeholder:', '{current_date}' in p.content)
    print('Has filter section:', 'date_from' in p.content)
asyncio.run(test())
"
```

Expected: both True

- [ ] **Step 4: Commit**

```bash
git add config/prompts/emma_prompts.yaml
git commit -m "feat(prompts): add filter guidance + current_date to ReAct system prompt"
```

---

### Task 3: Add feature flag

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Add feature flags for all 3 phases**

```python
# Smart Search Retrieval Intelligence
smart_search_feedback_enabled: bool = os.getenv("SMART_SEARCH_FEEDBACK_ENABLED", "true").lower() == "true"
smart_search_decompose_enabled: bool = os.getenv("SMART_SEARCH_DECOMPOSE_ENABLED", "false").lower() == "true"
```

Phase 1 needs no flag (prompt-only). Phase 2 defaults on. Phase 3 defaults off (opt-in).

- [ ] **Step 2: Commit**

```bash
git add app/core/config.py
git commit -m "feat(config): add smart_search feedback + decompose feature flags"
```

---

### Task 4: E2E Test — Verify LLM uses filters

- [ ] **Step 1: Run sanity check**

```bash
cd backend/docker && bash sanity-check.sh all
```

Expected: 23/23 ALL OK (including smart_search_temporal and smart_search_person)

- [ ] **Step 2: Manual test via curl — temporal filter**

```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)
curl -s -X POST http://localhost:8009/emma/query/stream \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "busca facturas de 2024",
    "tenant_id": "00000000-0000-0000-0000-000000000001"
  }' | grep -o '"date_from":[^,}]*' | head -3
```

If the LLM uses the filter, the SSE stream will contain tool_call events with `date_from` in the arguments.

- [ ] **Step 3: Commit Phase 1 completion tag**

```bash
git tag phase1-filter-guidance
```

---

## Chunk 2: Phase 2 — Retrieval Feedback Loop

### Task 5: Add _evaluate_results() to SmartSearchTool

**Files:**
- Modify: `app/agents/langgraph/tools/smart_search.py`

- [ ] **Step 1: Read current _format_results() method**

Read `smart_search.py:956-1035` to understand how results are formatted today. The evaluation block will be appended after the results text, before the sources.

- [ ] **Step 2: Implement _evaluate_results()**

Add a new method to `SmartSearchTool`:

```python
def _evaluate_results(
    self,
    query: str,
    results: List[Dict[str, Any]],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    person_filter: Optional[str] = None,
    dropped_filters: Optional[List[str]] = None,
) -> str:
    """Inline evaluation of search results for immediate agent feedback.

    Heuristic checks (~0ms, no LLM):
    1. Temporal mismatch — dates in results vs requested range
    2. Entity coverage — query entities in result titles
    3. Relevance distribution — average score, single-source bias
    4. Filter drop notice — which filters were dropped
    """
    feedback = []

    # 1. Temporal check
    if date_from or date_to:
        result_dates = [r.get("created_at", "") for r in results if r.get("created_at")]
        if result_dates:
            in_range = sum(1 for d in result_dates
                          if (not date_from or d >= date_from) and (not date_to or d <= date_to))
            if in_range == 0:
                feedback.append(f"- Temporal: Filtro {date_from or '?'}→{date_to or '?'} pero 0 resultados en rango. Reformula con otros términos.")
            elif in_range < len(result_dates):
                feedback.append(f"- Temporal: {in_range}/{len(result_dates)} resultados en el rango solicitado.")

    # 2. Entity coverage
    if person_filter and results:
        matches = sum(1 for r in results
                      if person_filter.lower() in (r.get("title", "") + r.get("content", "")).lower())
        if matches == 0:
            feedback.append(f"- Persona/Entidad: '{person_filter}' no aparece en ningún resultado.")

    # 3. Relevance
    if results:
        scores = [r.get("score") or 0 for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0
        if avg_score < 0.4:
            feedback.append(f"- Relevancia: promedio {avg_score:.2f} (bajo). Reformula con términos más específicos.")
        doc_ids = set(r.get("document_id", "") for r in results if r.get("document_id"))
        if len(doc_ids) == 1 and len(results) > 1:
            feedback.append("- Fuente única: todos los resultados del mismo documento.")

    # 4. Filter drops
    if dropped_filters:
        feedback.append(f"- Filtros descartados (sin resultados): {', '.join(dropped_filters)}.")

    if not feedback:
        return ""

    return "\n⚠️ EVALUACIÓN DE RESULTADOS:\n" + "\n".join(feedback)
```

- [ ] **Step 3: Integrate into _format_results()**

In `_format_results()`, after the results text and before returning, append the evaluation:

```python
# After existing retrieval_guard warnings (line ~1035)
if settings.smart_search_feedback_enabled:
    eval_text = self._evaluate_results(
        query=query, results=results,
        date_from=..., date_to=...,
        person_filter=..., dropped_filters=dropped_filters,
    )
    if eval_text:
        parts.append(eval_text)
```

Note: `_format_results` needs access to the original filter arguments. Thread `date_from`, `date_to`, `person_filter` through from `execute()`.

- [ ] **Step 4: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('app/agents/langgraph/tools/smart_search.py').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add app/agents/langgraph/tools/smart_search.py
git commit -m "feat(smart_search): add inline retrieval feedback evaluation"
```

---

### Task 6: Deprecate retrieval_guard inline warnings

**Files:**
- Modify: `app/agents/langgraph/retrieval_guard.py`

- [ ] **Step 1: Add deprecation notice**

Add to top of file:
```python
"""
DEPRECATED: Retrieval guard inline warnings are superseded by
SmartSearchTool._evaluate_results() (Phase 2 Retrieval Intelligence).

The assess_retrieval_quality() function is still called by smart_search.py
for metadata population (Quality Gate 4 reads last_retrieval_quality).
The warnings list is no longer appended to tool output when
SMART_SEARCH_FEEDBACK_ENABLED=true.
"""
```

- [ ] **Step 2: Commit**

```bash
git add app/agents/langgraph/retrieval_guard.py
git commit -m "docs: deprecate retrieval_guard warnings (superseded by inline feedback)"
```

---

### Task 7: Test Phase 2

- [ ] **Step 1: Run sanity checks**

```bash
bash sanity-check.sh all
```

Expected: 23/23 ALL OK

- [ ] **Step 2: Manual test — trigger low relevance feedback**

Search for something unlikely to have results:

```bash
curl -s -X POST http://localhost:8009/emma/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "busca documentos sobre nanotecnología cuántica",
    "tenant_id": "00000000-0000-0000-0000-000000000001"
  }' > /tmp/feedback_test.json
python3 -c "import json; r=json.load(open('/tmp/feedback_test.json')); print(r.get('answer', '')[:500])"
```

If feedback works, the answer should mention reformulating the search (guided by the inline evaluation).

- [ ] **Step 3: Commit Phase 2 tag**

```bash
git tag phase2-retrieval-feedback
```

---

## Chunk 3: Phase 3 — Query Decomposition

### Task 8: Register decomposition prompt

**Files:**
- Modify: `app/services/prompt_registry.py`
- Modify: `config/prompts/emma_prompts.yaml`

- [ ] **Step 1: Add prompt to registry**

```python
"emma_smart_search_decompose": PromptEntry(
    yaml_path=("smart_search", "decompose"),
    description="Decompose complex search query into independent sub-queries",
    section="smart_search",
),
```

- [ ] **Step 2: Add YAML content**

```yaml
smart_search:
  decompose: |
    Descompón esta búsqueda en sub-consultas independientes para buscar en paralelo.
    Preserva el contexto compartido (fechas, personas, filtros) en cada sub-consulta.

    Responde SOLO con un array JSON (sin markdown, sin explicaciones):
    [
      {"query": "sub-consulta 1", "scope": "documents|legislation|auto"},
      {"query": "sub-consulta 2", "scope": "documents|legislation|auto"}
    ]
    O [] si la búsqueda no necesita descomposición (es simple).

    Reglas:
    - Máximo 3 sub-consultas
    - Cada sub-consulta debe ser autocontenida (incluir fechas, persona si aplica)
    - Si la búsqueda mezcla documentos + legislación, separar por scope
    - NO descompongas búsquedas simples de un solo tema

    Búsqueda: {query}
```

- [ ] **Step 3: Seed to Langfuse**

```bash
docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --force --section smart_search
```

- [ ] **Step 4: Commit**

```bash
git add app/services/prompt_registry.py config/prompts/emma_prompts.yaml
git commit -m "feat(prompts): add smart_search decomposition prompt"
```

---

### Task 9: Implement query decomposition in SmartSearchTool

**Files:**
- Modify: `app/agents/langgraph/tools/smart_search.py`

- [ ] **Step 1: Add _is_complex_query() heuristic**

```python
def _is_complex_query(self, query: str) -> bool:
    """Detect queries that would benefit from decomposition."""
    if not settings.smart_search_decompose_enabled:
        return False
    if len(query) < 80:
        return False

    query_lower = query.lower()

    # Scope mixing: document + legislation keywords
    has_doc = any(kw in query_lower for kw in ("contrato", "factura", "nómina", "documento"))
    has_leg = any(kw in query_lower for kw in ("ley", "estatuto", "código", "real decreto", "artículo", "boe"))
    if has_doc and has_leg:
        return True

    # Conjunction with distinct topics
    conjunctions = (" y ", " además ", " también ", " por otro lado ", " comparar ", " compara ")
    if any(c in query_lower for c in conjunctions) and len(query) > 100:
        return True

    return False
```

- [ ] **Step 2: Add _decompose_query() with PLANNER LLM**

```python
async def _decompose_query(self, query: str) -> List[Dict[str, str]]:
    """Decompose complex query into sub-queries via PLANNER LLM (~100ms)."""
    try:
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_planner_model

        client = get_langfuse_prompt_client()
        prompt = await client.get_prompt(
            "emma_smart_search_decompose",
            variables={"query": query},
        )

        model = get_planner_model().bind(temperature=0.1, max_tokens=300)
        response = await model.ainvoke([
            SystemMessage(content=prompt.content),
            HumanMessage(content=f"/no_think\n{query}"),
        ])

        import json, re
        content = (response.content or "").strip()
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        sub_queries = json.loads(content)

        if isinstance(sub_queries, list) and len(sub_queries) >= 2:
            return sub_queries[:3]  # Cap at 3
    except Exception as e:
        logger.warning(f"Query decomposition failed: {e}")

    return []  # Fallback: no decomposition
```

- [ ] **Step 3: Add _merge_and_dedup()**

```python
def _merge_and_dedup(self, result_sets: List[List[Dict]]) -> List[Dict]:
    """Merge results from multiple sub-queries, dedup by document_id."""
    seen = set()
    merged = []
    for results in result_sets:
        for r in results:
            doc_id = r.get("document_id", "")
            key = doc_id or r.get("title", "")
            if key and key not in seen:
                seen.add(key)
                merged.append(r)
    # Sort by score descending
    merged.sort(key=lambda r: r.get("score") or 0, reverse=True)
    return merged
```

- [ ] **Step 4: Wire into execute()**

At the beginning of `execute()`, after argument parsing and before the main search:

```python
# Query decomposition (Phase 3)
if self._is_complex_query(query):
    sub_queries = await self._decompose_query(query)
    if sub_queries:
        # Execute sub-queries in parallel
        import asyncio
        sub_results = await asyncio.gather(*[
            self._search_tenant_documents(
                query=sq["query"], tenant_id=tenant_id, limit=limit,
                scope=sq.get("scope", "auto"), ...
            )
            for sq in sub_queries
        ])
        merged = self._merge_and_dedup(sub_results)
        if merged:
            logger.info(f"Decomposed '{query[:60]}' into {len(sub_queries)} sub-queries → {len(merged)} merged results")
            # Continue with merged results through normal formatting
```

- [ ] **Step 5: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('app/agents/langgraph/tools/smart_search.py').read()); print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add app/agents/langgraph/tools/smart_search.py
git commit -m "feat(smart_search): add LLM query decomposition for complex searches (Phase 3)"
```

---

### Task 10: Test Phase 3

- [ ] **Step 1: Enable feature flag**

```bash
# In backend/docker/.env, add:
SMART_SEARCH_DECOMPOSE_ENABLED=true
docker compose restart emma-agent-service
```

- [ ] **Step 2: Run sanity checks**

```bash
bash sanity-check.sh all
```

Expected: 23/23 ALL OK

- [ ] **Step 3: Test decomposition**

```bash
curl -s -X POST http://localhost:8009/emma/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "Compara los contratos de trabajo con lo que dice el Estatuto de Trabajadores sobre indemnización por despido",
    "tenant_id": "00000000-0000-0000-0000-000000000001"
  }' > /tmp/decompose_test.json
python3 -c "
import json
r = json.load(open('/tmp/decompose_test.json'))
print('Success:', r.get('success'))
print('Answer length:', len(r.get('answer', '')))
# Check logs for decomposition
"
```

Check logs for: `Decomposed '...' into N sub-queries → M merged results`

- [ ] **Step 4: Commit tag**

```bash
git tag phase3-query-decomposition
```

---

## Chunk 4: Final Verification

### Task 11: Full E2E verification

- [ ] **Step 1: Run all sanity checks**

```bash
bash sanity-check.sh all
```

Expected: 23/23 ALL OK

- [ ] **Step 2: Verify no broken imports**

```bash
cd backend/microservices/emma-agent-service
python3 -c "
import ast, glob
errors = []
for f in glob.glob('app/**/*.py', recursive=True):
    try:
        with open(f) as fh: ast.parse(fh.read())
    except SyntaxError as e: errors.append(f'{f}: {e}')
print(f'{len(errors)} errors' if errors else 'All files compile OK')
"
```

- [ ] **Step 3: Test matrix**

| Test | Command | Expected |
|------|---------|----------|
| Temporal filter | `"facturas de 2024"` via /query | Agent passes date_from/date_to |
| Person filter | `"contratos de ACME"` via /query | Agent passes person_filter |
| No temporal on legislation | `"legislación laboral vigente"` via /query | No date_from/date_to |
| Low relevance feedback | `"nanotecnología cuántica"` via /query | Answer mentions reformulating |
| Decomposition | `"contratos + ET sobre despido"` via /query | Logs show decomposed sub-queries |
| Simple query (no decomp) | `"busca facturas"` via /query | No decomposition (too short) |

- [ ] **Step 4: Final commit**

```bash
git add -A
git status
# Commit only if there are uncommitted fixes
```
