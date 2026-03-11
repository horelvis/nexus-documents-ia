# Emma AI - Technical Architecture

Emma is the intelligent AI assistant for NouxCubeIA, built on **LangGraph** (ReAct agent with Swarm parallel execution) with **SGLang** (Qwen3.5-9B) as the primary inference engine.

> **Current Status**: LangGraph ReAct Agent is the default execution path (`LANGGRAPH_RAG_ENABLED=true`). PostgresSaver checkpointer provides conversation continuity. AsyncPostgresStore provides cross-thread user memory.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EMMA AI ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────┐    │
│  │   Frontend  │     │  API Gateway│     │   Emma Agent Service        │    │
│  │  Next.js 15 │────▶│   FastAPI   │────▶│  ┌─────────────────────┐   │    │
│  │  EmmaChat   │     │   :8000     │     │  │  LangGraph ReAct    │   │    │
│  └─────────────┘     └─────────────┘     │  │  Agent (8 nodes)    │   │    │
│                             │            │  └──────────┬──────────┘   │    │
│                             │            │             │              │    │
│                             ▼            │  ┌──────────▼──────────┐   │    │
│  ┌─────────────────────────────────────┐ │  │  9 ReAct Tools      │   │    │
│  │         Data Layer                   │ │  │  - smart_search     │   │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────┐ │ │  │  - structural_query │   │    │
│  │  │PostgreSQL│ │ Weaviate │ │Redis │ │ │  │  - analyze_domain   │   │    │
│  │  │   +AGE   │ │ (Vector) │ │      │ │ │  │  - web_search       │   │    │
│  │  └──────────┘ └──────────┘ └──────┘ │ │  │  - ...              │   │    │
│  └─────────────────────────────────────┘ │  └─────────────────────┘   │    │
│                                          │                            │    │
│  ┌─────────────────────────────────────┐ │  ┌─────────────────────┐   │    │
│  │     Persistence Layer               │ │  │  SGLang (GPU)       │   │    │
│  │  ┌──────────────┐ ┌──────────────┐  │ │  │  Qwen3.5-9B BF16   │   │    │
│  │  │PostgresSaver │ │AsyncPostgres │  │ │  │  PLANNER + CHAT     │   │    │
│  │  │(checkpointer)│ │Store (memory)│  │ │  │  phases             │   │    │
│  │  └──────────────┘ └──────────────┘  │ │  └─────────────────────┘   │    │
│  │      shared psycopg3 pool           │ │                            │    │
│  └─────────────────────────────────────┘ └────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ReAct Agent Graph (8 Nodes)

Two execution paths through the same StateGraph:

```
START → classify → [fast_path → END]
                 → rewrite → memory_recall → react_loop ⟲ → synthesize → END       (simple)
                 → rewrite → memory_recall → decompose → Send[swarm_worker × N] →   (complex)
                   synthesize_swarm → END
```

### Nodes

| Node | Purpose | LLM Role | Retry |
|------|---------|----------|-------|
| `classify` | Intent detection, fast-path, sector config | PLANNER | Yes (2 attempts) |
| `rewrite` | Contextualize follow-up queries using conversation history | PLANNER | Yes |
| `memory_recall` | Scan document memories, generate clues | PLANNER | Yes |
| `react_loop` | Tool-calling ReAct iterations (max 10 steps) | PLANNER | Internal |
| `synthesize` | Format final answer from tool results | — (no LLM) | No |
| `decompose` | Split complex query into sub-tasks (Swarm) | PLANNER | Yes |
| `swarm_worker` | Mini-ReAct loop per sub-task (parallel via `Send()`) | PLANNER | Internal |
| `synthesize_swarm` | Merge parallel worker results into coherent answer | CHAT | Yes |

### Routing Logic

| Edge | Condition | Target |
|------|-----------|--------|
| `classify → END` | Fast-path (greeting, identity) | Direct response |
| `classify → rewrite` | All non-fast-path queries | Always |
| `rewrite → memory_recall` | Always | Pass-through when no history |
| `memory_recall → react_loop` | `use_swarm=False` | Standard single-agent path |
| `memory_recall → decompose` | `use_swarm=True` + `SWARM_ENABLED` | Complex multi-faceted queries |
| `decompose → Send[swarm_worker × N]` | Sub-tasks generated | Dynamic fan-out |
| `decompose → react_loop` | Decomposition failed | Fallback |
| `react_loop → react_loop` | `is_complete=False` | Continue iterating |
| `react_loop → synthesize` | `is_complete=True` | Terminate |

### Key Files

| File | Purpose |
|------|---------|
| `app/agents/langgraph/graph.py` | StateGraph definition + routing functions |
| `app/agents/langgraph/state.py` | `ReActState` TypedDict + `create_initial_react_state()` |
| `app/agents/langgraph/nodes/` | All 8 node implementations |
| `app/agents/langgraph/tools/` | 9 tools via `ToolRegistry` singleton |
| `app/agents/langgraph/sectors/` | Per-sector configuration (legal, medical, documental) |

---

## Persistence Layer (LangGraph Level 3)

### Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    PERSISTENCE (shared psycopg3 pool)                       │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────┐    ┌───────────────────────────────────┐    │
│   │   AsyncPostgresSaver    │    │       AsyncPostgresStore          │    │
│   │     (Checkpointer)      │    │       (Cross-Thread Memory)       │    │
│   ├─────────────────────────┤    ├───────────────────────────────────┤    │
│   │ Scope: per thread_id    │    │ Namespace: ("user_facts",         │    │
│   │                         │    │   tenant_id, user_id)             │    │
│   │ Stores:                 │    │                                    │    │
│   │ - Message history       │    │ Key: "category/fact_key"           │    │
│   │ - Graph state snapshots │    │ Value: {fact_value, confidence,    │    │
│   │ - Checkpoint sequence   │    │         source, source_query}      │    │
│   │                         │    │                                    │    │
│   │ Features:               │    │ Features:                          │    │
│   │ - Conversation continuity│   │ - Cross-session user facts         │    │
│   │ - Time travel (replay)  │    │ - Confidence maximization          │    │
│   │ - State snapshots       │    │ - GDPR right-to-erasure            │    │
│   └─────────────────────────┘    └───────────────────────────────────┘    │
│                                                                             │
│   Config: LANGGRAPH_CHECKPOINTER_ENABLED=true (default)                    │
│   Key file: app/core/checkpointer.py                                       │
│                                                                             │
│   Legacy fallback: asyncpg + Redis (when Store unavailable)                │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### Conversation Continuity

When a user sends a follow-up message to the same `thread_id`:

1. **Checkpointer restores** full message history from the last checkpoint
2. **`create_initial_react_state()`** only appends the new `HumanMessage` (not full history)
3. **`rewrite_node`** reads restored messages to contextualize follow-ups ("cuales son?" → "¿Cuáles son los contratos caducados?")
4. **`_checkpoint_offsets`** pattern prevents `merge_lists` fields from accumulating across turns

### Session Metadata

`emma_persistence_service` runs in **slim mode** when checkpointer is active:
- Stores only metadata (title, timestamps, message_count, previews)
- Full message history lives in the checkpointer (not `emma_sessions.messages` JSONB)
- Redis `emma:conv:` keys are skipped (no legacy conversation cache)

---

## LLM Router — Single-Model Dual-Phase

One Qwen3.5-9B model on SGLang, two behavioral phases:

```
                    ┌─────────────────────────────────────┐
                    │            LLMRouter                │
                    │                                     │
User Query ──────►  │  role=PLANNER → temp=0.3, 4K tok   │
                    │  role=CHAT    → temp=0.6, 16K tok   │
                    │                                     │
                    │  Single SGLang instance (9B BF16)    │
                    └─────────────────────────────────────┘
```

| Role | Temperature | Max Tokens | Used By | Purpose |
|------|-------------|------------|---------|---------|
| `PLANNER` | 0.3 | 4,096 | classify, rewrite, memory_recall, react_loop, decompose, swarm_worker | Tool calling, JSON extraction, routing |
| `CHAT` | 0.6 | 16,384 | synthesize_swarm, rlm_processor, writer_agent, specialists | User-facing text generation |

**Usage**:
```python
from app.agents.llm_router import get_llm_router
from app.agents.llm_client import ModelRole

router = await get_llm_router()
response = await router.chat(messages=messages, role=ModelRole.PLANNER)  # Fast tool calling
response = await router.chat(messages=messages, role=ModelRole.CHAT)     # Quality generation
```

**Optional dual-model**: `VLLM_DUAL_MODEL=true` runs a separate 4B planner instance.

---

## ReAct Tools (9)

| Tool | Purpose |
|------|---------|
| `smart_search` | Unified document + legislation search (auto-detects scope, 3 data stores) |
| `get_document_content` | Read full document by ID |
| `structural_query` | Count, list, filter via Apache AGE graph |
| `analyze_domain` | Specialist domain analysis (legal, fiscal, labor, etc.) |
| `web_search` | Internet search (Tavily primary, DuckDuckGo fallback) |
| `search_jurisprudence` | CENDOJ jurisprudence search |
| `list_sources` | Discover available data sources |
| `query_connector` | Query external connectors (SharePoint, etc.) |
| `terminate` | Signal completion with response |

Tools are registered via `ToolRegistry` singleton in `app/agents/langgraph/tools/registry.py`.

---

## System Flow

```
FRONTEND (Next.js)
┌─────────────────────────────────────────────────────────────────────────────┐
│  EmmaChat.tsx ───── emma.service.ts                                         │
│       │                    │                                                 │
│       │  queryEmmaStream() → POST /api/v1/emma/query/stream                │
└───────│─────────────────────── SSE Stream ─────────────────────────────────┘
        │
        v
MAIN API (FastAPI - port 8000)
┌─────────────────────────────────────────────────────────────────────────────┐
│  app/api/v1/emma.py → proxies to Emma Agent Service (port 8009)            │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        v
EMMA AGENT SERVICE (FastAPI - port 8009)
┌─────────────────────────────────────────────────────────────────────────────┐
│  app/api/emma.py                                                            │
│       │                                                                      │
│       v                                                                      │
│  stream_react_query() → graph.astream(stream_mode=["updates","custom"])    │
│       │                                                                      │
│       ├──→ Load session metadata (emma_persistence_service)                 │
│       ├──→ Hydrate upload context (if document attached)                    │
│       ├──→ Create initial state (loads user_memory from Store)              │
│       │                                                                      │
│       └──→ LangGraph ReAct Graph (8 nodes)                                 │
│            │                                                                 │
│            ├──→ classify (intent + fast-path + sector config)               │
│            ├──→ rewrite (contextualize follow-ups via history)              │
│            ├──→ memory_recall (document memories from knowledge-tree)       │
│            ├──→ react_loop (tool calls: smart_search, structural_query...)  │
│            │    └──→ SmartSearch → Weaviate + PublicKnowledge + AGE graph   │
│            └──→ synthesize / synthesize_swarm                               │
│                                                                              │
│  Checkpointer: PostgresSaver (conversation continuity)                      │
│  Store: AsyncPostgresStore (user facts across sessions)                     │
└─────────────────────────────────────────────────────────────────────────────┘

SSE EVENTS
  └→ event: slm_thinking  (reasoning steps, tool calls)
  └→ event: token          (streaming answer tokens)
  └→ event: sources        (retrieved documents)
  └→ event: complete       (final answer + metadata)
  └→ event: swarm_started / worker_started / worker_complete (Swarm mode)
```

---

## Complete Execution Flow

### Example: "What risks does this contract have?"

```
1. FRONTEND
   └→ User types query in EmmaChat
   └→ emma.service.queryEmmaStream()
      POST /api/v1/emma/query/stream
      Body: { query, session_id, tenant_id, context: { user_id } }

2. MAIN API (port 8000)
   └→ Validates auth token
   └→ Proxies to Emma Agent Service (port 8009)

3. EMMA AGENT SERVICE
   └→ stream_react_query()
       │
       ├→ Load session metadata (slim mode: title, timestamps only)
       ├→ Hydrate upload context (if documents attached)
       ├→ Create initial state
       │   ├→ Load user_memory from AsyncPostgresStore
       │   └→ Append HumanMessage (history from checkpointer)
       │
       └→ graph.astream(config={"configurable": {"thread_id": session_id}})
           │
           ├→ classify_node
           │   Intent: document_query (not fast-path)
           │   Records _checkpoint_offsets for merge_lists fields
           │
           ├→ rewrite_node
           │   No conversation history → pass-through
           │
           ├→ memory_recall_node
           │   Scans document memories → injects clues if found
           │
           ├→ react_loop (iteration 1)
           │   LLM decides: call smart_search(query="contract risks")
           │   → SmartSearch: entity extraction → scope detection →
           │     parallel search (Weaviate + PublicKnowledge) →
           │     merge + dedup + re-rank
           │   Returns: 8 relevant chunks with sources
           │
           ├→ react_loop (iteration 2)
           │   LLM has enough context → calls terminate(answer="...")
           │
           └→ synthesize_react_node
               Formats final_answer, deduplicates sources
               No extra LLM call (direct pass-through)

4. SSE STREAMING
   └→ event: slm_thinking { step: "Searching documents..." }
   └→ event: slm_thinking { step: "Found 8 relevant chunks" }
   └→ event: token { text: "He identificado..." }
   └→ event: sources [{ title, document_id, score }]
   └→ event: complete { answer, sources, metadata }

5. PERSISTENCE
   └→ Checkpointer: graph state saved (messages, tool results)
   └→ emma_persistence_service: metadata only (title, message_count)
   └→ Fire-and-forget: extract_and_save_facts() (user memory)
```

---

## Verified Generation (Generación Verificada)

Emma generates verified documents where each claim is validated against source evidence.

### Flow

```
User → "Verificar: [topic]" + attachments →
  EmmaChat.handleVerifiedGeneration() →
    POST /api/v1/emma/verified/generate/stream (SSE) →
      Stop-and-Go LangGraph: initialize → extract_item → search_and_evaluate → decide → synthesize
```

### Two-Tier Verification

| Tier | What | Source | Confidence Cap |
|------|------|--------|---------------|
| **Tier 1: Faithfulness** | NLI check against source document | Source evidence | 0.80 (fidelity_only) |
| **Tier 2: External** | Corroboration from external sources | External evidence | Full confidence |
| **Combined** | Both tiers agree | Both | `corroborated` |

### SSE Events

| Event | Description |
|-------|-------------|
| `claim_extracted` | New claim identified from source |
| `verification_started` | Searching evidence for claim |
| `claim_verified` | Claim confirmed with evidence |
| `claim_corrected` | Claim modified based on evidence |
| `claim_rejected` | Claim rejected (insufficient evidence) |
| `synthesis_started` | Generating final document |
| `document_complete` | Final verified document ready |

### Export Formats

- **PDF**: `GET /api/v1/emma/verified/session/{id}/pdf`
- **DOCX**: `GET /api/v1/emma/verified/session/{id}/docx`

### Key Files

| File | Purpose |
|------|---------|
| `emma-agent-service/app/agents/langgraph/stop_and_go/` | Stop-and-Go graph (14 files) |
| `emma-agent-service/app/services/verified_generation/service.py` | Service wrapper |
| `emma-agent-service/app/services/verified_generation/writer_agent.py` | Claim writing |
| `emma-agent-service/app/api/verified_generation.py` | REST endpoints |
| `frontend/.../components/emma-chat/VerifiedDocumentResult.tsx` | UI component |

---

## Predictive Analysis (Análisis Predictivo)

Emma analyzes legal factors and predicts outcome probabilities.

### Flow

```
User → "Predecir: [case]" + attachments →
  EmmaChat.handlePredictiveAnalysis() →
    POST /api/v1/emma/predictive/analyze/stream (SSE) →
      Stop-and-Go LangGraph: initialize → extract_item → search_and_evaluate → decide → synthesize
```

### Key Files

| File | Purpose |
|------|---------|
| `emma-agent-service/app/services/predictive_analysis/service.py` | Main service |
| `emma-agent-service/app/services/predictive_analysis/factor_agent.py` | Factor extraction |
| `emma-agent-service/app/services/predictive_analysis/prediction_synthesizer.py` | Synthesis |
| `emma-agent-service/app/api/predictive_analysis.py` | REST endpoints |

---

## SGLang Configuration

### Environment Variables

```bash
# SGLang (Primary LLM — service name kept as "vllm" for URL compatibility)
VLLM_ENABLED=true
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_MODEL=Qwen/Qwen3.5-9B
VLLM_MAX_MODEL_LEN=16384
VLLM_GPU_UTIL=0.75

# Embeddings (BGE-M3)
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024

# LangGraph Persistence
LANGGRAPH_CHECKPOINTER_ENABLED=true
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/db

# Redis (session metadata, caching)
REDIS_HOST=redis
REDIS_PORT=6379
```

### GPU Allocation (RTX 4090 24GB)

```
┌─────────────────────────────────────────────────────────────┐
│  LLM: Qwen/Qwen3.5-9B (BF16)                               │
│    • VRAM: ~11.4GB (75% allocation via mem_fraction_static)  │
│    • Context: 16K tokens (PLANNER: 8K)                       │
│    • Runtime: SGLang v0.5.9                                  │
├─────────────────────────────────────────────────────────────┤
│  Embedding: BAAI/bge-m3                                     │
│    • VRAM: ~2.7GB                                            │
│    • Dimensions: 1024                                        │
│    • Features: Multilingual (100+ languages)                │
├─────────────────────────────────────────────────────────────┤
│  Total VRAM: ~14.1GB (59% of 24GB)                           │
│  Buffer: ~9.9GB for KV cache and concurrent requests        │
└─────────────────────────────────────────────────────────────┘
```

---

## Timeout Configuration

| Layer | Timeout | File |
|-------|---------|------|
| Frontend SSE | 180s | `frontend/src/lib/config.ts` |
| Gateway proxy | 180s | `backend/app/api/v1/emma.py` |
| ReAct global | 120s | `emma-agent-service/app/core/config.py` (`react_global_timeout_seconds`) |
| Swarm worker | 45s | `SWARM_WORKER_TIMEOUT_SECONDS` |

---

## Multi-Pipeline RAG Sectors

Emma supports per-deployment sector configuration via `ACTIVE_SECTOR` environment variable.

| Sector | Specialist Agents | hybrid_alpha | top_k | Chunk Strategy |
|--------|-------------------|-------------|-------|----------------|
| `legal` | legal, labor, fiscal, contract, compliance, privacy | 0.7 | 12 | legal_sections (1500/200) |
| `medical` | general | 0.6 | 15 | paragraph (1200/150) |
| `documental` | general, education, realestate | 0.5 | 10 | semantic (1000/100) |

See `emma-agent-service/app/agents/langgraph/sectors/` for implementation.

---

## Emma Reactive (Event-Driven Proactive AI)

Emma Reactive extends Emma beyond request-response into a **proactive, event-driven, multi-channel** assistant. See **[EMMA_REACTIVE.md](./EMMA_REACTIVE.md)** for full documentation.

### Quick Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Event Bus** | Redis Streams | Inter-service events (document.indexed, connector.synced) |
| **Trigger Engine** | Python rules engine | Match events → dispatch actions per tenant |
| **Background Service** | LangGraph + Celery | Proactive analysis without user HTTP request |
| **Notifications** | Redis Pub/Sub + WebSocket | Real-time in-app, email, webhook |
| **Multi-Channel** | Telegram, WhatsApp, Slack, Email | External messaging with user pairing |
| **Heartbeat** | Celery Beat (30min) | Proactive context evaluation + insight generation |

---

## Critical Files

### Emma Agent Service (`backend/microservices/emma-agent-service/`)

| File | Purpose |
|------|---------|
| `app/api/emma.py` | REST + SSE endpoints (`/emma/query`, `/emma/stream`) |
| `app/agents/langgraph/graph.py` | StateGraph definition (compiled with checkpointer + Store) |
| `app/agents/langgraph/state.py` | `ReActState` TypedDict + initial state factory |
| `app/agents/langgraph/api.py` | `stream_react_query()` — SSE streaming bridge |
| `app/agents/langgraph/nodes/` | 8 node implementations |
| `app/agents/langgraph/tools/` | 9 tools via ToolRegistry |
| `app/agents/langgraph/sectors/` | Sector configuration |
| `app/agents/llm_router.py` | LLMRouter with dual-phase client pool |
| `app/core/checkpointer.py` | PostgresSaver + Store singletons (shared pool) |
| `app/services/memory/user_facts.py` | User memory CRUD (Store primary, legacy fallback) |
| `app/services/emma_persistence_service.py` | Session metadata (slim mode with checkpointer) |
| `app/services/prompt_registry.py` | Unified prompt registry (54 entries, single source of truth) |
| `app/services/langfuse_prompt_client.py` | Langfuse client with production label pinning |
| `config/prompts/emma_prompts.yaml` | LLM prompts YAML fallback (Langfuse is primary) |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx` | Main chat component |
| `frontend/apps/on-premise/src/lib/services/emma.service.ts` | API client + SSE parser |

---

## Voice-First Architecture (Phase 2 — Planned)

### Planned Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EMMA VOICE ASSISTANT                                 │
│                                                                              │
│   🎤 User speaks → STT → SGLang (Qwen3.5) → TTS → 🔊                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Component | Technology | Target Latency |
|-----------|------------|----------------|
| **STT** | faster-whisper (local) | <500ms |
| **LLM** | SGLang (Qwen3.5-9B) | <200ms first token |
| **TTS** | Gemini Pro | <300ms first chunk |
| **Streaming** | WebSocket | Bidirectional |
| **End-to-end** | — | **<1.5s** |

---

## Related Documentation

- [USER_MEMORY.md](./USER_MEMORY.md) - Cross-session persistent user facts (AsyncPostgresStore)
- [EMMA_REACTIVE.md](./EMMA_REACTIVE.md) - Emma Reactive event-driven system
- [RAG_PIPELINE.md](./RAG_PIPELINE.md) - RAG Implementation Blueprint
- [MODULAR_ARCHITECTURE.md](./MODULAR_ARCHITECTURE.md) - On-Premise Architecture
- [PUBLIC_KNOWLEDGE.md](./PUBLIC_KNOWLEDGE.md) - BOE Legislation & Legal Knowledge Graph

---

*Architecture: LangGraph ReAct Agent + SGLang (Qwen3.5-9B) + PostgresSaver + AsyncPostgresStore + SmartSearch + Multi-Pipeline RAG Sectors + Emma Reactive*
