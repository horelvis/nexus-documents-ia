# SLM Router: Small Language Model Based Query Planning

> ⚠️ **REMOVED**: The SLM Router has been removed from the codebase and replaced by **Multi-Pipeline RAG Sectors**.
> See `emma-agent-service/app/agents/langgraph/sectors/` for the current architecture.
> Sectors provide per-deployment RAG tuning (retrieval parameters, agent filtering, graph schemas, chunking strategies) configured via `ACTIVE_SECTOR` environment variable.
> This document is kept for historical reference only.

## Overview (Legacy)

The **SLM Router** was a unified query routing system that replaced fragmented routing approaches with a single, deterministic planning system using a Small Language Model (SLM). It generated **TOON (Task-Oriented Orchestration Notation)** plans that described how to answer a query.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  EVOLUTION: SIL → SLM Router                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SIL (Structural Intelligence Layer)     →    SLM Router                    │
│  ─────────────────────────────────────        ──────────────                │
│  ❌ Rule-based intent detection          →    ✅ SLM-generated plans         │
│  ❌ Hardcoded Cypher templates           →    ✅ Dynamic query generation    │
│  ❌ Manual entity extraction             →    ✅ LLM-powered extraction      │
│  ❌ Static routing rules                 →    ✅ Adaptive routing            │
│  ❌ No learning capability               →    ✅ Continuous learning         │
│                                                                              │
│  Key Insight:                                                                │
│  ───────────────────────────────────────────────────────────────────────    │
│  Instead of coding routing rules, we train a small, fast model to           │
│  generate structured execution plans in TOON format.                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SLM ROUTER ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Query                                                                 │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        SLM ROUTER                                    │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │    │
│  │  │  TenantSchema   │  │  HistoryManager │  │  SLMClient      │     │    │
│  │  │   Provider      │  │   (Redis)       │  │  (Qwen2-0.5B)   │     │    │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘     │    │
│  │           │                    │                    │               │    │
│  │           └────────────────────┼────────────────────┘               │    │
│  │                               │                                     │    │
│  │                               ▼                                     │    │
│  │                     ┌─────────────────────┐                         │    │
│  │                     │    TOON Plan        │                         │    │
│  │                     │  (Structured JSON)  │                         │    │
│  │                     └──────────┬──────────┘                         │    │
│  │                               │                                     │    │
│  │                               ▼                                     │    │
│  │                     ┌─────────────────────┐                         │    │
│  │                     │   TOONExecutor      │                         │    │
│  │                     └──────────┬──────────┘                         │    │
│  └───────────────────────────────┼─────────────────────────────────────┘    │
│                                  │                                           │
│           ┌──────────────────────┼──────────────────────┐                   │
│           │                      │                      │                   │
│           ▼                      ▼                      ▼                   │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐           │
│  │  Apache AGE     │   │    Weaviate     │   │   Ask Clarify   │           │
│  │  (Graph/Cypher) │   │  (Vector/RAG)   │   │   (User Input)  │           │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## TOON: Task-Oriented Orchestration Notation

TOON is the structured output format of the SLM Router. Every query produces a validated TOON plan:

```yaml
# Example TOON Plan
version: "1.0"
route: GRAPH_ONLY
confidence: 0.92

entities:
  - name: "ACME"
    type: "client"
    graph_label: "Entity"
    source: "query"
    confidence: 0.95

graph:
  enabled: true
  operation: COUNT
  cypher_template: |
    MATCH (c:Entity {name: $client_name, type: 'client'})
    -[:HAS_DOCUMENT]->(d:structural_document {semantic_type: 'contract'})
    WHERE d.tenant_id = $tenant_id
    RETURN count(d) as count
  params:
    client_name: "ACME"
    tenant_id: "tenant-123"
  limit: 50
  timeout_ms: 2000

vector:
  enabled: false

reasoning: "Counting query for specific client contracts - graph-only path"
```

### Route Types

| Route | Description | Data Source | Use Case |
|-------|-------------|-------------|----------|
| `GRAPH_ONLY` | Structural/counting queries | Apache AGE | "How many contracts?" |
| `VECTOR_ONLY` | Semantic search queries | Weaviate | "Find documents about..." |
| `HYBRID` | Structure + content | Both | "List ACME contracts and summarize risks" |
| `ASK_CLARIFY` | Ambiguous query | None | "Documents" (too vague) |

### Graph Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `COUNT` | Count matching nodes | "How many contracts?" |
| `LIST` | List nodes with properties | "Show all ACME documents" |
| `EXISTS` | Check if nodes exist | "Does ACME have contracts?" |
| `TRAVERSE` | Follow relationships | "Contracts related to this invoice" |
| `AGGREGATE` | Sum, average, etc. | "Total value of contracts" |

### Vector Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `SEMANTIC_SEARCH` | Meaning-based search | "Find documents about liability" |
| `SIMILARITY` | Find similar documents | "Documents like this one" |
| `RERANK` | Search + rerank | "Most relevant contracts" |

## Components

### 1. SLM Client

The SLM Client manages the Small Language Model that generates TOON plans:

```python
from app.services.slm_router import get_slm_client

# Generate a TOON plan
plan = await slm_client.generate_plan(
    query="How many contracts does ACME have?",
    tenant_schema=schema_context,
    conversation_history=history,
    tenant_id="tenant-123"
)
```

**Supported Models:**
- `Qwen/Qwen2-0.5B-Instruct` (default, ~1GB VRAM)
- `Qwen/Qwen2-1.5B-Instruct` (better accuracy)
- Any vLLM-compatible model

### 2. TOON Executor

Executes validated TOON plans against data sources:

```python
from app.services.slm_router import get_toon_executor

result = await executor.execute(plan)

if result.success:
    # Graph results
    print(f"Graph rows: {result.graph_row_count}")

    # Vector results
    print(f"Documents found: {result.vector_result_count}")

    # Context for main LLM
    print(result.context_for_llm)
```

### 3. Tenant Schema Provider

Provides tenant-specific context for accurate planning:

```python
from app.services.slm_router import get_schema_provider

context = await schema_provider.get_prompt_context(tenant_id)
# Returns: document types, clients, folder structure
```

### 4. History Manager

Manages conversation history for contextual queries:

```python
from app.services.slm_router import get_history_manager

# Add a turn to history
await history_manager.add_turn(
    session_id="session-123",
    tenant_id="tenant-123",
    query="How many contracts does ACME have?",
    plan=toon_plan,
    result_summary="count=5"
)

# Resolve references ("those documents", "the same client")
resolution = await history_manager.resolve_references(
    query="Show me those documents",
    session_id="session-123",
    tenant_id="tenant-123"
)
```

## Guardrails

Safety limits protect system resources:

```python
class TOONGuardrails:
    GRAPH = {
        "limit": {"max": 300, "default": 50},
        "hops": {"max": 4, "default": 2},
        "timeout_ms": {"max": 5000, "default": 2000},
    }

    VECTOR = {
        "top_k": {"max": 12, "default": 5},
        "rerank_limit": {"max": 20, "default": 10},
    }

    SLM = {
        "max_tokens": 512,
        "temperature": {"max": 0.2, "default": 0.0},
        "timeout_ms": 3000,
    }

    HISTORY = {
        "max_turns": 5,
        "max_tokens": 500,
        "entity_retention": 10,
        "ttl_seconds": 3600,
    }
```

## API Usage

### Main Entry Point

```python
from app.services.slm_router import get_slm_router, TOONRoute

# Initialize router
router = get_slm_router()
await router.initialize()

# Plan and execute in one call
result = await router.route(
    query="How many contracts does ACME have?",
    tenant_id="tenant-123",
    session_id="session-456"
)

# Handle result
if result.plan.route == TOONRoute.ASK_CLARIFY:
    print(f"Need clarification: {result.clarification_question}")
else:
    print(f"Context for LLM:\n{result.context_for_llm}")
```

### Plan Only (No Execution)

```python
# Generate plan without executing
plan = await router.plan(
    query="Show me all ACME contracts",
    tenant_id="tenant-123",
    session_id="session-456"
)

print(plan.to_yaml())
```

### Building Plans Programmatically

```python
from app.services.slm_router import (
    TOONPlanBuilder,
    TOONRoute,
    GraphOperation
)

plan = TOONPlanBuilder()\
    .with_route(TOONRoute.GRAPH_ONLY, confidence=0.9)\
    .with_entity("ACME", "client", graph_label="Entity")\
    .with_graph_query(
        operation=GraphOperation.COUNT,
        cypher_template="MATCH (d:structural_document) WHERE d.client = $client RETURN count(d)",
        params={"client": "ACME"},
        limit=50
    )\
    .with_context(
        original_query="Count ACME contracts",
        tenant_id="tenant-123",
        reasoning="Direct count query"
    )\
    .build()
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /slm/route` | POST | Plan and execute a query |
| `POST /slm/plan` | POST | Generate plan only |
| `GET /slm/health` | GET | Health check |
| `GET /slm/metrics` | GET | Router metrics |

### Example Request

```bash
curl -X POST http://localhost:8007/slm/route \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${API_KEY}" \
  -d '{
    "query": "How many contracts does ACME have?",
    "tenant_id": "tenant-123",
    "session_id": "session-456"
  }'
```

### Example Response

```json
{
  "success": true,
  "plan": {
    "route": "GRAPH_ONLY",
    "confidence": 0.92,
    "entities": [
      {"name": "ACME", "type": "client", "source": "query"}
    ]
  },
  "graph_result": {
    "count": 5
  },
  "context_for_llm": "## Structural Information\n**Count:** 5",
  "execution_time_ms": 45.2
}
```

## Continuous Learning

The SLM Router includes a continuous learning system that automatically fine-tunes the SLM based on successful query→plan mappings:

```python
from app.services.slm_router import get_learning_service

learning = get_learning_service()

# Export training data
examples = await learning.export_training_data(tenant_id="tenant-123")

# Trigger fine-tuning (when enough examples collected)
await learning.trigger_finetune()
```

**Learning Flow:**
1. Successful executions are logged to Redis
2. System collects query→plan pairs with positive outcomes
3. When threshold is reached, fine-tuning is triggered
4. New model is deployed with improved routing accuracy

## Integration with Emma AI

The SLM Router integrates with Emma as a pre-processing layer:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EMMA + SLM ROUTER INTEGRATION                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Query: "How many contracts does ACME have in 2024?"                  │
│       │                                                                      │
│       ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      SLM Router                                      │   │
│   │   1. Generate TOON plan                                             │   │
│   │   2. Execute against Apache AGE                                     │   │
│   │   3. Return: count=5, context="ACME has 5 contracts in 2024"        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     Emma Coordinator                                 │   │
│   │   Receives structured context, generates natural response:          │   │
│   │   "ACME has 5 contracts from 2024. Would you like me to list them?" │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   🎯 Result: Precise answer, minimal tokens, fast response                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## File Structure

```
backend/microservices/weaviate-service/app/services/slm_router/
├── __init__.py              # Exports and package documentation
├── toon_schema.py           # TOON models, enums, guardrails
├── slm_client.py            # SLM client for plan generation
├── toon_executor.py         # Plan execution against data sources
├── tenant_schema.py         # Tenant context provider
├── history_manager.py       # Conversation history management
├── router.py                # Main SLM Router orchestrator
└── continuous_learning.py   # Automated fine-tuning system
```

## Configuration

```bash
# Environment variables
SLM_ROUTER_ENABLED=true
SLM_MODEL=Qwen/Qwen2-0.5B-Instruct
SLM_BASE_URL=http://vllm:8000/v1
SLM_TEMPERATURE=0.0
SLM_MAX_TOKENS=512
SLM_TIMEOUT_MS=3000

# Redis for history and training data
REDIS_HOST=redis
REDIS_PORT=6379

# Apache AGE for graph queries
AGE_GRAPH_NAME=nexus_knowledge

# Weaviate for vector queries
WEAVIATE_URL=http://weaviate:8080
```

## Metrics

The SLM Router exposes metrics for monitoring:

```python
metrics = await router.health_check()

# Example metrics:
{
    "initialized": true,
    "enabled": true,
    "metrics": {
        "total_requests": 1250,
        "plans_generated": 1248,
        "executions_completed": 1245,
        "fallbacks_used": 12,
        "average_plan_time_ms": 45.2,
        "average_execution_time_ms": 120.5
    }
}
```

## Migration from SIL

If you were using SIL, the migration to SLM Router is straightforward:

| SIL Concept | SLM Router Equivalent |
|-------------|----------------------|
| `IntentType` | `TOONRoute` |
| `ReasoningType` | `GraphOperation` / `VectorOperation` |
| `sil_engine.process_query()` | `slm_router.route()` |
| `structural_collection` | Integrated in `TOONExecutor` |
| `intent_detector` | `SLMClient` (LLM-based) |
| `cypher_builder` | Embedded in TOON plans |

The SLM Router maintains backward compatibility with SIL concepts while providing more flexibility and learning capability.

---

*Documentation updated: 2026-01-26*
*Version: 1.0*
