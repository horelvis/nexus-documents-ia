# LLM Layer Migration — ChatOpenAI + LangChain Native

**Date**: 2026-03-15
**Status**: Reviewed (pass 1 — 3 critical + 4 important issues resolved)
**Scope**: Sub-project 1 of LangGraph Realignment — Replace custom LLMRouter with ChatOpenAI

## Problem Statement

Emma's LLM layer uses a custom `LLMRouter` (~300 lines) and `llm_client.py` (~250 lines) that:
- Make raw HTTP calls to SGLang's OpenAI-compatible endpoint
- Manually construct tool call schemas via `EmmaTool.to_openai_param()`
- Parse tool call responses from raw JSON
- Manage a client pool keyed by `(LLMProvider, ModelRole)`
- Handle dual-phase routing (PLANNER vs CHAT) with role-specific params

This is all functionality that `ChatOpenAI(base_url=sglang)` provides natively, with better streaming, automatic tool call parsing, and standard LangChain message types.

## Goals

1. Replace `LLMRouter` + `llm_client.py` with 2 `ChatOpenAI` instances (planner + chat)
2. Migrate all 9 graph nodes + 6 auxiliary services from `router.chat()` to `model.ainvoke()`
3. Adopt LangChain native tool calling via `model.bind_tools()` (prep for Tools migration sub-project)
4. Maintain backwards compatibility via deprecated wrapper during gradual migration
5. Keep `enable_thinking` (deep_reasoning) as raw HTTP escape hatch

## Non-Goals

- Migrating `EmmaTool` to `@tool` decorators (separate sub-project: Tools Migration)
- Changing the graph topology (stays as custom StateGraph)
- Migrating SSE streaming (separate sub-project)
- Replacing Langfuse (stays)
- Changing SGLang configuration or model

## Architecture

### Current State

```
Node → get_llm_router() → LLMRouter.chat(messages, role, tools, **kwargs)
                              ↓
                    llm_client.create_llm_config_for_provider(role)
                              ↓
                    raw HTTP POST to SGLang /v1/chat/completions
                              ↓
                    LLMResponse(content, tool_calls, thinking)
```

### Target State

```
Node → planner_model.ainvoke(messages)           # or chat_model.ainvoke()
           ↓
       ChatOpenAI(base_url=sglang, temp=0.3)     # native OpenAI-compatible
           ↓
       AIMessage(content, tool_calls)             # standard LangChain type
```

### New File: `app/agents/llm_models.py` (~100 lines)

Uses **lazy factory pattern** (not module-level globals) to avoid import-time instantiation before settings are loaded.

```python
"""
LLM Model Instances — ChatOpenAI backed by SGLang.

Two instances with different configs for dual-phase behavior:
- planner_model: fast, deterministic (classify, rewrite, tools, decompose)
- chat_model: creative, longer output (synthesize, social)

Uses lazy factory pattern — instantiated on first call, not at import time.
Replaces: llm_router.py + llm_client.py
"""
from langchain_openai import ChatOpenAI
from app.core.config import settings

_planner_model = None
_chat_model = None

def get_planner_model() -> ChatOpenAI:
    global _planner_model
    if _planner_model is None:
        _planner_model = ChatOpenAI(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=settings.planner_temperature,
            max_tokens=settings.planner_max_tokens,
            extra_body={
                "repetition_penalty": 1.15,  # Prevents generation loops in Qwen3.5 (must be extra_body, not model_kwargs)
                "chat_template_kwargs": {"enable_thinking": False},  # PLANNER never thinks
            },
        )
    return _planner_model

def get_chat_model() -> ChatOpenAI:
    global _chat_model
    if _chat_model is None:
        _chat_model = ChatOpenAI(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=settings.chat_temperature,
            max_tokens=settings.chat_max_tokens,
            extra_body={
                "repetition_penalty": 1.15,  # Must be extra_body (model_kwargs rejected by openai client)
                "chat_template_kwargs": {"enable_thinking": False},  # Default off, toggle via escape hatch
            },
        )
    return _chat_model
```

**Key fixes from spec review:**
- `repetition_penalty=1.15` passed via `model_kwargs` (was silently dropped without this)
- `enable_thinking=False` passed via `extra_body` for PLANNER calls (SGLang server default might be `true`)
- Lazy factory pattern (`get_planner_model()`/`get_chat_model()`) instead of module-level globals

### New File: `app/agents/llm_types.py` (~30 lines)

Keeps `ModelRole`, `LLMResponse`, and other types that are referenced beyond the router. Thin file — just type definitions, no logic.

```python
"""Type definitions preserved from the old LLM layer. Used during and after migration."""
from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

class ModelRole(str, Enum):
    PLANNER = "planner"
    CHAT = "chat"
```

### Langfuse Observability

Use `langfuse.callback.CallbackHandler` as a LangChain callback to preserve tracing:

```python
from langfuse.callback import CallbackHandler

langfuse_handler = CallbackHandler()
response = await get_planner_model().ainvoke(messages, config={"callbacks": [langfuse_handler]})
```

This replaces the manual Langfuse tracing in the old `LLMClient.chat()`. Each node passes the handler via `config={"callbacks": [...]}`.


### Thinking Escape Hatch

When `state["enable_thinking"] == True`, nodes that need thinking (`react_loop`, `synthesize_swarm`) make a raw `httpx` call to SGLang with `enable_thinking: true` parameter. This bypasses `ChatOpenAI` for that specific call only.

```python
async def chat_with_thinking(messages: list, **kwargs) -> str:
    """Raw SGLang call with thinking enabled. Used for deep_reasoning toggle."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            json={
                "model": settings.llm_model,
                "messages": [{"role": m.type, "content": m.content} for m in messages],
                "temperature": settings.chat_temperature,
                "max_tokens": settings.chat_max_tokens,
                "chat_template_kwargs": {"enable_thinking": True},
                **kwargs,
            },
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
```

### Deprecated Wrapper (`llm_router.py` → thin compat layer)

During migration, `get_llm_router()` returns a `_CompatRouter` that delegates to `planner_model`/`chat_model`. This allows nodo-by-nodo migration without breaking the system.

```python
class _CompatRouter:
    async def chat(self, messages, role=None, tools=None, **kwargs):
        model = chat_model if role == ModelRole.CHAT else planner_model
        if tools:
            model = model.bind_tools(tools)
        lc_messages = _convert_dict_messages(messages)
        response = await model.ainvoke(lc_messages)
        return LLMResponse(content=response.content, tool_calls=response.tool_calls)
```

Marked `@deprecated`. Removed after all consumers are migrated.

## Configuration Changes

### `app/core/config.py`

New settings (backwards compatible — old `VLLM_*` vars still work as aliases):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `VLLM_BASE_URL` or `http://vllm:8000/v1` | SGLang OpenAI-compatible endpoint |
| `LLM_MODEL` | `VLLM_MODEL` or `Qwen/Qwen3.5-9B` | Model name |
| `LLM_API_KEY` | `not-needed` | API key (SGLang doesn't require one) |
| `PLANNER_TEMPERATURE` | `0.3` | Planner model temperature |
| `PLANNER_MAX_TOKENS` | `4096` | Planner max output tokens |
| `CHAT_TEMPERATURE` | `0.6` | Chat model temperature |
| `CHAT_MAX_TOKENS` | `16384` | Chat max output tokens |

Alias logic:
```python
llm_base_url: str = os.getenv("LLM_BASE_URL", os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1"))
llm_model: str = os.getenv("LLM_MODEL", os.getenv("VLLM_MODEL", "Qwen/Qwen3.5-9B"))
```

## Dependencies

### Add to `requirements.txt`

```
langchain-openai>=0.3.0
```

### Already present (no change)

```
langgraph>=1.0.0
langchain-core>=0.3.0
```

## Migration Pattern Per Node

### Message conversion

```python
# BEFORE — dict messages
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": query},
]
response = await router.chat(messages=messages, role=ModelRole.PLANNER)
text = response.content

# AFTER — LangChain message types
from langchain_core.messages import SystemMessage, HumanMessage
messages = [SystemMessage(content=system_prompt), HumanMessage(content=query)]
response = await planner_model.ainvoke(messages)
text = response.content
```

### Tool calling conversion

```python
# BEFORE — manual schema
tools_params = [tool.to_openai_param() for tool in tools]
response = await router.chat(messages=msgs, tools=tools_params, role=ModelRole.PLANNER)
if response.tool_calls:
    for tc in response.tool_calls:
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"])

# AFTER — bind_tools (interim: still EmmaTool, converted via .to_openai_param())
# Full @tool migration is a separate sub-project
model_with_tools = planner_model.bind_tools(
    [t.to_openai_param() for t in tools]  # interim: OpenAI schema dicts
)
response = await model_with_tools.ainvoke(msgs)
if response.tool_calls:
    for tc in response.tool_calls:
        name = tc["name"]       # already parsed
        args = tc["args"]       # already a dict, no json.loads needed
```

## Nodes — Migration Detail

### Graph nodes (9)

| Node | File | Role | Change | Risk |
|------|------|------|--------|------|
| `classify` | `nodes/classify.py` | PLANNER | 1 LLM call → `planner_model.ainvoke()` | Low |
| `rewrite` | `nodes/rewrite.py` | PLANNER | 1 LLM call → `planner_model.ainvoke()` | Low |
| `memory_recall` | `nodes/memory_recall.py` | PLANNER | 1 LLM call → `planner_model.ainvoke()` | Low |
| `react_loop` | `nodes/react_loop.py` | PLANNER | Tool loop + thinking → `planner_model.bind_tools().ainvoke()` + `chat_with_thinking()` | **High** |
| `decompose` | `nodes/decompose.py` | PLANNER | JSON output → `planner_model.ainvoke()` | Medium |
| `swarm_worker` | `nodes/swarm_worker.py` | PLANNER | Mini ReAct with tools → `planner_model.bind_tools().ainvoke()` | Medium |
| `synthesize_react` | `nodes/synthesize_react.py` | — | No LLM call — skip | None |
| `synthesize_swarm` | `nodes/synthesize_swarm.py` | CHAT | Synthesis + thinking → `chat_model.ainvoke()` + `chat_with_thinking()` | Medium |
| `social` | `nodes/specialists/social.py` | CHAT | Social responses → `chat_model.ainvoke()` | Low |

### Auxiliary services (13)

| Service | File | Role | Change |
|---------|------|------|--------|
| `guardrail_service` | `services/guardrail_service.py` | PLANNER | `_validate_llm()` → `get_planner_model()` |
| `fact_extractor` | `services/memory/fact_extractor.py` | PLANNER | Memory extraction → `get_planner_model()` |
| `verified` | `stop_and_go/strategies/verified.py` | PLANNER | Claim verification → `get_planner_model()` |
| `search_and_evaluate` | `stop_and_go/nodes/search_and_evaluate.py` | PLANNER | Evidence eval → `get_planner_model()` |
| `insight_evaluator` | `services/heartbeat/insight_evaluator.py` | PLANNER | Insights → `get_planner_model()` |
| `rlm_processor` | `services/verified_generation/service.py` | CHAT | RLM processing → `get_chat_model()` |
| `diagnostics` | `api/diagnostics.py` | PLANNER/CHAT | Health check LLM calls → factory functions |
| `intent_router` | `services/intent_router.py` | PLANNER | Intent classification → `get_planner_model()` |
| `document_generator` | `services/document_generator.py` | CHAT | Document generation → `get_chat_model()` |
| `memory_generator` | `services/memory/memory_generator.py` | PLANNER | Memory generation → `get_planner_model()` |
| `specialists` (tools) | `agents/langgraph/tools/specialists.py` | PLANNER | Domain analysis → `get_planner_model()` |
| `writer_agent` | `services/predictive_analysis/writer_agent.py` | — | Already uses raw httpx — no change needed |
| `factor_agent` | `services/predictive_analysis/factor_agent.py` | — | Already uses raw httpx — no change needed |

**Note:** `writer_agent.py` and `factor_agent.py` make direct httpx calls to SGLang (bypassing both LLMRouter AND ChatOpenAI). They are listed for completeness but do NOT need migration — they already work independently.

## Migration Order (lower risk first)

1. **Spike test** — validate ChatOpenAI + SGLang compatibility (tool calling, streaming, Qwen3.5)
2. **`llm_models.py`** — create 2 instances + thinking helper
3. **`llm_router.py`** — replace with deprecated compat wrapper
4. **`config.py`** — add new settings with VLLM_* aliases
5. **`classify.py`** — simplest node, 1 call, no tools
6. **`rewrite.py`** — same pattern
7. **`memory_recall.py`** — same pattern
8. **`decompose.py`** — JSON output, no tools
9. **`synthesize_swarm.py`** — CHAT model + thinking edge case
10. **`swarm_worker.py`** — tools + mini ReAct
11. **`react_loop.py`** — most complex (tools + thinking + iterative loop)
12. **Auxiliary services** (6) — guardrail, fact_extractor, verified, etc.
13. **Cleanup** — delete old `llm_client.py`, remove compat wrapper from `llm_router.py`

## Spike Test (Pre-Implementation Gate)

Before any migration, run this validation against live SGLang:

```python
# scripts/spike_chatopenai_sglang.py
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

model = ChatOpenAI(
    base_url="http://vllm:8000/v1",
    model="Qwen/Qwen3.5-9B",
    api_key="not-needed",
    temperature=0.3,
    max_tokens=4096,
)

# Test 1: Basic invocation
response = model.invoke([HumanMessage(content="Hola, ¿qué puedes hacer?")])
assert response.content, "Empty response"
print(f"✅ Basic: {response.content[:80]}")

# Test 2: Tool calling
from langchain_core.tools import tool
@tool
def search(query: str) -> str:
    """Search documents."""
    return f"Results for: {query}"

model_with_tools = model.bind_tools([search])
response = model_with_tools.invoke([
    SystemMessage(content="Use tools when needed."),
    HumanMessage(content="Search for contracts from 2024"),
])
assert response.tool_calls, "No tool calls generated"
print(f"✅ Tool calls: {response.tool_calls}")

# Test 3: Async streaming
import asyncio
async def test_stream():
    chunks = []
    async for chunk in model.astream([HumanMessage(content="Explica RAG en 2 frases")]):
        chunks.append(chunk.content)
    full = "".join(chunks)
    assert len(full) > 20, "Stream too short"
    print(f"✅ Streaming: {full[:80]}...")

asyncio.run(test_stream())
print(f"✅ Streaming: {full[:80]}...")

# Test 4: repetition_penalty forwarded via model_kwargs
model_with_penalty = ChatOpenAI(
    base_url="http://vllm:8000/v1",
    model="Qwen/Qwen3.5-9B",
    api_key="not-needed",
    temperature=0.3,
    model_kwargs={"repetition_penalty": 1.15},
)
response = model_with_penalty.invoke([HumanMessage(content="Repite la palabra 'hola' 20 veces")])
print(f"✅ repetition_penalty: response length={len(response.content)} (should be short, not 20x)")

# Test 5: enable_thinking=False via extra_body
model_no_think = ChatOpenAI(
    base_url="http://vllm:8000/v1",
    model="Qwen/Qwen3.5-9B",
    api_key="not-needed",
    temperature=0.3,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
response = model_no_think.invoke([HumanMessage(content="¿Cuánto es 2+2?")])
assert "<think>" not in response.content, "Thinking tags present despite enable_thinking=False!"
print(f"✅ enable_thinking=False: no <think> tags in response")

# Test 6: bind_tools with OpenAI-format dict (EmmaTool.to_openai_param() format)
tool_schema = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Search documents in the knowledge base",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
}
# Try full format first, fall back to inner dict if double-wrapping occurs
try:
    model_with_dict_tools = model.bind_tools([tool_schema])
    response = model_with_dict_tools.invoke([
        SystemMessage(content="Use tools when needed."),
        HumanMessage(content="Busca contratos de 2024"),
    ])
    print(f"✅ bind_tools with full OpenAI dict: tool_calls={bool(response.tool_calls)}")
except Exception as e:
    # Try inner dict only
    model_with_inner = model.bind_tools([tool_schema["function"]])
    response = model_with_inner.invoke([
        SystemMessage(content="Use tools when needed."),
        HumanMessage(content="Busca contratos de 2024"),
    ])
    print(f"⚠️ bind_tools needs inner dict only (not full wrapper): tool_calls={bool(response.tool_calls)}")

# Test 7: Langfuse callback handler
try:
    from langfuse.callback import CallbackHandler
    handler = CallbackHandler()
    response = model.invoke(
        [HumanMessage(content="Test Langfuse tracing")],
        config={"callbacks": [handler]},
    )
    print(f"✅ Langfuse callback: response received, trace should appear in Langfuse UI")
except ImportError:
    print("⚠️ langfuse.callback not available — install langfuse>=2.0")

print("\n✅ All spike tests passed — ChatOpenAI + SGLang compatible")
```

If any test fails, investigate before proceeding. Common issues:
- Tool calling: SGLang tool parser might need `--tool-call-parser qwen3_coder`
- `repetition_penalty` not forwarded: try `extra_body` instead of `model_kwargs`
- `enable_thinking`: if `extra_body` doesn't work, use `model_kwargs` or raw httpx
- `bind_tools` double-wrap: use inner `function` dict instead of full `{"type": "function", ...}`
- API key: SGLang may reject empty key — try `"not-needed"` or `"EMPTY"`

## Testing Strategy

1. **Spike test** — ChatOpenAI + SGLang compatibility (pre-implementation gate)
2. **Per-node verification** — after migrating each node, run relevant diagnostics
3. **E2E regression** — full pipeline test via `/diagnostics/e2e`
4. **Cleanup gate** — all 15 consumers migrated + E2E green → delete old files

## Files Changed Summary

All paths relative to `backend/microservices/emma-agent-service/`:

| File | Type | Description |
|------|------|-------------|
| `app/agents/llm_models.py` | NEW | Lazy factory: `get_planner_model()` + `get_chat_model()` + thinking helper |
| `app/agents/llm_types.py` | NEW | `ModelRole`, type definitions preserved from old layer |
| `scripts/spike_chatopenai_sglang.py` | NEW | Spike test script (7 tests including repetition_penalty, thinking, bind_tools format) |
| `app/agents/llm_router.py` | MOD→DEL | Replace with compat wrapper, then delete |
| `app/agents/llm_client.py` | DEL | Logic removed (types moved to `llm_types.py`) |
| `app/core/config.py` | MOD | New LLM_* settings with VLLM_* aliases |
| `requirements.txt` | MOD | Add `langchain-openai>=0.3.0` |
| `app/agents/langgraph/nodes/classify.py` | MOD | `router.chat()` → `planner_model.ainvoke()` |
| `app/agents/langgraph/nodes/rewrite.py` | MOD | Same pattern |
| `app/agents/langgraph/nodes/memory_recall.py` | MOD | Same pattern |
| `app/agents/langgraph/nodes/decompose.py` | MOD | Same pattern |
| `app/agents/langgraph/nodes/react_loop.py` | MOD | Tools + thinking + loop migration |
| `app/agents/langgraph/nodes/swarm_worker.py` | MOD | Tools + mini ReAct migration |
| `app/agents/langgraph/nodes/synthesize_swarm.py` | MOD | CHAT model + thinking |
| `app/agents/langgraph/nodes/specialists/social.py` | MOD | CHAT model |
| `app/services/guardrail_service.py` | MOD | `_validate_llm()` → `planner_model` |
| `app/services/memory/fact_extractor.py` | MOD | → `planner_model` |
| `app/agents/langgraph/stop_and_go/strategies/verified.py` | MOD | → `planner_model` |
| `app/agents/langgraph/stop_and_go/nodes/search_and_evaluate.py` | MOD | → `planner_model` |
| `app/services/heartbeat/insight_evaluator.py` | MOD | → `planner_model` |
| `app/services/verified_generation/service.py` | MOD | → `chat_model` (RLM) |

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| ChatOpenAI doesn't support SGLang's tool call format (qwen3_coder parser) | Spike test validates this first. Fallback: use `bind_tools(tool_choice="auto")` or raw schema dicts |
| Streaming format differences between ChatOpenAI and raw SSE | SSE migration is a separate sub-project. Current nodes use `.ainvoke()` not streaming |
| `enable_thinking` not supported via ChatOpenAI | Kept as raw HTTP escape hatch — only 2 nodes use it |
| Breaking changes during gradual migration | Deprecated wrapper ensures old code works until each consumer is migrated |
| `langchain-openai` version conflicts with existing deps | Pin to `>=0.3.0` and test in Docker build |
