# LLM Layer Migration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace custom LLMRouter + llm_client.py with 2 ChatOpenAI instances (planner + chat) backed by SGLang, migrating all 22 consumers gradually.

**Architecture:** Lazy factory pattern (`get_planner_model()`/`get_chat_model()`) with deprecated compat wrapper for gradual migration. Thinking toggle kept as raw HTTP escape hatch. Langfuse observability via callback handler.

**Tech Stack:** `langchain-openai>=0.3.0`, `ChatOpenAI`, SGLang OpenAI-compatible API

**Spec:** `docs/superpowers/specs/2026-03-15-llm-layer-migration-chatopenai-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `app/agents/llm_models.py` | Lazy factory: `get_planner_model()`, `get_chat_model()`, `chat_with_thinking()` |
| `app/agents/llm_types.py` | `ModelRole` enum + type definitions preserved from old layer |
| `scripts/spike_chatopenai_sglang.py` | Pre-implementation validation (7 tests) |

### Modified Files
| File | Change |
|------|--------|
| `requirements.txt` | Add `langchain-openai>=0.3.0` |
| `app/core/config.py` | New `LLM_*` settings with `VLLM_*` aliases |
| `app/agents/llm_router.py` | Replace with deprecated compat wrapper |
| `app/agents/langgraph/nodes/classify.py` | `router.chat()` → `get_planner_model().ainvoke()` |
| `app/agents/langgraph/nodes/rewrite.py` | Same pattern |
| `app/agents/langgraph/nodes/memory_recall.py` | Same pattern |
| `app/agents/langgraph/nodes/decompose.py` | Same pattern |
| `app/agents/langgraph/nodes/synthesize_swarm.py` | `get_chat_model().ainvoke()` + thinking escape |
| `app/agents/langgraph/nodes/swarm_worker.py` | `get_planner_model().bind_tools().ainvoke()` |
| `app/agents/langgraph/nodes/react_loop.py` | Tools + thinking + loop — most complex |
| `app/agents/langgraph/nodes/specialists/social.py` | `get_chat_model().ainvoke()` |
| 11 auxiliary services | Various — see spec for full list |

### Deleted Files (cleanup phase)
| File | Reason |
|------|--------|
| `app/agents/llm_client.py` | Replaced by `llm_models.py` + `llm_types.py` |

---

## Chunk 1: Foundation — Spike Test + New Files + Config

### Task 1: Spike test — validate ChatOpenAI + SGLang

**Files:**
- Create: `backend/microservices/emma-agent-service/scripts/spike_chatopenai_sglang.py`

- [ ] **Step 1: Add `langchain-openai` dependency**

Read `requirements.txt`, add `langchain-openai>=0.3.0` if not present.

- [ ] **Step 2: Create spike test script**

Copy the spike test from the spec (Section "Spike Test"). It has 7 tests:
1. Basic invocation
2. Tool calling with `@tool`
3. Async streaming
4. `repetition_penalty` via `model_kwargs`
5. `enable_thinking=False` via `extra_body`
6. `bind_tools` with OpenAI-format dict (`to_openai_param()` format)
7. Langfuse callback handler

- [ ] **Step 3: Run spike test inside Docker**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/docker
docker compose exec emma-agent-service pip install langchain-openai>=0.3.0
docker compose exec emma-agent-service python scripts/spike_chatopenai_sglang.py
```

Expected: All 7 tests pass. If any fail, investigate and document findings before proceeding.

**GATE: Do NOT proceed to Task 2 if spike test fails.**

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/scripts/spike_chatopenai_sglang.py backend/microservices/emma-agent-service/requirements.txt
git commit -m "feat(llm): add spike test for ChatOpenAI + SGLang compatibility"
```

---

### Task 2: Create `llm_models.py` + `llm_types.py` + config changes

**Files:**
- Create: `backend/microservices/emma-agent-service/app/agents/llm_models.py`
- Create: `backend/microservices/emma-agent-service/app/agents/llm_types.py`
- Modify: `backend/microservices/emma-agent-service/app/core/config.py`

- [ ] **Step 1: Create `llm_types.py`**

Read `app/agents/llm_client.py` first. Extract `ModelRole` enum and any other types referenced externally (`LLMResponse` if needed for compat wrapper). Keep it minimal.

- [ ] **Step 2: Create `llm_models.py`**

Copy from spec — lazy factory with `get_planner_model()`, `get_chat_model()`, `chat_with_thinking()`. Include `repetition_penalty`, `enable_thinking=False` in `extra_body`.

- [ ] **Step 3: Add config settings**

In `config.py`, add after the existing vLLM section:
```python
# LLM Layer (ChatOpenAI) — aliases for backwards compatibility with VLLM_* vars
llm_base_url: str = os.getenv("LLM_BASE_URL", os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1"))
llm_model: str = os.getenv("LLM_MODEL", os.getenv("VLLM_MODEL", "Qwen/Qwen3.5-9B"))
llm_api_key: str = os.getenv("LLM_API_KEY", "not-needed")
planner_temperature: float = float(os.getenv("PLANNER_TEMPERATURE", "0.3"))
planner_max_tokens: int = int(os.getenv("PLANNER_MAX_TOKENS", "4096"))
chat_temperature: float = float(os.getenv("CHAT_TEMPERATURE", "0.6"))
chat_max_tokens: int = int(os.getenv("CHAT_MAX_TOKENS", "16384"))
```

- [ ] **Step 4: Verify imports work**

```bash
docker compose exec emma-agent-service python -c "
from app.agents.llm_models import get_planner_model, get_chat_model, chat_with_thinking
from app.agents.llm_types import ModelRole
print('planner:', get_planner_model())
print('chat:', get_chat_model())
print('ModelRole:', ModelRole.PLANNER, ModelRole.CHAT)
print('✅ All imports OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/llm_models.py backend/microservices/emma-agent-service/app/agents/llm_types.py backend/microservices/emma-agent-service/app/core/config.py
git commit -m "feat(llm): add llm_models.py (ChatOpenAI factory) + llm_types.py + config"
```

---

### Task 3: Create deprecated compat wrapper in `llm_router.py`

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/llm_router.py`

- [ ] **Step 1: Read current `llm_router.py` and `llm_client.py`**

Understand the current `LLMRouter.chat()` signature, return type (`LLMResponse`), and how it's called by consumers.

- [ ] **Step 2: Replace `llm_router.py` with thin compat wrapper**

Keep `get_llm_router()` as the entry point (same function name). Replace internals with delegation to `get_planner_model()`/`get_chat_model()`:

```python
"""
DEPRECATED: LLM Router compat wrapper.

This module is a thin compatibility layer that delegates to llm_models.py.
Migrate consumers to use get_planner_model()/get_chat_model() directly.
"""
import warnings
import logging
from app.agents.llm_models import get_planner_model, get_chat_model
from app.agents.llm_types import ModelRole
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

logger = logging.getLogger(__name__)

class _CompatRouter:
    """Deprecated compat wrapper — delegates to ChatOpenAI instances."""

    async def chat(self, messages=None, role=None, tools=None, **kwargs):
        warnings.warn(
            "LLMRouter.chat() is deprecated. Use get_planner_model()/get_chat_model() directly.",
            DeprecationWarning, stacklevel=2,
        )
        model = get_chat_model() if role == ModelRole.CHAT else get_planner_model()

        # Convert dict messages to LangChain types
        lc_messages = []
        for m in (messages or []):
            if isinstance(m, dict):
                r = m.get("role", "user")
                c = m.get("content", "")
                if r == "system": lc_messages.append(SystemMessage(content=c))
                elif r == "assistant": lc_messages.append(AIMessage(content=c))
                else: lc_messages.append(HumanMessage(content=c))
            else:
                lc_messages.append(m)  # Already a LangChain message

        if tools:
            model = model.bind_tools(tools)

        response = await model.ainvoke(lc_messages)

        # Map AIMessage back to LLMResponse-like object
        from app.agents.llm_client import LLMResponse
        return LLMResponse(
            content=response.content,
            tool_calls=response.tool_calls if hasattr(response, 'tool_calls') else [],
            thinking=None,
        )

_compat_router = None

async def get_llm_router():
    global _compat_router
    if _compat_router is None:
        _compat_router = _CompatRouter()
    return _compat_router
```

IMPORTANT: Keep `llm_client.py` intact for now — the `LLMResponse` class is still needed by the compat wrapper and existing consumers. Only delete it in cleanup phase.

- [ ] **Step 3: Verify existing code still works through wrapper**

```bash
docker compose exec emma-agent-service python -c "
import asyncio
from app.agents.llm_router import get_llm_router
from app.agents.llm_client import ModelRole

async def test():
    router = await get_llm_router()
    response = await router.chat(
        messages=[{'role': 'user', 'content': 'Hola'}],
        role=ModelRole.PLANNER,
    )
    print(f'Compat wrapper: {response.content[:80]}')
    print('✅ Backwards compatible')

asyncio.run(test())
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/llm_router.py
git commit -m "feat(llm): replace LLMRouter with deprecated compat wrapper delegating to ChatOpenAI"
```

---

## Chunk 2: Simple Node Migration (classify, rewrite, memory_recall, decompose)

### Task 4: Migrate 4 simple nodes

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/rewrite.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/memory_recall.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/decompose.py`

For EACH node:

- [ ] **Step 1: Read the node file fully**

Find all `get_llm_router()` / `router.chat()` calls. Note the `role=` parameter used.

- [ ] **Step 2: Replace imports and calls**

Pattern:
```python
# REMOVE
from app.agents.llm_router import get_llm_router
from app.agents.llm_client import ModelRole

# ADD
from app.agents.llm_models import get_planner_model
from langchain_core.messages import SystemMessage, HumanMessage

# REPLACE each call:
# OLD: router = await get_llm_router()
#      response = await router.chat(messages=[...], role=ModelRole.PLANNER)
#      text = response.content

# NEW: response = await get_planner_model().ainvoke([SystemMessage(...), HumanMessage(...)])
#      text = response.content
```

Convert dict messages `{"role": "system", "content": ...}` to `SystemMessage(content=...)` etc. Most nodes already import `langchain_core.messages` — check first.

- [ ] **Step 3: Handle JSON parsing nodes (decompose)**

`decompose.py` expects JSON output. The response is still `response.content` (a string) — JSON parsing logic stays the same. Just change how the LLM is called.

- [ ] **Step 4: Test each node via Emma query**

```bash
# classify (fast-path): greeting triggers classify only
curl -sk -X POST "https://localhost/emma/stream" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -d '{"query": "Hola buenos días", "context": {"user_id": "a060f046-9992-4d1a-87c4-fa5c6f8c066c"}}' \
  > /tmp/test_classify.txt 2>&1
grep -c "complete" /tmp/test_classify.txt
```

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py backend/microservices/emma-agent-service/app/agents/langgraph/nodes/rewrite.py backend/microservices/emma-agent-service/app/agents/langgraph/nodes/memory_recall.py backend/microservices/emma-agent-service/app/agents/langgraph/nodes/decompose.py
git commit -m "feat(llm): migrate classify, rewrite, memory_recall, decompose to ChatOpenAI"
```

---

## Chunk 3: Complex Node Migration (synthesize_swarm, swarm_worker, react_loop, social)

### Task 5: Migrate synthesize_swarm + social (CHAT model)

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_swarm.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/specialists/social.py`

- [ ] **Step 1: Migrate synthesize_swarm**

This node uses `ModelRole.CHAT`. Replace with `get_chat_model()`. Handle the `enable_thinking` edge case:

```python
from app.agents.llm_models import get_chat_model, chat_with_thinking

# Normal path
response = await get_chat_model().ainvoke(messages)

# Thinking path (when state["enable_thinking"] == True)
if state.get("enable_thinking"):
    content = await chat_with_thinking(messages)
else:
    response = await get_chat_model().ainvoke(messages)
    content = response.content
```

- [ ] **Step 2: Migrate social node**

Simple — uses CHAT model, no tools, no thinking.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_swarm.py backend/microservices/emma-agent-service/app/agents/langgraph/nodes/specialists/social.py
git commit -m "feat(llm): migrate synthesize_swarm + social to ChatOpenAI (CHAT model)"
```

### Task 6: Migrate swarm_worker (PLANNER + tools)

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/swarm_worker.py`

- [ ] **Step 1: Read the file — understand the mini ReAct loop**

The swarm worker runs a small tool-calling loop (max 2-3 steps). Find where tools are bound and how tool calls are parsed.

- [ ] **Step 2: Replace with bind_tools pattern**

```python
from app.agents.llm_models import get_planner_model

# Get tools for this worker's profile
tools_params = [t.to_openai_param() for t in worker_tools]
model_with_tools = get_planner_model().bind_tools(tools_params)

# In the loop:
response = await model_with_tools.ainvoke(messages)
if response.tool_calls:
    for tc in response.tool_calls:
        name = tc["name"]
        args = tc["args"]  # Already a dict — no json.loads needed
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/swarm_worker.py
git commit -m "feat(llm): migrate swarm_worker to ChatOpenAI with bind_tools"
```

### Task 7: Migrate react_loop (PLANNER + tools + thinking + iterative loop)

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py`

This is the **most complex** migration. Read the entire file carefully.

- [ ] **Step 1: Read and map all LLM call sites**

The react_loop has an iterative tool-calling loop. Map every `router.chat()` call:
- Initial call with tools
- Follow-up calls after tool execution
- The `enable_thinking` conditional

- [ ] **Step 2: Replace with ChatOpenAI pattern**

```python
from app.agents.llm_models import get_planner_model, chat_with_thinking

# Build model with tools
tools_params = [t.to_openai_param() for t in available_tools]
model_with_tools = get_planner_model().bind_tools(tools_params)

# In the loop:
if state.get("enable_thinking") and is_final_response:
    content = await chat_with_thinking(messages)
else:
    response = await model_with_tools.ainvoke(messages)
    # Handle tool_calls from response.tool_calls (already parsed)
```

- [ ] **Step 3: Handle tool_calls format difference**

The current code parses `response.tool_calls` as raw dicts with `function.name` and `function.arguments` (string). ChatOpenAI returns `ToolCall` objects with `.name` (str) and `.args` (dict — already parsed). Adjust the parsing accordingly.

- [ ] **Step 4: Test with a document query**

```bash
curl -sk -X POST "https://localhost/emma/stream" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -d '{"query": "¿Cuántas facturas hay?", "context": {"user_id": "a060f046-9992-4d1a-87c4-fa5c6f8c066c"}}' \
  > /tmp/test_react.txt 2>&1
grep "tool_call\|complete" /tmp/test_react.txt
```

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py
git commit -m "feat(llm): migrate react_loop to ChatOpenAI with bind_tools + thinking escape"
```

---

## Chunk 4: Auxiliary Services Migration

### Task 8: Migrate auxiliary services (11 files)

**Files:** See spec "Auxiliary services (13)" table — 11 need migration, 2 (writer_agent, factor_agent) stay as-is.

For each service:

- [ ] **Step 1: Read and find all `get_llm_router()` / `router.chat()` calls**

- [ ] **Step 2: Replace with `get_planner_model()` or `get_chat_model()`**

Same pattern as nodes. Most services use PLANNER. Only `rlm_processor` and `document_generator` use CHAT.

- [ ] **Step 3: Add Langfuse callback where tracing existed**

For services that had Langfuse `@observe` decorators or manual tracing:

```python
from langfuse.callback import CallbackHandler
handler = CallbackHandler()
response = await get_planner_model().ainvoke(messages, config={"callbacks": [handler]})
```

- [ ] **Step 4: Commit in batches (2-3 files per commit)**

```bash
git commit -m "feat(llm): migrate guardrail_service + fact_extractor to ChatOpenAI"
git commit -m "feat(llm): migrate verified + search_and_evaluate to ChatOpenAI"
git commit -m "feat(llm): migrate diagnostics + intent_router + remaining services to ChatOpenAI"
```

---

## Chunk 5: Cleanup + Final Verification

### Task 9: Delete old files + E2E test

- [ ] **Step 1: Verify no remaining imports of old router**

```bash
docker compose exec emma-agent-service grep -r "from app.agents.llm_router import" app/ --include="*.py" | grep -v "llm_router.py"
docker compose exec emma-agent-service grep -r "from app.agents.llm_client import" app/ --include="*.py" | grep -v "llm_types.py\|llm_router.py"
```

Expected: No results (all consumers migrated).

- [ ] **Step 2: Remove compat wrapper from llm_router.py**

Replace with a simple re-export that points to llm_models.py:

```python
"""DEPRECATED — use app.agents.llm_models instead."""
from app.agents.llm_models import get_planner_model, get_chat_model, chat_with_thinking

async def get_llm_router():
    raise ImportError("LLMRouter removed. Use get_planner_model()/get_chat_model() from llm_models.py")
```

- [ ] **Step 3: Delete llm_client.py**

Only after verifying no imports remain (except from llm_types.py which has the types).

- [ ] **Step 4: Run full E2E diagnostics**

```bash
docker compose exec emma-agent-service python -c "
import asyncio, httpx

async def test():
    async with httpx.AsyncClient() as client:
        # Infra check
        r = await client.get('http://localhost:8009/diagnostics/infra')
        print(f'Infra: {r.json()[\"status\"]}')

        # Integration check
        r = await client.get('http://localhost:8009/diagnostics/integration')
        print(f'Integration: {r.json()[\"status\"]}')

        # E2E check
        r = await client.get('http://localhost:8009/diagnostics/e2e')
        print(f'E2E: {r.json()[\"status\"]}')

asyncio.run(test())
"
```

Expected: All `healthy` or `degraded` (not `critical`).

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(llm): complete migration — delete llm_client.py, remove compat wrapper"
```

---

## Post-Implementation Checklist

- [ ] Spike test passes all 7 tests (ChatOpenAI + SGLang compatible)
- [ ] `get_planner_model()` returns ChatOpenAI with repetition_penalty + enable_thinking=False
- [ ] `get_chat_model()` returns ChatOpenAI with repetition_penalty
- [ ] All 9 graph nodes migrated from `router.chat()` to `model.ainvoke()`
- [ ] All 11 auxiliary services migrated
- [ ] Tool calling works via `bind_tools()` with OpenAI-format dicts
- [ ] Thinking escape hatch works when `enable_thinking=True`
- [ ] Langfuse tracing preserved via callback handler
- [ ] E2E diagnostics pass
- [ ] `llm_client.py` deleted, `llm_router.py` is stub
- [ ] No `DeprecationWarning` in logs (all consumers migrated)
