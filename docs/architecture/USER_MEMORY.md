# User Memory — Cross-Session Persistent Facts

Emma's User Memory system gives the assistant **persistent recall across chat sessions**. When a user says "Me llamo Carlos, trabajo en Legal", Emma remembers that fact forever (or until the user asks to forget), even after session expiry, browser close, or server restart.

Unlike session-based conversation history (Redis, 30min TTL), User Memory uses **PostgreSQL** as the source of truth, with a Redis cache for fast reads. Facts survive indefinitely and are scoped to `(tenant_id, user_id)`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         WRITE PATH                                  │
│                                                                     │
│  User message ──→ Emma responds ──→ fire-and-forget asyncio.task    │
│                                          │                          │
│                                    FactExtractor                    │
│                                    ┌─────────────┐                  │
│                                    │ Stage 1:     │                  │
│                                    │ Regex (~1ms) │──→ declared     │
│                                    │ "me llamo X" │    facts        │
│                                    ├─────────────┤                  │
│                                    │ Stage 2:     │                  │
│                                    │ LLM (~200ms) │──→ inferred     │
│                                    │ (optional)   │    facts        │
│                                    └──────┬──────┘                  │
│                                           │                         │
│                                    UserFactsService                 │
│                                    ┌──────▼──────┐                  │
│                                    │  UPSERT     │                  │
│                                    │  PostgreSQL  │                  │
│                                    │  + cache     │                  │
│                                    │  invalidate  │                  │
│                                    └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                          READ PATH                                  │
│                                                                     │
│  New query arrives ──→ create_initial_react_state()                 │
│                              │                                      │
│                    UserFactsService.format_facts_for_prompt()       │
│                              │                                      │
│                     ┌────────▼────────┐                             │
│                     │  Redis cache    │──── hit ──→ return facts    │
│                     │  (1h TTL)       │                             │
│                     └────────┬────────┘                             │
│                              │ miss                                 │
│                     ┌────────▼────────┐                             │
│                     │  PostgreSQL     │──→ cache + return           │
│                     │  (active=true)  │                             │
│                     └─────────────────┘                             │
│                                                                     │
│  Facts formatted as:                                                │
│    ## Memoria del usuario                                           │
│    - Nombre: Carlos                                                 │
│    - Departamento: Legal                                            │
│                                                                     │
│  Injected into:                                                     │
│    1. classify_node → conversational fast-path system prompt        │
│    2. react_loop_node → ReAct system prompt                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Table: `emma_user_memory_facts`

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | PK | `gen_random_uuid()` | Primary key |
| `tenant_id` | UUID | NOT NULL | — | Tenant isolation |
| `user_id` | VARCHAR(255) | NOT NULL | — | KeyCloak user ID |
| `category` | VARCHAR(50) | NOT NULL | — | `identity`, `work`, `preference`, `interest` |
| `fact_key` | VARCHAR(100) | NOT NULL | — | e.g. `name`, `department`, `language` |
| `fact_value` | TEXT | NOT NULL | — | e.g. `Carlos`, `Legal`, `español` |
| `confidence` | FLOAT | NOT NULL | `1.0` | 1.0 = declared, 0.5–0.9 = inferred |
| `source` | VARCHAR(20) | NOT NULL | `declared` | `declared` or `inferred` |
| `source_query` | TEXT | NULL | — | Original user message that triggered extraction |
| `is_active` | BOOLEAN | NOT NULL | `true` | Soft-delete flag |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `now()` | Last update timestamp |

### Indexes

| Name | Columns | Type | Description |
|------|---------|------|-------------|
| `idx_user_memory_tenant_id` | `tenant_id` | B-tree | Fast tenant lookup |
| `idx_user_memory_user_id` | `user_id` | B-tree | Fast user lookup |
| `idx_user_memory_tenant_user` | `tenant_id, user_id` | B-tree | Composite lookup |
| `idx_user_memory_active` | `tenant_id, user_id, is_active` | B-tree | Active facts filter |
| `uq_user_memory_active_fact` | `tenant_id, user_id, category, fact_key` | **Partial UNIQUE** (`WHERE is_active = true`) | One active fact per user+category+key |

The partial unique index is the key design choice — it allows soft-deleted duplicates while guaranteeing exactly one active fact per `(tenant, user, category, key)` combination.

### Migration

```bash
cd backend && alembic upgrade head
```

Migration file: `alembic/versions/d4e5f6g7h8i9_add_user_memory_facts.py`

---

## Components

| Component | Module | Description |
|-----------|--------|-------------|
| **UserFactsService** | `memory/user_facts.py` | CRUD + Redis cache. Singleton via `get_user_facts_service()`. Reads (Redis → PG fallback), writes (PG UPSERT + cache invalidation), GDPR hard-delete |
| **FactExtractor** | `memory/fact_extractor.py` | Two-stage extraction: regex (~1ms) + optional LLM (~200ms). Fire-and-forget entry point `extract_and_save_facts()` |
| **MemoryService** | `memory/service.py` | Unified interface that wraps ConversationMemory + PreferencesStore + UserFactsService. Enriches `get_user_context()` with persistent facts |
| **ReActState** | `langgraph/state.py` | `user_memory: Optional[str]` field. Loaded at state initialization |

---

## Read Path

1. **State initialization** (`create_initial_react_state` in `state.py`):
   - If `user_id` is present, calls `UserFactsService.format_facts_for_prompt(tenant_id, user_id)`
   - Result stored in `state["user_memory"]`

2. **Redis cache** (key: `emma:facts:{tenant_id}:{user_id}`, TTL: 1h):
   - On hit: returns cached JSON array of fact dicts
   - On miss: queries PostgreSQL, populates cache, returns

3. **Prompt injection** — two points in the LangGraph:
   - **classify_node** (`nodes/classify.py:192`): When intent is `conversational` or `identity`, `user_memory` is appended to the system prompt for personalized greetings
   - **react_loop_node** (`nodes/react_loop.py:181`): For all ReAct iterations, `user_memory` is appended to the system prompt so the LLM knows the user's context

4. **Prompt format** (generated by `format_facts_for_prompt`):
   ```
   ## Memoria del usuario
   - Nombre: Carlos
   - Departamento: Legal
   - Prefiere respuestas en español
   - Área de interés: contratos laborales (inferido)
   ```

   Facts with confidence < 0.8 are tagged `(inferido)`. Max facts enforced by `USER_MEMORY_MAX_FACTS` (default: 50).

---

## Write Path

1. **Trigger**: After every Emma response (both non-streaming and streaming endpoints in `api/emma.py`), a fire-and-forget `asyncio.create_task()` calls `extract_and_save_facts()`

2. **Stage 1 — Regex extraction** (~1ms):
   Declarative patterns match explicit user statements:

   | Pattern | Category | Key | Example |
   |---------|----------|-----|---------|
   | `me llamo\|mi nombre es\|soy` | identity | name | "Me llamo Carlos" → Carlos |
   | `tengo N años` | identity | age | "Tengo 35 años" → 35 |
   | `trabajo en\|pertenezco a` | work | department | "Trabajo en Legal" → Legal |
   | `soy\|trabajo como\|mi cargo es` | work | role | "Soy abogado" → abogado |
   | `mi empresa es\|trabajo para` | work | company | "Trabajo para Acme" → Acme |
   | `prefiero respuestas en` | preference | language | "Prefiero respuestas en español" → español |
   | `prefiero respuestas breves` | preference | response_style | "Quiero respuestas técnicas" → técnicas |
   | `no me hables con` | preference | avoid_style | "No me hables con emojis" → emojis |
   | `llámame\|puedes llamarme` | identity | preferred_name | "Llámame Charly" → Charly |

3. **Forget patterns** — user can request deletion:

   | Pattern | Action |
   |---------|--------|
   | `olvida\|borra mi nombre` | Soft-delete `identity/name` |
   | `olvida todo lo que sabes\|borra mis datos` | Hard-delete ALL facts (GDPR) |

4. **Stage 2 — LLM extraction** (optional, ~200ms):
   - Enabled via `USER_MEMORY_LLM_EXTRACTION=true` (default: `false`)
   - Sends conversation to LLM with a structured prompt
   - Extracts inferred facts (confidence = 0.7, source = `inferred`)
   - Validates categories and sanitizes output

5. **UPSERT logic** (PostgreSQL):
   - `ON CONFLICT (tenant_id, user_id, category, fact_key) WHERE is_active = true`
   - Updates `fact_value`, keeps highest `confidence` via `GREATEST()`
   - `declared` source always takes precedence over `inferred`
   - After UPSERT, Redis cache is invalidated

6. **Max facts limit**: If user already has `USER_MEMORY_MAX_FACTS` (50) facts, new extractions are silently skipped

---

## Fact Categories

| Category | Purpose | Example Keys |
|----------|---------|--------------|
| `identity` | Who the user is | `name`, `preferred_name`, `age` |
| `work` | Professional context | `department`, `role`, `company` |
| `preference` | Communication preferences | `language`, `response_style`, `avoid_style` |
| `interest` | Areas of interest (usually inferred) | Topics detected by LLM |

---

## LangGraph Integration

The `user_memory` field flows through the ReAct graph at two critical points:

```
START → classify ─── fast-path (conversational/identity) ──→ END
           │              ↑ user_memory injected here
           │
           └── react_loop ⟲ → synthesize → END
                    ↑ user_memory injected here
```

### 1. State Initialization (`state.py:628-637`)

```python
# Load persistent user memory (cross-session facts)
user_memory = ""
if user_id:
    facts_service = get_user_facts_service()
    user_memory = await facts_service.format_facts_for_prompt(tenant_id, user_id)
```

### 2. Classify Fast-Path (`classify.py:62-63`)

For conversational intents (greetings, identity), the system prompt includes:
```python
if user_memory:
    system_msg += f"\n\n{user_memory}"
```

This enables proactive greetings like: "¡Hola, Carlos! ¿Cómo va todo en Legal?"

### 3. ReAct System Prompt (`react_loop.py:180-182`)

For all tool-assisted queries, facts are appended to the system prompt:
```python
user_memory = state.get("user_memory")
if user_memory:
    prompt += f"\n\n{user_memory}"
```

---

## API Endpoints

All endpoints are on the Emma Agent Service (port 8009), under `/emma/memory/facts`.

### GET `/emma/memory/facts` — List Facts

```bash
curl -s "http://localhost:8009/emma/memory/facts?user_id=USER_ID&tenant_id=TENANT_ID" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Response:
```json
{
  "facts": [
    {
      "id": "a1b2c3d4-...",
      "category": "identity",
      "fact_key": "name",
      "fact_value": "Carlos",
      "confidence": 1.0,
      "source": "declared"
    }
  ],
  "count": 1
}
```

### DELETE `/emma/memory/facts` — Clear All (GDPR)

```bash
curl -s -X DELETE "http://localhost:8009/emma/memory/facts?user_id=USER_ID&tenant_id=TENANT_ID" \
  -H "X-API-Key: $API_KEY"
```

Response:
```json
{"success": true, "deleted_count": 5, "message": "Cleared 5 facts"}
```

**Important**: This performs a **hard DELETE** (not soft-delete) for GDPR right-to-erasure compliance. All rows for the user are permanently removed from PostgreSQL.

### DELETE `/emma/memory/facts/{fact_id}` — Delete Single Fact

```bash
curl -s -X DELETE "http://localhost:8009/emma/memory/facts/a1b2c3d4-...?user_id=USER_ID&tenant_id=TENANT_ID" \
  -H "X-API-Key: $API_KEY"
```

This performs a **soft-delete** (`is_active = false`). The partial unique index allows a new fact with the same `(category, fact_key)` to be created later.

---

## GDPR Compliance

| Operation | Mechanism | Scope |
|-----------|-----------|-------|
| **Right to erasure** (Art. 17) | `DELETE /emma/memory/facts` | Hard DELETE — all rows permanently removed |
| **Right to rectification** (Art. 16) | User says "Me llamo María" | UPSERT overwrites previous `identity/name` |
| **Right to object** (Art. 21) | `USER_MEMORY_ENABLED=false` | Disables system entirely |
| **Data minimization** (Art. 5) | `USER_MEMORY_MAX_FACTS=50` | Caps stored facts per user |
| **Natural language deletion** | User says "Olvida todo lo que sabes" | Triggers `clear_user_facts()` (hard DELETE) |

### Soft vs Hard Delete

- **Single fact deletion** (`DELETE /facts/{id}`): **Soft-delete** (`is_active = false`). Row retained for audit trail. Fact no longer returned or injected into prompts.
- **Full user clear** (`DELETE /facts`): **Hard DELETE**. All rows physically removed. No trace remains. Used for GDPR erasure requests.
- **Natural language "olvida todo"**: Triggers **hard DELETE** via `clear_user_facts()`.
- **Natural language "olvida mi nombre"**: Triggers **soft-delete** of specific fact.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_MEMORY_ENABLED` | `true` | Master switch for user memory system |
| `USER_MEMORY_LLM_EXTRACTION` | `false` | Enable Stage 2 LLM-based fact extraction |
| `USER_MEMORY_MAX_FACTS` | `50` | Maximum active facts per user |
| `USER_MEMORY_CACHE_TTL` | `3600` | Redis cache TTL in seconds (1 hour) |

All variables are defined in `emma-agent-service/app/core/config.py` (lines 267-270).

---

## Proactive Greetings

When a user greets Emma (e.g., "Hola"), the classify node detects `conversational` intent and generates a personalized response using the user's facts:

**Without memory**: "¡Hola! Soy Emma, tu asistente documental. ¿En qué te ayudo?"

**With memory**: "¡Hola, Carlos! ¿Cómo va todo en Legal? ¿En qué te ayudo hoy?"

The system prompt instructs the LLM to use memory **proactively but naturally** — not to recite all stored facts, but to weave relevant ones into the greeting.

---

## File Locations

| File | Path (relative to `backend/`) | Purpose |
|------|-------------------------------|---------|
| DB Model | `app/db/emma_memory_models.py` | SQLAlchemy `EmmaUserMemoryFact` model |
| Migration | `alembic/versions/d4e5f6g7h8i9_add_user_memory_facts.py` | Table + indexes creation |
| UserFactsService | `microservices/emma-agent-service/app/services/memory/user_facts.py` | CRUD + cache singleton |
| FactExtractor | `microservices/emma-agent-service/app/services/memory/fact_extractor.py` | Regex + LLM extraction |
| MemoryService | `microservices/emma-agent-service/app/services/memory/service.py` | Unified memory interface |
| Memory `__init__` | `microservices/emma-agent-service/app/services/memory/__init__.py` | Public exports |
| Config | `microservices/emma-agent-service/app/core/config.py` | `user_memory_*` settings |
| API Endpoints | `microservices/emma-agent-service/app/api/emma.py` | GET/DELETE `/emma/memory/facts` |
| ReActState | `microservices/emma-agent-service/app/agents/langgraph/state.py` | `user_memory` field + load in `create_initial_react_state()` |
| Classify Node | `microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py` | Fast-path injection |
| React Loop | `microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py` | System prompt injection |

---

## Verification

Manual test steps to verify the system end-to-end:

### 1. Send a greeting with identity

```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)

curl -s -X POST "http://localhost:8009/emma/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "Hola, me llamo Carlos y trabajo en el departamento Legal",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "user_id": "test-user-1"
  }' > /tmp/response.json

python3 -c "import json; r=json.load(open('/tmp/response.json')); print(r['answer'])"
```

### 2. Verify facts were extracted

```bash
curl -s "http://localhost:8009/emma/memory/facts?user_id=test-user-1&tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY" > /tmp/facts.json

python3 -c "import json; facts=json.load(open('/tmp/facts.json')); print(json.dumps(facts, indent=2))"
```

Expected: facts with `identity/name=Carlos` and `work/department=Legal`.

### 3. Verify proactive greeting

```bash
curl -s -X POST "http://localhost:8009/emma/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "Hola",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "user_id": "test-user-1"
  }' > /tmp/response2.json

python3 -c "import json; r=json.load(open('/tmp/response2.json')); print(r['answer'])"
```

Expected: Response mentions "Carlos" and/or "Legal" proactively.

### 4. Test GDPR deletion

```bash
curl -s -X DELETE "http://localhost:8009/emma/memory/facts?user_id=test-user-1&tenant_id=00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY"
```

Expected: `{"success": true, "deleted_count": 2, "message": "Cleared 2 facts"}`

---

## Related Documentation

- [Emma Reactive](EMMA_REACTIVE.md) — Event-driven proactive system (heartbeat insights)
- [Prompt Management](PROMPT_MANAGEMENT.md) — Dynamic prompt injection and Langfuse integration
- [RAG Caching](RAG_CACHING.md) — Multi-tier caching architecture (User Memory uses its own Redis cache layer)
