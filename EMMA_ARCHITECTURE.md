# Emma AI: Arquitectura y Documentacion Tecnica

## Introduccion

**Emma** es el asistente de IA inteligente de NexusDocs360, construido sobre **Microsoft Agent Framework** con **vLLM** (Qwen3-14B) como motor de inferencia principal.

> **Estado actual**: EmmaCoordinator es el unico path de ejecucion activo. Los flujos legacy (AutoGen, EmmaHandoffWorkflow) estan deprecated.

---

## Arquitectura General

```
                              FRONTEND (Next.js)
+-----------------------------------------------------------------------------+
|  /[tenantId]/chat/page.tsx                                                  |
|       |                                                                      |
|       v                                                                      |
|  EmmaChat.tsx -----> EmmaQueryInput.tsx                                     |
|       |                    |                                                 |
|       v                    v                                                 |
|  emma.service.ts <---------+                                                |
|       |                                                                      |
|       |  queryEmmaStream() --> POST /api/v1/weaviate/emma/query/stream      |
+-------|------------------------------ SSE Stream ---------------------------+
        |
        v
                              BACKEND GATEWAY (FastAPI - port 8000)
+-----------------------------------------------------------------------------+
|  backend/app/api/v1/weaviate.py                                             |
|       |                                                                      |
|       |  Inject tenant_id from Clerk JWT                                    |
|       |  Proxy to Weaviate microservice (timeout: 180s)                     |
|       v                                                                      |
|  httpx.AsyncClient --> http://weaviate-service:8007/emma/query/stream       |
+-------|------------------------------ HTTP ----------------------------------+
        |
        v
                              WEAVIATE MICROSERVICE (FastAPI - port 8007)
+-----------------------------------------------------------------------------+
|  backend/microservices/weaviate-service/app/api/emma.py                     |
|       |                                                                      |
|       v                                                                      |
|  EmmaService.execute_query_stream()                                         |
|       |                                                                      |
|       +---> MemoryService (load conversation history)                       |
|       |     Key: emma:conv:{tenant}:{session}                               |
|       |     Returns: Last 10 messages                                       |
|       |                                                                      |
|       +---> EmmaCoordinator.execute() [PRIMARY]                             |
|             |                                                                |
|             +---> SemanticPatternRouter (classify intent ~10ms)             |
|             |                                                                |
|             +---> AgentThread (context management)                          |
|             |                                                                |
|             +---> Subagents via .as_tool()                                  |
|                   +-- SearchAgent                                           |
|                   +-- ContractAgent                                         |
|                   +-- ComplianceAgent                                       |
|                   +-- LaborAgent                                            |
|                   +-- FiscalAgent                                           |
|                   +-- PrivacyAgent                                          |
|                   +-- AnalystAgent                                          |
|                   +-- SummarizerAgent                                       |
|                                                                              |
|       +---> MemoryService (store conversation)                              |
+-----------------------------------------------------------------------------+
```

---

## Sistema de Memoria (3 capas)

### Arquitectura

```
+----------------------------------------------------------------+
|                    MEMORY SERVICE (Unified)                     |
+----------------------------------------------------------------+
|                                                                  |
|   +---------------------+    +-----------------------------+    |
|   | ConversationMemory  |    |     PreferencesStore        |    |
|   |     (Redis)         |    |        (Redis)              |    |
|   +---------------------+    +-----------------------------+    |
|   | Key: emma:conv:     |    | Key: emma:prefs:            |    |
|   |   {tenant}:{session}|    |   {tenant}:{user}           |    |
|   |                     |    |                             |    |
|   | TTL: 30 min         |    | TTL: Persistent             |    |
|   | Max: 100 messages   |    |                             |    |
|   | Max: 32K tokens     |    | Fields:                     |    |
|   |                     |    | - display_name              |    |
|   | Stores:             |    | - preferred_language        |    |
|   | - Message history   |    | - response_style            |    |
|   | - Active documents  |    | - expertise_level           |    |
|   | - Tool results      |    | - frequent_queries          |    |
|   |                     |    | - frequent_documents        |    |
|   +---------------------+    +-----------------------------+    |
+----------------------------------------------------------------+
```

### Limites de Memoria (P7 Fix)

| Limite | Valor | Proposito |
|--------|-------|-----------|
| MAX_MESSAGES | 100 | Mensajes por sesion |
| MAX_TOKENS | 32,000 | Tokens totales (~128KB) |
| MAX_MESSAGE_LENGTH | 8,000 chars | Por mensaje individual |

### Archivos Clave

- `app/services/memory/service.py` - MemoryService unificado
- `app/services/memory/conversation.py` - ConversationMemory (Redis)
- `app/services/memory/preferences.py` - PreferencesStore (Redis)
- `app/services/memory/types.py` - Message, ConversationContext, UserPreferences

---

## EmmaCoordinator (Orquestador Principal)

### Patrones de Orquestacion

| Patron | Descripcion | Casos de Uso |
|--------|-------------|--------------|
| **HANDOFF** | LLM decide delegacion via `.as_tool()` | Default, queries conversacionales |
| **SEQUENTIAL** | Pipeline A->B->C | "Busca, analiza, resume" |
| **CONCURRENT** | Paralelo A\|B\|C | "Desde perspectiva legal, fiscal y laboral" |

### Flujo de Ejecucion

```python
# 1. Deteccion de patron (SemanticRouter, ~10ms)
pattern = await detect_orchestration_pattern(query)

# 2. Load/Create AgentThread (Redis persistence)
thread = await self._load_or_create_thread(tenant_id, session_id)

# 3. Emma ChatAgent.run() con subagents como tools
#    Emma ve 8 tools disponibles y decide cuales invocar
result = await self._emma.run(query, thread)

# 4. Clean thinking tags (Qwen3)
answer = clean_thinking_tags(result.text)

# 5. Save thread state
await self._save_thread(thread)
```

### Archivo Principal

`backend/microservices/weaviate-service/app/agents/emma_coordinator.py`

---

## SemanticRouter (Clasificacion de Intenciones)

### SemanticPatternRouter

Clasifica queries en ~10ms usando embeddings locales:

```python
# Modelo: sentence-transformers/all-MiniLM-L6-v2
# Latencia: ~10ms por clasificacion

Routes definidas:
- conversational: Saludos, agradecimientos, identidad
- sequential: "Primero..., despues..."
- concurrent: "Desde perspectiva legal, fiscal y laboral"
```

### SemanticDomainRouter

Clasifica queries por dominio legal:

| Dominio | Agente | Keywords |
|---------|--------|----------|
| contract | ContractAgent | contrato, clausula, terminos |
| labor | LaborAgent | despido, nomina, convenio |
| fiscal | FiscalAgent | impuesto, IVA, IRPF |
| compliance | ComplianceAgent | GDPR, RGPD, cumplimiento |
| privacy | PrivacyAgent | LOPDGDD, datos personales |
| search | SearchAgent | busca, encuentra, documentos |
| summary | SummarizerAgent | resume, sintetiza |
| general | AnalystAgent | analiza, evalua, examina |

### Archivo

`backend/microservices/weaviate-service/app/agents/orchestration/router.py`

---

## Agentes Especializados (8)

### Core Agents

| Agente | Proposito | Temperature |
|--------|-----------|-------------|
| **SearchAgent** | Busqueda de documentos | 0.2 |
| **AnalystAgent** | Analisis profundo | 0.2 |
| **ContractAgent** | Contratos, clausulas | 0.1 |
| **ComplianceAgent** | GDPR/RGPD | 0.1 |
| **SummarizerAgent** | Resumenes ejecutivos | 0.3 |

### Legal Domain Agents

| Agente | Dominio | Legislacion |
|--------|---------|-------------|
| **LaborAgent** | Derecho laboral | Estatuto de los Trabajadores |
| **FiscalAgent** | Fiscal | Ley General Tributaria |
| **PrivacyAgent** | Proteccion datos | LOPDGDD |

### Archivo

`backend/microservices/weaviate-service/app/agents/agents/`

---

## Channel Tools (Busqueda en Canales)

### Herramientas Disponibles

| Tool | Fuente | Filtro Privacidad |
|------|--------|-------------------|
| `search_emails` | Gmail indexado | user_id (siempre) |
| `search_drive` | Google Drive indexado | user_id (por defecto) |
| `search_channel` | Cualquier canal | user_id (canales personales) |

### Privacidad Intra-Tenant (P6 Fix)

Los emails y archivos de Drive se filtran por `user_id` para evitar que usuarios del mismo tenant vean contenido de otros:

```python
# PRIVACY: Emails son contenido personal - siempre filtrar por user_id
if context.user_id:
    filters["user_id"] = context.user_id
```

### Archivo

`backend/microservices/weaviate-service/app/tools/channel_tools.py`

---

## RAG Pipeline (7 capas)

```
Layer 0: Document Processing (chunking)
Layer 1: Semantic Chunking (structure-aware)
Layer 2: Query Intelligence <-- Expansion, intent classification
Layer 3: Hybrid Retrieval + RRF <-- Dense + Sparse fusion
Layer 4: Context Assembly <-- Token management
Layer 5: Validated Generation <-- LLM + semantic validation
Layer 6: Semantic Cache <-- Redis (~90% latency reduction)
```

---

## Configuracion

### Variables de Entorno

```bash
# vLLM (Primary LLM)
VLLM_ENABLED=true
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_MODEL=Qwen/Qwen3-14B
VLLM_MAX_MODEL_LEN=32768

# Redis (Memory + Context)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Weaviate (Vector DB)
WEAVIATE_URL=http://weaviate:8080

# Agents
AGENTS_ENABLED=true
```

### Timeouts Unificados (P5 Fix)

| Capa | Timeout | Archivo |
|------|---------|---------|
| Frontend | 180s | `frontend/src/lib/config.ts` |
| Gateway | 180s | `backend/app/api/v1/weaviate.py` |
| Coordinator | 300s | `emma_coordinator.py` |

---

## Redis Connection Pool (P9 Fix)

```python
# Shared connection pool (singleton)
_redis_pool = ConnectionPool(
    host=agent_config.redis_host,
    port=agent_config.redis_port,
    max_connections=20,
    socket_timeout=5.0,
)

# Usage in EmmaCoordinator
pool = get_redis_pool()
self._redis = redis.Redis(connection_pool=pool)
```

---

## Utilidades

### clean_thinking_tags() (P11 Fix)

Qwen3 usa `<think>...</think>` tags para chain-of-thought. Esta funcion los elimina:

```python
def clean_thinking_tags(text: str) -> str:
    """Remove Qwen3 thinking tags from LLM output."""
    if "</think>" in text:
        return text.split("</think>")[-1].strip()
    return text
```

---

## Archivos Criticos

### Frontend

| Archivo | Proposito |
|---------|-----------|
| `frontend/src/app/(main)/[tenantId]/chat/page.tsx` | Pagina de chat |
| `frontend/src/components/emma-chat/EmmaChat.tsx` | Componente principal |
| `frontend/src/lib/services/emma.service.ts` | Cliente API |
| `frontend/src/hooks/use-agent-chat.ts` | Hook de chat |

### Backend Gateway

| Archivo | Proposito |
|---------|-----------|
| `backend/app/api/v1/weaviate.py` | Proxy a microservicio |

### Weaviate Microservice

| Archivo | Proposito |
|---------|-----------|
| `app/api/emma.py` | Endpoints Emma |
| `app/services/emma_service.py` | Servicio principal |
| `app/agents/emma_coordinator.py` | Orquestador principal |
| `app/agents/orchestration/router.py` | Semantic Router |
| `app/services/memory/service.py` | Memoria unificada |
| `app/services/memory/conversation.py` | Memoria conversacional |
| `app/tools/channel_tools.py` | Herramientas de canales |

---

## Desarrollo Local

```bash
# Iniciar servicios backend
cd backend/docker && ./start-dev.sh

# Verificar Emma service
curl -H "Authorization: Bearer ${MICROSERVICES_API_KEY}" \
     http://localhost:8007/emma/health

# Ver logs de Emma
docker logs docker-weaviate-service-1 --tail 100 -f
```

---

## Flujo Completo de Ejecucion

### Ejemplo: "Que riesgos tiene este contrato?"

```
1. FRONTEND
   +-> User types query in EmmaQueryInput
   +-> EmmaChat.handleSendQuery() called
   +-> emma.service.queryEmmaStream()
       POST /api/v1/weaviate/emma/query/stream
       Body: { query, session_id, tenant_id, context: { user_id, user_name } }

2. BACKEND GATEWAY (weaviate.py)
   +-> Validates Clerk JWT
   +-> Injects tenant_id from claims
   +-> Proxies to Weaviate microservice (timeout: 180s)

3. WEAVIATE SERVICE (emma.py)
   +-> EmmaService.execute_query_stream()
       |
       +-> Load conversation history (MemoryService)
       |   Key: emma:conv:{tenant}:{session}
       |   Returns: Last 10 messages
       |
       +-> Enrich user context (name, email, role, preferences)
       |
       +-> EmmaCoordinator.execute()
           |
           +-> Pattern Detection (SemanticRouter)
           |   Query: "riesgos" + "contrato"
           |   -> HANDOFF pattern (default)
           |
           +-> Load/Create AgentThread
           |   Key: emma:coordinator:thread:{tenant}:{session}
           |
           +-> Build context-aware query
           |   "[Tenant: xxx] [User: Juan, Abogado]
           |    Que riesgos tiene este contrato?"
           |
           +-> Emma ChatAgent.run(query, thread)
           |   |
           |   |  Emma sees 8 tools available:
           |   |  - search_agent, contract_agent, compliance_agent...
           |   |
           |   |  Emma decides to call:
           |   |  1. contract_agent.as_tool() -> Analyze contract clauses
           |   |  2. compliance_agent.as_tool() -> Check GDPR compliance
           |   |
           |   +-> Synthesize final answer
           |
           +-> clean_thinking_tags(answer)
           |
           +-> Save AgentThread to Redis
           |
           +-> Return EmmaCoordinatorResult
               - answer: "He identificado 3 riesgos principales..."
               - agents_delegated: ["contract_agent", "compliance_agent"]
               - confidence_score: 0.92

4. STREAMING EVENTS (SSE)
   +-> event: start
   +-> event: delegation { agent: "contract_agent" }
   +-> event: delegation { agent: "compliance_agent" }
   +-> event: token { text: "He identificado..." }
   +-> event: complete { answer, tools_used, confidence }

5. MEMORY STORAGE
   +-> MemoryService.add_exchange()
       - Store user message
       - Store assistant response
       - Store tools_used metadata
       - Apply token limits (truncate if needed)
```

---

## Cambios Recientes (Diciembre 2024)

### Fixes Implementados

| ID | Problema | Solucion |
|----|----------|----------|
| P2 | Fallback handoff pierde contexto | Eliminado, solo EmmaCoordinator |
| P5 | Timeout gateway < frontend | 120s -> 180s |
| P6 | Sin filtro user_id en channels | Agregado para privacidad |
| P7 | Sin limite de tokens en memoria | MAX_TOKENS=32000 |
| P9 | Redis sin connection pool | ConnectionPool compartido |
| P11 | Thinking tags duplicados | clean_thinking_tags() centralizado |

### Componentes Deprecated

- `EmmaHandoffWorkflow` - Mantenido para referencia, NO usado
- `AutoGen Orchestrator` - Completamente removido
- Path de fallback en `EmmaService` - Eliminado

---

*Documento actualizado - Diciembre 2024*
*Arquitectura: EmmaCoordinator + Microsoft Agent Framework + vLLM (Qwen3-14B)*
