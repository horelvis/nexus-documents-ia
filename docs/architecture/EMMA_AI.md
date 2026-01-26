# Emma AI - Technical Architecture

Emma is the intelligent AI assistant for NouxCubeIA, built on **Anthropic Skill Custom** framework with **vLLM** (Qwen3) as the primary inference engine.

> **Current Status**: EmmaCoordinator is the active execution path. Voice-first capabilities are planned for Phase 2.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EMMA AI ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────┐    │
│  │   Frontend  │     │  API Gateway│     │     Emma Service            │    │
│  │  Next.js 15 │────▶│   FastAPI   │────▶│  ┌─────────────────────┐   │    │
│  │  EmmaChat   │     │   :8000     │     │  │  EmmaCoordinator    │   │    │
│  └─────────────┘     └─────────────┘     │  │  (Orchestrator)     │   │    │
│                             │            │  └──────────┬──────────┘   │    │
│                             │            │             │              │    │
│                             ▼            │  ┌──────────▼──────────┐   │    │
│  ┌─────────────────────────────────────┐ │  │  Specialized Agents │   │    │
│  │         Data Layer                   │ │  │  - SearchAgent      │   │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────┐ │ │  │  - ContractAgent    │   │    │
│  │  │PostgreSQL│ │ Weaviate │ │Redis │ │ │  │  - LaborAgent       │   │    │
│  │  │   +AGE   │ │ (Vector) │ │Memory│ │ │  │  - FiscalAgent      │   │    │
│  │  └──────────┘ └──────────┘ └──────┘ │ │  │  - PrivacyAgent     │   │    │
│  └─────────────────────────────────────┘ │  │  - ComplianceAgent  │   │    │
│                                          │  │  - AnalystAgent     │   │    │
│                                          │  │  - SummarizerAgent  │   │    │
│                                          │  └─────────────────────┘   │    │
│                                          └────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## System Flow

```
FRONTEND (Next.js)
┌─────────────────────────────────────────────────────────────────────────────┐
│  /[tenantId]/chat/page.tsx                                                  │
│       │                                                                      │
│       v                                                                      │
│  EmmaChat.tsx ───── emma.service.ts                                         │
│       │                    │                                                 │
│       │  queryEmmaStream() → POST /api/v1/weaviate/emma/query/stream        │
└───────│─────────────────────── SSE Stream ─────────────────────────────────┘
        │
        v
WEAVIATE MICROSERVICE (FastAPI - port 8007)
┌─────────────────────────────────────────────────────────────────────────────┐
│  app/api/emma.py                                                            │
│       │                                                                      │
│       v                                                                      │
│  EmmaService.execute_query_stream()                                         │
│       │                                                                      │
│       ├──→ MemoryService (load conversation history)                        │
│       │    Key: emma:conv:{tenant}:{session}                                │
│       │                                                                      │
│       └──→ EmmaCoordinator.execute() [PRIMARY]                              │
│            │                                                                 │
│            ├──→ SemanticPatternRouter (classify intent ~10ms)               │
│            │                                                                 │
│            ├──→ AgentThread (context management)                            │
│            │                                                                 │
│            └──→ Subagents via .as_tool()                                    │
│                 ├── SearchAgent                                             │
│                 ├── ContractAgent                                           │
│                 ├── ComplianceAgent                                         │
│                 ├── LaborAgent                                              │
│                 ├── FiscalAgent                                             │
│                 ├── PrivacyAgent                                            │
│                 ├── AnalystAgent                                            │
│                 └── SummarizerAgent                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Memory System (3 Layers)

### Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          MEMORY SERVICE (Unified)                           │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────┐    ┌───────────────────────────────────┐    │
│   │   ConversationMemory    │    │       PreferencesStore             │    │
│   │        (Redis)          │    │          (Redis)                   │    │
│   ├─────────────────────────┤    ├───────────────────────────────────┤    │
│   │ Key: emma:conv:         │    │ Key: emma:prefs:                   │    │
│   │   {tenant}:{session}    │    │   {tenant}:{user}                  │    │
│   │                         │    │                                    │    │
│   │ TTL: 30 min             │    │ TTL: Persistent                    │    │
│   │ Max: 100 messages       │    │                                    │    │
│   │ Max: 32K tokens         │    │ Fields:                            │    │
│   │                         │    │ - display_name                     │    │
│   │ Stores:                 │    │ - preferred_language               │    │
│   │ - Message history       │    │ - response_style                   │    │
│   │ - Active documents      │    │ - expertise_level                  │    │
│   │ - Tool results          │    │ - frequent_queries                 │    │
│   └─────────────────────────┘    └───────────────────────────────────┘    │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### Memory Limits

| Limit | Value | Purpose |
|-------|-------|---------|
| MAX_MESSAGES | 100 | Messages per session |
| MAX_TOKENS | 32,000 | Total tokens (~128KB) |
| MAX_MESSAGE_LENGTH | 8,000 chars | Per individual message |

### Key Files

- `app/services/memory/service.py` - Unified MemoryService
- `app/services/memory/conversation.py` - ConversationMemory (Redis)
- `app/services/memory/preferences.py` - PreferencesStore (Redis)
- `app/services/memory/types.py` - Message, ConversationContext, UserPreferences

---

## EmmaCoordinator (Main Orchestrator)

### Orchestration Patterns

| Pattern | Description | Use Cases |
|---------|-------------|-----------|
| **HANDOFF** | LLM decides delegation via `.as_tool()` | Default, conversational queries |
| **SEQUENTIAL** | Pipeline A→B→C | "Search, analyze, summarize" |
| **CONCURRENT** | Parallel A\|B\|C | "From legal, fiscal and labor perspective" |

### Execution Flow

```python
# 1. Pattern detection (SemanticRouter, ~10ms)
pattern = await detect_orchestration_pattern(query)

# 2. Load/Create AgentThread (Redis persistence)
thread = await self._load_or_create_thread(tenant_id, session_id)

# 3. Emma ChatAgent.run() with subagents as tools
#    Emma sees 8 available tools and decides which to invoke
result = await self._emma.run(query, thread)

# 4. Clean thinking tags (Qwen3)
answer = clean_thinking_tags(result.text)

# 5. Save thread state
await self._save_thread(thread)
```

### Main File

`backend/microservices/weaviate-service/app/agents/emma_coordinator.py`

---

## SemanticRouter (Intent Classification)

### SemanticPatternRouter

Classifies queries in ~10ms using local embeddings:

```python
# Model: sentence-transformers/all-MiniLM-L6-v2
# Latency: ~10ms per classification

Routes defined:
- conversational: Greetings, thanks, identity
- sequential: "First..., then..."
- concurrent: "From legal, fiscal and labor perspective"
```

### SemanticDomainRouter

Classifies queries by legal domain:

| Domain | Agent | Keywords |
|--------|-------|----------|
| contract | ContractAgent | contract, clause, terms |
| labor | LaborAgent | dismissal, payroll, collective agreement |
| fiscal | FiscalAgent | tax, VAT, IRPF |
| compliance | ComplianceAgent | GDPR, RGPD, compliance |
| privacy | PrivacyAgent | LOPDGDD, personal data |
| search | SearchAgent | search, find, documents |
| summary | SummarizerAgent | summarize, synthesize |
| general | AnalystAgent | analyze, evaluate, examine |

### File

`backend/microservices/weaviate-service/app/agents/orchestration/router.py`

---

## Specialized Agents (8)

### Core Agents

| Agent | Purpose | Temperature |
|-------|---------|-------------|
| **SearchAgent** | Document search | 0.2 |
| **AnalystAgent** | Deep analysis | 0.2 |
| **ContractAgent** | Contracts, clauses | 0.1 |
| **ComplianceAgent** | GDPR/RGPD | 0.1 |
| **SummarizerAgent** | Executive summaries | 0.3 |

### Legal Domain Agents

| Agent | Domain | Legislation |
|-------|--------|-------------|
| **LaborAgent** | Employment law | Workers' Statute |
| **FiscalAgent** | Tax | General Tax Law |
| **PrivacyAgent** | Data protection | LOPDGDD |

### File Location

`backend/microservices/weaviate-service/app/agents/agents/`

---

## RAG Pipeline (7 Layers)

```
Layer 0: Document Processing (chunking)
Layer 1: Semantic Chunking (structure-aware)
Layer 2: Query Intelligence ◄── Expansion, intent classification
Layer 3: Hybrid Retrieval + RRF ◄── Dense + Sparse fusion
Layer 4: Context Assembly ◄── Token management
Layer 5: Validated Generation ◄── LLM + semantic validation
Layer 6: Semantic Cache ◄── Redis (~90% latency reduction)
```

---

## vLLM Configuration

### Environment Variables

```bash
# vLLM (Primary LLM)
VLLM_ENABLED=true
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_MODEL=Qwen/Qwen3-4B
VLLM_MAX_MODEL_LEN=16384

# Embeddings (BGE-M3)
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024

# Redis (Memory + Context)
REDIS_HOST=redis
REDIS_PORT=6379

# Weaviate (Vector DB)
WEAVIATE_URL=http://weaviate:8080
```

### Recommended Configuration (RTX 4090 24GB)

```
┌─────────────────────────────────────────────────────────────┐
│  LLM: Qwen/Qwen3-4B                                         │
│    • VRAM: ~8GB (35% allocation)                            │
│    • Context: 16K tokens (configurable up to 32K)           │
├─────────────────────────────────────────────────────────────┤
│  Embedding: BAAI/bge-m3                                     │
│    • VRAM: ~2GB (10% allocation)                            │
│    • Dimensions: 1024                                       │
│    • Features: Multilingual (100+ languages)                │
├─────────────────────────────────────────────────────────────┤
│  Total VRAM: ~10GB (45% of 24GB)                            │
│  Buffer: ~14GB for batching and concurrent requests         │
└─────────────────────────────────────────────────────────────┘
```

---

## Timeout Configuration

| Layer | Timeout | File |
|-------|---------|------|
| Frontend | 180s | `frontend/src/lib/config.ts` |
| Gateway | 180s | `backend/app/api/v1/weaviate.py` |
| Coordinator | 300s | `emma_coordinator.py` |

---

## Critical Files

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/app/(main)/[tenantId]/chat/page.tsx` | Chat page |
| `frontend/src/components/emma-chat/EmmaChat.tsx` | Main component |
| `frontend/src/lib/services/emma.service.ts` | API client |
| `frontend/src/hooks/use-agent-chat.ts` | Chat hook |

### Weaviate Microservice

| File | Purpose |
|------|---------|
| `app/api/emma.py` | Emma endpoints |
| `app/services/emma_service.py` | Main service |
| `app/agents/emma_coordinator.py` | Main orchestrator |
| `app/agents/orchestration/router.py` | Semantic Router |
| `app/services/memory/service.py` | Unified memory |
| `app/tools/channel_tools.py` | Channel tools |

---

## Complete Execution Flow

### Example: "What risks does this contract have?"

```
1. FRONTEND
   └→ User types query in EmmaQueryInput
   └→ EmmaChat.handleSendQuery() called
   └→ emma.service.queryEmmaStream()
      POST /api/v1/weaviate/emma/query/stream
      Body: { query, session_id, tenant_id, context: { user_id, user_name } }

2. BACKEND GATEWAY (weaviate.py)
   └→ Validates JWT token
   └→ Injects tenant_id from claims
   └→ Proxies to Weaviate microservice (timeout: 180s)

3. WEAVIATE SERVICE (emma.py)
   └→ EmmaService.execute_query_stream()
       │
       ├→ Load conversation history (MemoryService)
       │   Key: emma:conv:{tenant}:{session}
       │
       ├→ Enrich user context (name, email, role, preferences)
       │
       └→ EmmaCoordinator.execute()
           │
           ├→ Pattern Detection (SemanticRouter)
           │   Query: "risks" + "contract"
           │   → HANDOFF pattern (default)
           │
           ├→ Load/Create AgentThread
           │
           ├→ Build context-aware query
           │
           └→ Emma ChatAgent.run(query, thread)
               │
               │  Emma sees 8 tools available:
               │  - search_agent, contract_agent, compliance_agent...
               │
               │  Emma decides to call:
               │  1. contract_agent.as_tool() → Analyze contract clauses
               │  2. compliance_agent.as_tool() → Check GDPR compliance
               │
               └→ Synthesize final answer

4. STREAMING EVENTS (SSE)
   └→ event: start
   └→ event: delegation { agent: "contract_agent" }
   └→ event: delegation { agent: "compliance_agent" }
   └→ event: token { text: "I have identified..." }
   └→ event: complete { answer, tools_used, confidence }

5. MEMORY STORAGE
   └→ MemoryService.add_exchange()
       - Store user message
       - Store assistant response
       - Store tools_used metadata
       - Apply token limits (truncate if needed)
```

---

## Voice-First Architecture (Phase 2)

### Planned Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EMMA VOICE ASSISTANT                                 │
│                                                                              │
│   🎤 User speaks → STT → vLLM (own model) → TTS → 🔊                        │
│                                                                              │
│   "Analyze the contract"  →  [Processing]  →  "I found 3 risks..."          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Voice Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **STT** | faster-whisper (local) | Speech to Text |
| **LLM** | vLLM (Qwen3) | Inference |
| **TTS** | Gemini Pro | Text to Speech |
| **Streaming** | WebSocket | Bidirectional |
| **VAD** | silero-vad | Voice Activity Detection |

### Latency Targets

| Phase | Target |
|-------|--------|
| VAD detection | <50ms |
| STT (Whisper) | <500ms |
| vLLM first token | <200ms |
| TTS first chunk | <300ms |
| **End-to-end** | **<1.5s** |

---

## Development

```bash
# Start backend services
cd backend/docker && ./start-dev.sh

# Verify Emma service
curl -H "Authorization: Bearer ${MICROSERVICES_API_KEY}" \
     http://localhost:8007/emma/health

# View Emma logs
docker logs docker-weaviate-service-1 --tail 100 -f
```

---

## SLM Router Integration

Emma integrates with the SLM Router for intelligent query pre-processing:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EMMA + SLM ROUTER INTEGRATION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Query                                                                 │
│       │                                                                      │
│       ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      SLM Router                                      │   │
│   │   • Generates TOON (Task-Oriented Orchestration Notation) plans     │   │
│   │   • Routes to GRAPH_ONLY / VECTOR_ONLY / HYBRID / ASK_CLARIFY       │   │
│   │   • Executes against Apache AGE (graph) and Weaviate (vector)       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       │ Structured context (not raw documents)                              │
│       ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     Emma Coordinator                                 │   │
│   │   • Receives pre-processed context from SLM Router                  │   │
│   │   • Delegates to specialized agents as needed                       │   │
│   │   • Generates natural language response                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   Benefits:                                                                  │
│   • 70-90% token reduction for structural queries                           │
│   • Faster response times (<500ms for graph-only queries)                   │
│   • More precise answers based on actual data                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### TOON Route Types

| Route | Emma Behavior | Example |
|-------|--------------|---------|
| `GRAPH_ONLY` | Direct answer from graph context | "ACME has 5 contracts" |
| `VECTOR_ONLY` | RAG with retrieved documents | "The contract mentions..." |
| `HYBRID` | Graph context + RAG documents | "ACME has 5 contracts, with risks in..." |
| `ASK_CLARIFY` | Ask user for more details | "Which client are you asking about?" |

For full SLM Router documentation, see [SLM_ROUTER.md](./SLM_ROUTER.md).

---

## Related Documentation

- [SLM_ROUTER.md](./SLM_ROUTER.md) - SLM Router (Query Planning)
- [SIL.md](./SIL.md) - Structural Intelligence Layer (Legacy)
- [RAG_PIPELINE.md](./RAG_PIPELINE.md) - RAG Implementation Blueprint
- [MODULAR_ARCHITECTURE.md](./MODULAR_ARCHITECTURE.md) - On-Premise Architecture

---

*Architecture: EmmaCoordinator + Anthropic Skill Custom + vLLM (Qwen3) + SLM Router*
