# LangGraph Sub-Graph Consolidation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Absorb Verified Generation and Predictive Analysis into the ReAct agent as sub-graph tools, eliminating the stop-and-go system and 3,195 lines of code.

**Architecture:** Two new LangGraph sub-graphs (`VerifiedGenGraph`, `PredictiveGraph`) compiled with `checkpointer=False`, wrapped as `EmmaTool` instances. The ReAct agent invokes them via tool calling when `classify` detects verified/predictive intents. SSE streaming via `pending_events` + `astream("values")` drain.

**Tech Stack:** LangGraph StateGraph, TypedDict states, merge_lists/merge_dicts reducers, EmmaTool base class, existing business logic modules (WriterAgent, FactorAgent, etc.)

**Spec:** `docs/superpowers/specs/2026-03-17-langgraph-subgraph-consolidation-design.md`

---

## File Structure

### New Files

```
agents/langgraph/subgraphs/
├── __init__.py                          # Package init
├── verified_gen/
│   ├── __init__.py                      # Exports get_verified_gen_graph
│   ├── state.py                         # VerifiedGenState TypedDict
│   ├── graph.py                         # StateGraph assembly + compile
│   └── nodes.py                         # generate_claim, verify_claim, decide nodes
└── predictive/
    ├── __init__.py                       # Exports get_predictive_graph
    ├── state.py                          # PredictiveState TypedDict
    ├── graph.py                          # StateGraph assembly + compile
    └── nodes.py                          # extract_factor, evaluate_outcome, decide nodes

agents/langgraph/tools/
├── verified_generation.py               # VerifiedGenerationTool (EmmaTool)
└── predictive_analysis.py               # PredictiveAnalysisTool (EmmaTool)
```

### Files to Delete

```
agents/langgraph/stop_and_go/            # Entire directory (15 files, 3195 lines)
api/verified_generation.py               # Standalone API router
api/predictive_analysis.py               # Standalone API router
```

### Files to Modify

```
agents/langgraph/state.py                # Deprecate RAGState
agents/langgraph/nodes/rlm_processor.py  # RAGState → Dict type hints
agents/langgraph/tools/registry.py       # Register 2 new tools
agents/langgraph/__init__.py             # Update exports
api/__init__.py                          # Remove verified_router, predictive_router
api/emma.py                              # SSE: slm_thinking → agent_reasoning + sub-graph events
main.py                                  # Remove verified_router, predictive_router includes
services/verified_generation/service.py  # Remove stop_and_go imports, add sub-graph call
services/predictive_analysis/service.py  # Remove stop_and_go imports, add sub-graph call
```

---

## Chunk 1: Verified Generation Sub-Graph

### Task 1: Create VerifiedGenState

**Files:**
- Create: `app/agents/langgraph/subgraphs/__init__.py`
- Create: `app/agents/langgraph/subgraphs/verified_gen/__init__.py`
- Create: `app/agents/langgraph/subgraphs/verified_gen/state.py`

- [ ] **Step 1: Create package structure**

```bash
mkdir -p app/agents/langgraph/subgraphs/verified_gen
```

- [ ] **Step 2: Write `subgraphs/__init__.py`**

```python
"""LangGraph sub-graphs — compiled graphs invoked as tools from the ReAct agent."""
```

- [ ] **Step 3: Write `verified_gen/__init__.py`**

```python
"""Verified Generation sub-graph — claim-by-claim document generation with two-tier verification."""

from .graph import get_verified_gen_graph

__all__ = ["get_verified_gen_graph"]
```

- [ ] **Step 4: Write `verified_gen/state.py`**

Translate all fields from current `StopAndGoState` (lines 21-83 of `stop_and_go/state.py`) into a dedicated `VerifiedGenState`. Keep `pending_events` with `merge_lists` reducer. Keep `metadata` with `merge_dicts` reducer. All other fields are `LastValue` (default).

Reference: `app/agents/langgraph/stop_and_go/state.py` for the complete field list.

- [ ] **Step 5: Verify syntax**

```bash
python3 -c "from app.agents.langgraph.subgraphs.verified_gen.state import VerifiedGenState; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add app/agents/langgraph/subgraphs/
git commit -m "feat(subgraphs): add VerifiedGenState for verified generation sub-graph"
```

---

### Task 2: Create Verified Generation Nodes

**Files:**
- Create: `app/agents/langgraph/subgraphs/verified_gen/nodes.py`

The node functions extract logic from three existing files:
- `stop_and_go/strategies/verified.py` (696 lines) — core verification logic
- `stop_and_go/nodes/extract_item.py` (71 lines) — item extraction dispatch
- `stop_and_go/nodes/search_and_evaluate.py` (733 lines) — evidence search + evaluation
- `stop_and_go/nodes/decide.py` (110 lines) — completion check
- `stop_and_go/nodes/initialize.py` (411 lines) — source hydration, DOI validation, sectioning

Business logic modules called (NOT rewritten):
- `services/verified_generation/writer_agent.py` — `WriterAgent.generate_claim()`
- `services/verified_generation/verified_context_cache.py` — `VerifiedContextCache`
- `services/verified_generation/upload_context_service.py` — `UploadContextService.get_texts()`

- [ ] **Step 1: Read existing strategy and node files**

Read these files completely to understand the logic that needs to be extracted:
- `app/agents/langgraph/stop_and_go/strategies/verified.py`
- `app/agents/langgraph/stop_and_go/nodes/initialize.py`
- `app/agents/langgraph/stop_and_go/nodes/search_and_evaluate.py`
- `app/agents/langgraph/stop_and_go/nodes/extract_item.py`
- `app/agents/langgraph/stop_and_go/nodes/decide.py`
- `app/agents/langgraph/stop_and_go/nodes/synthesize.py`

- [ ] **Step 2: Write `nodes.py` with 4 node functions**

Structure:
```python
async def initialize_node(state: VerifiedGenState) -> Dict[str, Any]:
    """Hydrate source texts, split into sections, pre-validate DOIs, fetch jurisprudence."""
    # Extract from: stop_and_go/nodes/initialize.py + verified.py.initialize()
    # Calls: UploadContextService.get_texts(), _validate_source_dois(), cendoj_agent

async def generate_claim_node(state: VerifiedGenState) -> Dict[str, Any]:
    """Generate one factual claim from the current section."""
    # Extract from: stop_and_go/nodes/extract_item.py + verified.py.extract_item()
    # Calls: WriterAgent, emits claim_generated event
    # Handles: section windowing, deduplication, duplicate_streak

async def verify_claim_node(state: VerifiedGenState) -> Dict[str, Any]:
    """Two-tier verification: faithfulness (NLI) + external corroboration."""
    # Extract from: stop_and_go/nodes/search_and_evaluate.py + verified.py.evaluate_item()
    # Calls: LLM for faithfulness + external prompts, VerifiedContextCache
    # Emits: claim_verified / claim_corrected events
    # Handles: _combine_verdicts(), auto_correct, DOI cross-reference

async def decide_node(state: VerifiedGenState) -> Dict[str, Any]:
    """Check completion: more claims needed, advance section, or synthesize."""
    # Extract from: stop_and_go/nodes/decide.py + verified.py.check_completion()
    # Returns: is_complete flag
    # Handles: max_claims, duplicate_streak threshold, section advancement
```

Each node reads from `VerifiedGenState`, returns partial updates as `Dict[str, Any]`. Append SSE events to `pending_events` list.

- [ ] **Step 3: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('app/agents/langgraph/subgraphs/verified_gen/nodes.py').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add app/agents/langgraph/subgraphs/verified_gen/nodes.py
git commit -m "feat(subgraphs): add verified generation node functions"
```

---

### Task 3: Create Verified Generation Graph

**Files:**
- Create: `app/agents/langgraph/subgraphs/verified_gen/graph.py`

- [ ] **Step 1: Write `graph.py`**

```python
from langgraph.graph import END, START, StateGraph
from .state import VerifiedGenState
from .nodes import initialize_node, generate_claim_node, verify_claim_node, decide_node

_graph = None

def _route_after_decide(state: VerifiedGenState):
    if state.get("is_complete"):
        return END
    return "generate_claim"

def create_verified_gen_graph() -> StateGraph:
    builder = StateGraph(VerifiedGenState)
    builder.add_node("initialize", initialize_node)
    builder.add_node("generate_claim", generate_claim_node)
    builder.add_node("verify_claim", verify_claim_node)
    builder.add_node("decide", decide_node)

    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "generate_claim")
    builder.add_edge("generate_claim", "verify_claim")
    builder.add_edge("verify_claim", "decide")
    builder.add_conditional_edges("decide", _route_after_decide, ["generate_claim", END])

    return builder.compile(checkpointer=False)

def get_verified_gen_graph():
    global _graph
    if _graph is None:
        _graph = create_verified_gen_graph()
    return _graph
```

- [ ] **Step 2: Verify graph compiles**

```bash
python3 -c "from app.agents.langgraph.subgraphs.verified_gen.graph import create_verified_gen_graph; g = create_verified_gen_graph(); print('Nodes:', list(g.nodes.keys()))"
```

Expected: `Nodes: ['__start__', 'initialize', 'generate_claim', 'verify_claim', 'decide', '__end__']`

- [ ] **Step 3: Commit**

```bash
git add app/agents/langgraph/subgraphs/verified_gen/graph.py
git commit -m "feat(subgraphs): assemble verified generation StateGraph"
```

---

### Task 4: Create VerifiedGenerationTool

**Files:**
- Create: `app/agents/langgraph/tools/verified_generation.py`

- [ ] **Step 1: Write the tool wrapper**

The tool:
1. Receives args from ReAct agent (query, source_document_ids, etc.)
2. Builds initial `VerifiedGenState`
3. Streams the sub-graph with `astream(stream_mode="values")`
4. Drains `pending_events` from each state snapshot → emits SSE via context callback
5. Returns `ToolResult` with the final document

Key pattern for SSE drain:
```python
events_seen = 0
async for snapshot in graph.astream(initial_state, stream_mode="values"):
    all_events = snapshot.get("pending_events", [])
    for event in all_events[events_seen:]:
        # Emit to parent SSE stream
        if emit_sse := context.get("emit_sse"):
            emit_sse(event)
    events_seen = len(all_events)
    final_state = snapshot
```

Reference: `app/agents/langgraph/tools/base.py` for `EmmaTool` interface.
Reference: `app/services/verified_generation/service.py` for upload hydration logic to port.

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('app/agents/langgraph/tools/verified_generation.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/agents/langgraph/tools/verified_generation.py
git commit -m "feat(tools): add verified_generation tool wrapper for sub-graph"
```

---

## Chunk 2: Predictive Analysis Sub-Graph

### Task 5: Create PredictiveState

**Files:**
- Create: `app/agents/langgraph/subgraphs/predictive/__init__.py`
- Create: `app/agents/langgraph/subgraphs/predictive/state.py`

- [ ] **Step 1: Create package**

```bash
mkdir -p app/agents/langgraph/subgraphs/predictive
```

- [ ] **Step 2: Write `__init__.py`**

```python
"""Predictive Analysis sub-graph — factor extraction, outcome evaluation, recommendation."""

from .graph import get_predictive_graph

__all__ = ["get_predictive_graph"]
```

- [ ] **Step 3: Write `state.py`**

Same pattern as Task 1 Step 4 but for predictive fields. Reference `stop_and_go/state.py` + `stop_and_go/strategies/predictive.py` for field usage.

- [ ] **Step 4: Verify syntax**

```bash
python3 -c "from app.agents.langgraph.subgraphs.predictive.state import PredictiveState; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add app/agents/langgraph/subgraphs/predictive/
git commit -m "feat(subgraphs): add PredictiveState for predictive analysis sub-graph"
```

---

### Task 6: Create Predictive Analysis Nodes + Graph

**Files:**
- Create: `app/agents/langgraph/subgraphs/predictive/nodes.py`
- Create: `app/agents/langgraph/subgraphs/predictive/graph.py`

- [ ] **Step 1: Read existing strategy**

Read `app/agents/langgraph/stop_and_go/strategies/predictive.py` (310 lines) completely.

- [ ] **Step 2: Write `nodes.py`**

```python
async def initialize_node(state: PredictiveState) -> Dict[str, Any]:
    """Hydrate source texts, fetch jurisprudence (legal sector)."""

async def extract_factor_node(state: PredictiveState) -> Dict[str, Any]:
    """Extract one legal/business factor from source documents."""
    # Calls: FactorAgent, emits factor_extracted

async def evaluate_outcome_node(state: PredictiveState) -> Dict[str, Any]:
    """Evaluate evidence for/against the current factor, assign weight."""
    # Calls: OutcomeExtractor, emits outcome_evaluated + factor_weighted

async def decide_node(state: PredictiveState) -> Dict[str, Any]:
    """Check completion: more factors needed or synthesize recommendation."""
    # Calls: PredictionSynthesizer on completion, emits prediction_ready
```

- [ ] **Step 3: Write `graph.py`**

Same pattern as Task 3: `START → initialize → extract_factor → evaluate_outcome → decide → [loop or END]`.

- [ ] **Step 4: Verify graph compiles**

```bash
python3 -c "from app.agents.langgraph.subgraphs.predictive.graph import create_predictive_graph; g = create_predictive_graph(); print('Nodes:', list(g.nodes.keys()))"
```

- [ ] **Step 5: Commit**

```bash
git add app/agents/langgraph/subgraphs/predictive/
git commit -m "feat(subgraphs): add predictive analysis sub-graph (nodes + graph)"
```

---

### Task 7: Create PredictiveAnalysisTool

**Files:**
- Create: `app/agents/langgraph/tools/predictive_analysis.py`

- [ ] **Step 1: Write tool wrapper**

Same pattern as Task 4 but for predictive. Reference `app/services/predictive_analysis/service.py` for initial state construction.

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('app/agents/langgraph/tools/predictive_analysis.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/agents/langgraph/tools/predictive_analysis.py
git commit -m "feat(tools): add predictive_analysis tool wrapper for sub-graph"
```

---

## Chunk 3: Integration — Wire Tools into ReAct Agent

### Task 8: Register Tools in ToolRegistry

**Files:**
- Modify: `app/agents/langgraph/tools/registry.py`

- [ ] **Step 1: Read current registry**

```bash
grep -n "class ToolRegistry" app/agents/langgraph/tools/registry.py
```

- [ ] **Step 2: Add imports and registration**

Add `VerifiedGenerationTool` and `PredictiveAnalysisTool` to the registry's `_register_default_tools()` method, alongside the existing 9 tools.

- [ ] **Step 3: Verify tool count**

```bash
python3 -c "
from app.agents.langgraph.tools.registry import ToolRegistry
r = ToolRegistry()
print(f'Tools: {len(r.get_all_tools())}')
for t in r.get_all_tools():
    print(f'  - {t.name}')
"
```

Expected: 11 tools (9 existing + verified_generation + predictive_analysis)

- [ ] **Step 4: Commit**

```bash
git add app/agents/langgraph/tools/registry.py
git commit -m "feat(tools): register verified_generation and predictive_analysis in ToolRegistry"
```

---

### Task 9: SSE Event Mapping — Rename slm_thinking + Add Sub-Graph Events

**Files:**
- Modify: `app/api/emma.py`

- [ ] **Step 1: Rename `slm_thinking` → `agent_reasoning`**

In `app/api/emma.py`, replace all occurrences of `event: slm_thinking` with `event: agent_reasoning`. There are ~20 occurrences (grep found them earlier). Use `replace_all`.

Also rename the JSON field `slmIsThinking` → `isThinking` in the same data payloads.

- [ ] **Step 2: Add sub-graph event pass-through**

In the `_generate_langgraph_sse()` function, add handling for sub-graph events. These events arrive in the `reasoning_steps` state field or via tool result metadata. The tool wrapper emits them via context callback — the SSE mapper re-emits them.

Add cases for: `claim_generated`, `claim_verified`, `claim_corrected`, `section_advanced`, `document_complete`, `factor_extracted`, `factor_weighted`, `outcome_evaluated`, `prediction_ready`, `progress`, `error`.

- [ ] **Step 3: Verify SSE mapper compiles**

```bash
python3 -c "import ast; ast.parse(open('app/api/emma.py').read()); print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add app/api/emma.py
git commit -m "feat(sse): rename slm_thinking → agent_reasoning, add sub-graph event pass-through"
```

---

## Chunk 4: Cleanup — Remove Stop-and-Go + Old Endpoints

### Task 10: Remove API Endpoints and Routers

**Files:**
- Delete: `app/api/verified_generation.py`
- Delete: `app/api/predictive_analysis.py`
- Modify: `app/api/__init__.py`
- Modify: `app/main.py`

- [ ] **Step 1: Remove router imports from `api/__init__.py`**

Remove lines importing `verified_router` and `predictive_router`. Remove from `__all__`.

- [ ] **Step 2: Remove router includes from `main.py`**

Remove `verified_router` and `predictive_router` from the import line (line 46) and the `app.include_router()` calls (lines 222-223).

- [ ] **Step 3: Delete the API router files**

```bash
rm app/api/verified_generation.py app/api/predictive_analysis.py
```

- [ ] **Step 4: Verify main.py compiles and service starts**

```bash
python3 -c "import ast; ast.parse(open('app/main.py').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(api): remove standalone verified/predictive endpoints (absorbed by /emma/query)"
```

---

### Task 11: Update Service Layers

**Files:**
- Modify: `app/services/verified_generation/service.py`
- Modify: `app/services/predictive_analysis/service.py`

- [ ] **Step 1: Read both service files**

Understand which methods call `stop_and_go` imports and which are independent.

- [ ] **Step 2: Simplify `verified_generation/service.py`**

Remove all `from app.agents.langgraph.stop_and_go import ...` blocks. The service becomes a thin wrapper that:
- Builds initial state from request params
- Calls `get_verified_gen_graph().ainvoke(state)`
- Returns the result

Or if the service is only called by the (now deleted) API endpoints, mark it as deprecated with a comment pointing to the tool wrapper.

- [ ] **Step 3: Simplify `predictive_analysis/service.py`**

Same pattern as Step 2.

- [ ] **Step 4: Verify both compile**

```bash
python3 -c "import ast; ast.parse(open('app/services/verified_generation/service.py').read()); print('OK')"
python3 -c "import ast; ast.parse(open('app/services/predictive_analysis/service.py').read()); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add app/services/verified_generation/service.py app/services/predictive_analysis/service.py
git commit -m "refactor(services): decouple verified/predictive services from stop_and_go"
```

---

### Task 12: Delete Stop-and-Go Package

**Files:**
- Delete: `app/agents/langgraph/stop_and_go/` (entire directory, 15 files, 3195 lines)

- [ ] **Step 1: Verify no remaining imports**

```bash
grep -r "from app.agents.langgraph.stop_and_go" app/ --include="*.py" | grep -v "stop_and_go/"
```

Expected: 0 results (services updated in Task 11)

- [ ] **Step 2: Delete the directory**

```bash
rm -rf app/agents/langgraph/stop_and_go/
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: delete stop_and_go package (3195 lines — replaced by sub-graph tools)"
```

---

### Task 13: Deprecate RAGState

**Files:**
- Modify: `app/agents/langgraph/state.py`
- Modify: `app/agents/langgraph/nodes/rlm_processor.py`
- Modify: `app/agents/langgraph/__init__.py`

- [ ] **Step 1: Add deprecation warning to RAGState**

In `state.py`, add a docstring note: `"""DEPRECATED: Only used by rlm_processor.py. Will be removed when RLM migrates to ReActState."""`

Do NOT delete it — `rlm_processor.py` still uses it.

- [ ] **Step 2: Change rlm_processor type hints**

In `rlm_processor.py`, change the 3 node function signatures from `state: RAGState` to `state: Dict[str, Any]`. Remove the `from ..state import RAGState` import.

- [ ] **Step 3: Remove RAGState from langgraph `__init__.py` exports**

Remove `RAGState` and `create_initial_state` from `__all__` and imports (keep them importable directly from `state.py` for backwards compat).

- [ ] **Step 4: Verify**

```bash
python3 -c "import ast; ast.parse(open('app/agents/langgraph/state.py').read()); print('state OK')"
python3 -c "import ast; ast.parse(open('app/agents/langgraph/nodes/rlm_processor.py').read()); print('rlm OK')"
```

- [ ] **Step 5: Commit**

```bash
git add app/agents/langgraph/state.py app/agents/langgraph/nodes/rlm_processor.py app/agents/langgraph/__init__.py
git commit -m "refactor: deprecate RAGState, decouple rlm_processor type hints"
```

---

## Chunk 5: Verification

### Task 14: Full Sanity Check

- [ ] **Step 1: Syntax check all files**

```bash
python3 -c "
import ast, glob
errors = []
for f in glob.glob('app/**/*.py', recursive=True):
    try:
        with open(f) as fh: ast.parse(fh.read())
    except SyntaxError as e: errors.append(f'{f}: {e}')
if errors:
    for e in errors: print(f'ERROR: {e}')
else:
    print('All Python files compile OK')
"
```

- [ ] **Step 2: Verify no broken imports to deleted files**

```bash
grep -r "stop_and_go\|verified_router\|predictive_router\|from app.agents.langgraph.state import.*RAGState" app/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
```

Expected: Only `state.py` itself and the deprecation comment.

- [ ] **Step 3: Run sanity checks**

```bash
cd backend/docker && bash sanity-check.sh all
```

Expected: ALL OK (21/21)

- [ ] **Step 4: Test verified generation via /emma/query**

```bash
curl -X POST http://localhost:8009/emma/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "Genera un documento verificado sobre proteccion de datos basado en mis documentos",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "context": {"user_id": "diagnostics-probe"}
  }' > /tmp/verified_response.json
python3 -c "import json; r=json.load(open('/tmp/verified_response.json')); print(f'success={r[\"success\"]}, len={len(r.get(\"answer\",\"\"))}')"
```

- [ ] **Step 5: Test predictive analysis via /emma/query**

```bash
curl -X POST http://localhost:8009/emma/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "Analiza predictivamente el riesgo de un despido improcedente",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "context": {"user_id": "diagnostics-probe"}
  }' > /tmp/predictive_response.json
python3 -c "import json; r=json.load(open('/tmp/predictive_response.json')); print(f'success={r[\"success\"]}, len={len(r.get(\"answer\",\"\"))}')"
```

- [ ] **Step 6: Final commit with summary**

```bash
git add -A
git status
# Only commit if there are uncommitted changes from verification fixes
```
