# SLM Router - Technical Documentation

## Overview

The **SLM Router** is a query planning and execution system that uses a Small Language Model (SLM) to generate structured execution plans called **TOON (Task-Oriented Orchestration Notation)**. It routes queries to the optimal data source (Apache AGE graph, Weaviate vector, or both), achieving 70-90% token savings compared to full RAG.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SLM ROUTER ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Query: "How many contracts does ACME have?"                          │
│       │                                                                      │
│       ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         SLMRouter.route()                            │   │
│   │   Coordinates: SLMClient, TOONExecutor, SchemaProvider, History     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ├──────────────────┬───────────────────┬──────────────────┐           │
│       ▼                  ▼                   ▼                  ▼           │
│   ┌──────────┐    ┌─────────────┐    ┌─────────────┐    ┌────────────┐     │
│   │SLMClient │    │TenantSchema │    │HistoryMgr  │    │Continuous  │     │
│   │(Planning)│    │  Provider   │    │  (Redis)   │    │ Learning   │     │
│   └────┬─────┘    └──────┬──────┘    └──────┬─────┘    └─────┬──────┘     │
│        │                 │                  │                 │            │
│        │   schema context│   conversation  │   training data │            │
│        │◄────────────────┘   history       │◄────────────────┘            │
│        │◄──────────────────────────────────┘                              │
│        │                                                                   │
│        ▼                                                                   │
│   ┌──────────────────────────────────────────────────────────────────┐    │
│   │                         TOON Plan                                 │    │
│   │   route: GRAPH_ONLY | VECTOR_ONLY | HYBRID | ASK_CLARIFY         │    │
│   │   entities: [{name, type, graph_label}]                          │    │
│   │   graph: {cypher_template, params, operation}                    │    │
│   │   vector: {operation, filters, top_k}                            │    │
│   └───────────────────────────────┬──────────────────────────────────┘    │
│                                   │                                        │
│                                   ▼                                        │
│   ┌──────────────────────────────────────────────────────────────────┐    │
│   │                       TOONExecutor                                │    │
│   │   ┌─────────────────┐              ┌─────────────────┐           │    │
│   │   │  GraphExecutor  │              │ VectorExecutor  │           │    │
│   │   │  (Apache AGE)   │              │   (Weaviate)    │           │    │
│   │   │                 │              │                 │           │    │
│   │   │  • CypherValid  │              │  • RAG Pipeline │           │    │
│   │   │  • Parameterized│              │  • Filters      │           │    │
│   │   │  • Guardrails   │              │  • Reranking    │           │    │
│   │   └────────┬────────┘              └────────┬────────┘           │    │
│   └────────────┼───────────────────────────────┼─────────────────────┘    │
│                │                               │                           │
│                ▼                               ▼                           │
│   ┌─────────────────────┐         ┌─────────────────────┐                 │
│   │    Apache AGE       │         │     Weaviate        │                 │
│   │   (PostgreSQL)      │         │   (Vector DB)       │                 │
│   │                     │         │                     │                 │
│   │  Structural data:   │         │  Semantic content:  │                 │
│   │  - Document counts  │         │  - Document text    │                 │
│   │  - Relationships    │         │  - Embeddings       │                 │
│   │  - Entity graph     │         │  - Similarity       │                 │
│   └─────────────────────┘         └─────────────────────┘                 │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
slm_router/
├── __init__.py              # Public API exports
├── router.py                # Main SLMRouter orchestrator (602 lines)
├── slm_client.py            # SLM inference (TGI/vLLM/Ollama) (771 lines)
├── toon_executor.py         # Plan execution engine (700+ lines)
├── toon_schema.py           # TOON data models and validation
├── tenant_schema.py         # Tenant context extraction from Apache AGE
├── history_manager.py       # Conversation state in Redis
├── continuous_learning.py   # Automated fine-tuning (551 lines)
└── README.md                # This documentation
```

## Component Details

### 1. SLMRouter (router.py)

The main orchestrator that coordinates all components.

**Key Methods:**

```python
# Plan only (no execution)
plan = await router.plan(query, tenant_id, session_id)

# Plan and execute (main entry point)
result = await router.route(query, tenant_id, session_id)

# Execute existing plan
result = await router.execute(plan)

# Health check
status = await router.health_check()
```

**Configuration:**

```python
SLMRouterConfig(
    enabled=True,                    # Enable/disable router
    use_redis=True,                  # Use Redis for caching
    slm_config=SLMConfig(...),       # SLM provider config
    fallback_to_vector=True,         # Fallback on low confidence
    min_confidence_threshold=0.4,    # Min confidence to trust plan
    collect_training_data=True       # Collect for continuous learning
)
```

### 2. SLMClient (slm_client.py)

Generates TOON plans using a Small Language Model.

**Supported Providers:**
- `tgi` - Text Generation Inference (recommended)
- `vllm` - vLLM server
- `ollama` - Ollama local models
- `local` - Direct transformers loading

**Provider Configuration:**

```python
SLMConfig(
    provider="tgi",
    tgi_base_url="http://tgi:8080",
    tgi_model="Qwen/Qwen2-0.5B-Instruct",
    max_tokens=512,
    temperature=0.0,  # Deterministic for consistent plans
    timeout_ms=3000
)
```

### 3. TOONExecutor (toon_executor.py)

Executes validated TOON plans against data sources.

**Components:**
- `GraphExecutor` - Executes Cypher against Apache AGE
- `VectorExecutor` - Executes semantic search in Weaviate
- `CypherValidator` - Security validation for Cypher queries

**Security Features:**
- Cypher injection prevention
- Parameter validation
- Query timeout enforcement
- Result limit guardrails

### 4. TenantSchemaProvider (tenant_schema.py)

Extracts and caches tenant-specific schema information.

**Extracted Information:**
- Document types (contract, invoice, etc.)
- Folder types (case, project, etc.)
- Known entities (clients, departments)
- Domains (legal, fiscal, hr)
- Graph labels available
- Custom terminology

**Caching:**
- In-memory cache (5 min default)
- Optional Redis cache for distributed systems

### 5. HistoryManager (history_manager.py)

Manages conversation state for contextual queries.

**Features:**
- Multi-turn conversation tracking
- Entity resolution ("those documents", "the same client")
- TOON plan history for continuations
- Redis-backed persistence

### 6. ContinuousLearningService (continuous_learning.py)

Automated fine-tuning based on usage patterns.

**Pipeline:**
1. **Collection**: Successful query→plan mappings stored in Redis
2. **Monitoring**: Background check every hour
3. **Training**: LoRA fine-tuning during maintenance window (3 AM)
4. **Deployment**: Hot-swap updated model without downtime

**Configuration:**

```python
LearningConfig(
    enabled=True,
    min_examples=500,              # Minimum examples before training
    maintenance_hour=3,            # 3 AM maintenance window
    check_interval_seconds=3600,   # Check every hour
    min_success_rate=0.80,         # 80% success rate required
    training_epochs=3,
    batch_size=16
)
```

## TOON Schema

### Route Types

| Route | Description | Data Source | Example |
|-------|-------------|-------------|---------|
| `GRAPH_ONLY` | Structural queries | Apache AGE | "How many contracts?" |
| `VECTOR_ONLY` | Semantic search | Weaviate | "Find documents about..." |
| `HYBRID` | Structure + content | Both | "List ACME contracts and summarize" |
| `ASK_CLARIFY` | Ambiguous query | None | "documents" (too vague) |

### Graph Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `COUNT` | Count matching nodes | "How many?" |
| `LIST` | List nodes with properties | "Show all" |
| `EXISTS` | Check existence | "Does X have?" |
| `TRAVERSE` | Follow relationships | "Related to" |
| `AGGREGATE` | Sum, average, etc. | "Total value" |

### Vector Operations

| Operation | Description | Example |
|-----------|-------------|---------|
| `SEMANTIC_SEARCH` | Meaning-based search | "About liability" |
| `SIMILARITY` | Similar documents | "Like this one" |
| `RERANK` | Search + rerank | "Most relevant" |

### Guardrails

```python
TOONGuardrails = {
    "GRAPH": {
        "limit": {"max": 300, "default": 50},
        "hops": {"max": 4, "default": 2},
        "timeout_ms": {"max": 5000, "default": 2000}
    },
    "VECTOR": {
        "top_k": {"max": 12, "default": 5},
        "rerank_limit": {"max": 20, "default": 10}
    },
    "SLM": {
        "max_tokens": 512,
        "temperature": {"max": 0.2, "default": 0.0},
        "timeout_ms": 3000
    }
}
```

## API Endpoints

Defined in `app/api/slm_router.py`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /slm/route` | POST | Plan and execute query |
| `POST /slm/plan` | POST | Generate plan only |
| `GET /slm/health` | GET | Health check |
| `GET /slm/metrics` | GET | Router metrics |
| `GET /slm/learning/status` | GET | Learning service status |
| `POST /slm/learning/trigger` | POST | Manual training trigger |

## Integration with Emma AI

The SLM Router integrates as a pre-processing layer for Emma:

```python
# In Emma service
async def process_query(query: str, tenant_id: str) -> str:
    # 1. Try SLM Router first
    if slm_router.config.enabled:
        result = await slm_router.route(query, tenant_id)

        if result.success and result.context_for_llm:
            # 2. Pass structured context to Emma
            return await emma.generate_response(
                query=query,
                context=result.context_for_llm  # Pre-processed, minimal tokens
            )

    # 3. Fallback to full RAG
    return await emma.full_rag_response(query, tenant_id)
```

## Error Handling

### Graceful Degradation

1. **SLM timeout**: Falls back to VECTOR_ONLY route
2. **Graph unavailable**: Uses VECTOR_ONLY route
3. **Vector unavailable**: Uses GRAPH_ONLY if possible
4. **Both unavailable**: Returns error with explanation

### Background Task Errors

All fire-and-forget tasks (history storage, training collection) use error callbacks:

```python
task.add_done_callback(self._handle_background_task_error)
```

## Security

### Cypher Injection Prevention

The `CypherValidator` class prevents injection attacks:

1. **Dangerous keyword blocking**: DELETE, DROP, CREATE, SET, MERGE, etc.
2. **Injection pattern detection**: Command chaining, SQL comments, template injection
3. **Parameter validation**: Checks string values for suspicious content

### Tenant Isolation

- All queries include `tenant_id` filter
- Schema extraction is tenant-scoped
- Training data is isolated by tenant

## Monitoring

### Metrics Available

```python
{
    "total_requests": 1250,
    "plans_generated": 1248,
    "executions_completed": 1245,
    "fallbacks_used": 12,
    "average_plan_time_ms": 45.2,
    "average_execution_time_ms": 120.5
}
```

### Health Check Response

```json
{
    "initialized": true,
    "enabled": true,
    "slm": {"status": "healthy", "provider": "tgi"},
    "executor": {
        "initialized": true,
        "graph_available": true,
        "vector_available": true
    },
    "metrics": {...}
}
```

## Testing

```python
# Unit test example
async def test_graph_only_route():
    router = get_slm_router()
    await router.initialize()

    result = await router.route(
        query="How many contracts does ACME have?",
        tenant_id="test-tenant"
    )

    assert result.success
    assert result.plan.route == TOONRoute.GRAPH_ONLY
    assert result.graph_result.get("count") is not None
```

## Troubleshooting

### Common Issues

1. **"Graph executor not initialized"**
   - Check Apache AGE connection
   - Verify SIL graph provider is available
   - Check PostgreSQL connection settings

2. **"Low confidence, fallback to vector"**
   - SLM may need more context
   - Consider lowering `min_confidence_threshold`
   - Check tenant schema extraction

3. **"Training collection failed"**
   - Verify Redis connection
   - Check Redis memory limits
   - Review training example format

### Debug Logging

```python
# Enable debug logging for SLM Router
import logging
logging.getLogger("app.services.slm_router").setLevel(logging.DEBUG)
```

---

*Version 1.0 - January 2026*
*Maintained by NouxCubeIA Team*
