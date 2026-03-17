# LangGraph Sub-Graph Consolidation — Design Spec

**Date:** 2026-03-17
**Status:** Approved (v2 — post-review)
**Scope:** Absorb Verified Generation and Predictive Analysis into the ReAct agent as sub-graph tools

---

## Context

After removing ~9,400 lines of legacy code (Emma v2, orchestration routers, YAML prompt system), LangGraph is the single orchestration engine. Two subsystems still operate outside the ReAct agent graph:

- **Verified Generation** — claim-by-claim document generation with two-tier verification
- **Predictive Analysis** — factor extraction, outcome evaluation, and recommendation synthesis

Both use a stop-and-go graph pattern (`stop_and_go/`, 15 files, **3,195 lines**) with a strategy pattern dispatch, separate API endpoints, and their own SSE streaming.

**Problem:** Three execution paths, two state types, two streaming patterns. The stop-and-go pattern duplicates routing, checkpointing, and error handling that LangGraph provides natively.

---

## Architecture

### Before

```
/emma/query          → ReAct graph (ReActState)
/emma/verified/*     → StopAndGo runner → StopAndGoState
/emma/predictive/*   → StopAndGo runner → StopAndGoState
```

### After

```
/emma/query → ReAct graph (ReActState)
                 ├── classify → "verified" intent
                 │   └── react_loop → tool: verified_generation
                 │       └── VerifiedGenGraph (VerifiedGenState) → claim events → ToolResult
                 ├── classify → "predictive" intent
                 │   └── react_loop → tool: predictive_analysis
                 │       └── PredictiveGraph (PredictiveState) → factor events → ToolResult
                 └── classify → normal intent
                     └── react_loop → smart_search, analyze_domain, etc.
```

Single entry point. The ReAct agent invokes verification/prediction as tools. Each sub-graph has dedicated state and emits custom SSE events.

---

## Sub-Graph Design

### Verified Generation Graph (4 nodes + HITL)

```
START → generate_claim → verify_claim → decide ──→ END
              ↑                           │
              └────── more_claims ────────┘
                                          │
                                  [HITL: review] ← (if hitl_enabled + low confidence)
```

**State** (complete — mirrors StopAndGoState fields used by verified strategy):

```python
class VerifiedGenState(TypedDict, total=False):
    # Session
    session_id: str
    tenant_id: str
    user_id: Optional[str]

    # Input
    query: str
    source_context: str
    uploaded_texts: List[Dict]
    collections: List[str]
    context_document_ids: List[str]
    source_document_ids: List[str]
    source_filenames: List[str]

    # Configuration
    max_claims: int
    confidence_threshold: float
    auto_correct: bool
    mode_config: Dict[str, Any]  # fidelity_cap, max_evidence, document_type

    # Loop
    current_step: int
    items_extracted: int
    items_accepted: int
    items_rejected: int
    items_corrected: int
    duplicate_streak: int
    is_complete: bool

    # Section-Windowed Generation
    source_sections: List[str]
    current_section_index: int
    section_claims_count: List[int]

    # Evidence
    jurisprudence_evidence: List[Dict]
    source_doi_validations: List[Dict]

    # Items
    all_extracted_items: List[Dict]
    current_item: Optional[Dict]

    # HITL
    hitl_enabled: bool
    review_payload: Optional[Dict]
    review_response: Optional[Dict]

    # SSE
    pending_events: Annotated[List[Dict], merge_lists]

    # Output
    result: Optional[Dict]
    sources_map: Dict[str, Dict]
    metadata: Annotated[Dict[str, Any], merge_dicts]
```

### Predictive Analysis Graph (4 nodes)

```
START → extract_factor → evaluate_outcome → decide → END
              ↑                               │
              └────────── more_factors ────────┘
```

**State** (complete):

```python
class PredictiveState(TypedDict, total=False):
    # Session
    session_id: str
    tenant_id: str
    user_id: Optional[str]

    # Input
    query: str
    source_context: str
    uploaded_texts: List[Dict]
    collections: List[str]
    context_document_ids: List[str]
    source_document_ids: List[str]
    source_filenames: List[str]

    # Configuration
    max_factors: int
    confidence_threshold: float
    mode_config: Dict[str, Any]  # sector override, outcome labels, weights

    # Loop
    current_step: int
    items_extracted: int
    items_accepted: int
    items_rejected: int
    duplicate_streak: int
    is_complete: bool

    # Evidence
    jurisprudence_evidence: List[Dict]

    # Items
    all_extracted_items: List[Dict]
    current_item: Optional[Dict]

    # Evaluation
    outcomes: List[Dict]
    weights: List[Dict]

    # SSE
    pending_events: Annotated[List[Dict], merge_lists]

    # Output
    result: Optional[Dict]
    sources_map: Dict[str, Dict]
    metadata: Annotated[Dict[str, Any], merge_dicts]
```

### Sub-graph compilation

**Standard mode** (no HITL):
```python
verified_graph = verified_builder.compile(checkpointer=False)
predictive_graph = predictive_builder.compile(checkpointer=False)
```

**HITL mode** (verified only — human review of low-confidence claims):
```python
# When hitl_enabled=True, compile with checkpointer for interrupt/resume
verified_graph_hitl = verified_builder.compile(checkpointer=True)
```

See HITL section below.

---

## HITL (Human-in-the-Loop) — Phased Approach

**Phase 1 (this spec):** Non-HITL path only. Sub-graphs compile with `checkpointer=False`. The tool wrapper calls `graph.ainvoke()` and returns the full result. This covers the majority of usage (~95% of verified generations don't trigger HITL).

**Phase 2 (follow-up spec):** Re-enable HITL for verified generation. The `VerifiedGenerationTool` detects `hitl_enabled=True` in context, compiles the sub-graph with `checkpointer=True`, and uses `interrupt()` in the `decide` node when a claim falls below the confidence threshold. The parent ReAct graph's `/emma/query/resume/stream` endpoint handles resume via `Command(resume=...)`.

**Known regression during Phase 1:** HITL review is unavailable. Config `verified_hitl_enabled` is ignored. Document as a temporary limitation.

---

## SSE Streaming

### Pattern: `pending_events` (kept from stop-and-go)

After review, `get_stream_writer()` does **not** propagate through `graph.ainvoke()` inside tool wrappers. The existing `pending_events` + state snapshot drain pattern is preserved for sub-graphs.

Each sub-graph node appends events to `pending_events: Annotated[List, merge_lists]`. The tool wrapper streams the sub-graph with `astream(stream_mode="values")`, drains new events from each snapshot, and re-emits them to the parent's SSE stream.

```python
class VerifiedGenerationTool(EmmaTool):
    async def execute(self, arguments, context) -> ToolResult:
        graph = get_verified_gen_graph()
        events_seen = 0
        final_state = None
        async for state in graph.astream(initial_state, stream_mode="values"):
            # Drain new events
            all_events = state.get("pending_events", [])
            for event in all_events[events_seen:]:
                context["emit_sse"](event)  # callback to parent SSE
            events_seen = len(all_events)
            final_state = state
        return ToolResult(output=final_state["result"]["document_text"], ...)
```

### Event Types

**Verified generation events:**
- `claim_generated` — new claim text
- `claim_verified` — verification verdict (supported/unsupported/corrected)
- `claim_corrected` — auto-corrected claim
- `section_advanced` — windowed generation moved to next section
- `document_complete` — final document with DOI validations
- `progress` — step counter update
- `error` — verification error

**Predictive analysis events:**
- `factor_extracted` — new factor identified
- `factor_weighted` — factor weight assigned
- `factor_rejected` — factor didn't meet threshold
- `outcome_evaluated` — evidence assessed against factor
- `prediction_ready` — final recommendation + confidence
- `progress` — step counter update
- `error` — analysis error

**ReAct agent events (renamed):**
- `slm_thinking` → `agent_reasoning`

---

## Tool Integration

Two new tools registered in `ToolRegistry`:

| Tool | Input | Output |
|------|-------|--------|
| `verified_generation` | query, source_document_ids, uploaded_texts, collections, auto_correct, mode_config | document_text + claims + summary + doi_validations |
| `predictive_analysis` | query, case_description, source_document_ids, uploaded_texts, collections, mode_config | recommendation + factors + outcomes + confidence |

The tool wrapper handles:
1. **Upload hydration** — resolves `source_document_ids` to full text via `upload_context_service`
2. **Section splitting** — splits large documents into sections for windowed generation
3. **Jurisprudence pre-fetch** — calls CENDOJ for legal sector (cached per session)
4. **Redis cache** — creates session in cache for PDF/DOCX export

`classify` node removes early-exit for verified/predictive intents.

---

## File Changes

### Create (8 files + 2 `__init__.py`, ~1,200 lines estimated)

| File | Purpose | Est. lines |
|------|---------|-----------|
| `agents/langgraph/subgraphs/__init__.py` | Package init | ~5 |
| `agents/langgraph/subgraphs/verified_gen/__init__.py` | Package init | ~5 |
| `agents/langgraph/subgraphs/verified_gen/state.py` | `VerifiedGenState` | ~80 |
| `agents/langgraph/subgraphs/verified_gen/graph.py` | Graph assembly + compile | ~150 |
| `agents/langgraph/subgraphs/verified_gen/nodes.py` | `generate_claim`, `verify_claim`, `decide` | ~350 |
| `agents/langgraph/subgraphs/predictive/__init__.py` | Package init | ~5 |
| `agents/langgraph/subgraphs/predictive/state.py` | `PredictiveState` | ~70 |
| `agents/langgraph/subgraphs/predictive/graph.py` | Graph assembly + compile | ~150 |
| `agents/langgraph/subgraphs/predictive/nodes.py` | `extract_factor`, `evaluate_outcome`, `decide` | ~300 |
| `agents/langgraph/tools/verified_generation.py` | Tool wrapper with upload hydration + SSE drain | ~100 |
| `agents/langgraph/tools/predictive_analysis.py` | Tool wrapper with upload hydration + SSE drain | ~80 |

### Delete (~3,195 lines)

| File/Directory | Lines |
|---------------|-------|
| `agents/langgraph/stop_and_go/` (15 files) | 3,195 |

### Modify

| File | Change |
|------|--------|
| `agents/langgraph/state.py` | Remove `RAGState` class (~170 lines), keep `create_initial_state()` as deprecated stub |
| `agents/langgraph/nodes/rlm_processor.py` | Change `RAGState` type hints to `Dict[str, Any]` |
| `agents/langgraph/tools/registry.py` | Register 2 new tools |
| `agents/langgraph/nodes/classify.py` | Remove early-exit for verified/predictive intents |
| `agents/langgraph/__init__.py` | Remove `RAGState` export (keep `create_initial_state` as deprecated) |
| `api/emma.py` | SSE mapper: add sub-graph event pass-through, rename `slm_thinking` → `agent_reasoning` |
| `api/__init__.py` | Remove `verified_router`, `predictive_router` exports |
| `main.py` | Remove `verified_router`, `predictive_router` includes |
| `services/predictive_analysis/service.py` | Remove `stop_and_go` imports, simplify to direct sub-graph call |
| `services/verified_generation/service.py` | Remove `stop_and_go` imports, simplify to direct sub-graph call |
| `services/rule_engine.py` | Remove RAGState reference in docstring |

### Preserve (business logic, no changes)

| Module | Used by |
|--------|---------|
| `services/verified_generation/writer_agent.py` | `generate_claim` node |
| `services/verified_generation/verified_context_cache.py` | `verify_claim` node |
| `services/verified_generation/upload_context_service.py` | Tool wrapper (hydration) |
| `services/predictive_analysis/factor_agent.py` | `extract_factor` node |
| `services/predictive_analysis/outcome_extractor.py` | `evaluate_outcome` node |
| `services/predictive_analysis/prediction_synthesizer.py` | `decide` node |
| `services/predictive_analysis/predictive_cache.py` | `extract_factor` node |

### API Endpoints

**Delete:**
- `api/verified_generation.py` — absorbed by `/emma/query`
- `api/predictive_analysis.py` — absorbed by `/emma/query`

**Keep (adapted):**
- PDF/DOCX export endpoints move to a generic `/emma/export/{session_id}/{format}` endpoint that reads from Redis session cache (both modes store results there)

---

## Frontend Impact

| Frontend file | Current | After |
|--------------|---------|-------|
| `services/verified-generation.service.ts` | Calls `/emma/verified/session/{id}` | Calls `/emma/query/stream` with verified context |
| `services/predictive-analysis.service.ts` | Calls `/emma/predictive/analysis/{id}` | Calls `/emma/query/stream` with predictive context |
| `handlers/usePredictiveAnalysis.ts` | Dedicated SSE handler | Merged into unified SSE handler |
| `VerifiedDocumentResult.tsx` | Standalone page | Rendered inline in chat (same component, different mount point) |
| `app/verified/[sessionId]/page.tsx` | Dedicated route | Redirect to chat session or remove |

SSE event names remain identical (`claim_generated`, `claim_verified`, etc.) — only the endpoint changes.

---

## Verification Plan

After each phase:
```bash
cd backend/docker && bash sanity-check.sh all
```

E2E tests:
| Test | Trigger |
|------|---------|
| Fast-path | "Hola" |
| ReAct + smart_search | "Resume los contratos activos" |
| Swarm | "Compara legislacion laboral con mis contratos" |
| Verified generation | "Genera un documento verificado sobre proteccion de datos" |
| Predictive analysis | "Analiza predictivamente el caso de despido improcedente" |
| PDF/DOCX export | Export session result after verified/predictive |

---

## Rollback Plan

If verified generation quality regresses:
1. The `stop_and_go/` directory is in git history — revert the deletion commit
2. Re-add the `verified_router` to `main.py`
3. Route `/emma/verified/*` back to the stop-and-go runner

---

## Estimated Balance

- Deleted: ~3,195 lines (stop_and_go) + ~170 (RAGState) = **~3,365 lines**
- Created: ~1,200 lines (sub-graphs + tools)
- **Net: ~-2,165 lines**
