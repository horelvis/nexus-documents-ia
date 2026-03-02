# Changelog 2026-02-04: Web Search + LLM Quality Improvements

## Resumen

Mejoras en la calidad de respuestas del Social Agent y migración a Tavily para búsquedas web.

---

## 1. Web Search: Migración de DuckDuckGo a Tavily

### Problema
DuckDuckGo devolvía resultados irrelevantes (artículos de Dell para consultas del tiempo).

### Solución
Implementado **Tavily como motor principal** con DuckDuckGo como fallback.

### Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `emma-agent-service/app/services/web_search.py` | Nueva arquitectura con providers |
| `emma-agent-service/app/core/config.py` | Añadido `tavily_api_key` |
| `emma-agent-service/requirements.txt` | Añadido `tavily-python>=0.5.0` |
| `docker/docker-compose.onpremise.yml` | Variable `TAVILY_API_KEY` |
| `docker/.env` | API key de Tavily |

### Configuración

```bash
# .env
TAVILY_API_KEY=tvly-dev-xxxxxxxx  # Get from https://tavily.com
```

### Arquitectura

```
WebSearchClient
├── TavilySearchProvider (primary)
│   └── 1000 free searches/month
│   └── Optimized for LLM/RAG
└── DuckDuckGoSearchProvider (fallback)
    └── No API key required
    └── Lower quality
```

---

## 2. LLM: Migración de AWQ a FP16

### Problema
Qwen 2.5 7B-AWQ (4-bit quantized) ocasionalmente mezclaba idiomas (chino, coreano) en respuestas.

### Solución
Migración a **Qwen 2.5 7B FP16** (sin cuantización) para máxima calidad.

### Comparativa

| Métrica | AWQ (antes) | FP16 (ahora) |
|---------|-------------|--------------|
| VRAM | ~6GB | ~14GB |
| Calidad | 85-90% | 100% |
| Mezcla idiomas | Ocasional | Ninguna |
| Latencia | ~500ms | ~1000ms |

### Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `docker/docker-compose.onpremise.yml` | Modelo FP16, GPU util 85% |
| `docker/.env` | `VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct` |

### Configuración vLLM

```yaml
# docker-compose.onpremise.yml
vllm:
  command:
    - "--model"
    - "Qwen/Qwen2.5-7B-Instruct"  # FP16, no AWQ
    - "--dtype"
    - "float16"
    - "--gpu-memory-utilization"
    - "0.85"  # Increased from 0.65
    # Removed: --quantization awq
```

### Requisitos VRAM

```
Modelo FP16:     ~14GB
Embedding BGE:   ~2GB
KV Cache:        ~4-6GB
─────────────────────
Total:           ~20-22GB (requires 24GB GPU)
```

---

## 3. Tests de Modelos via OpenRouter

### Scripts Creados

| Script | Propósito |
|--------|-----------|
| `scripts/test_models_openrouter.py` | Test básico de modelos |
| `scripts/test_models_openrouter_v2.py` | Test comprehensivo (5 categorías) |
| `scripts/test_quantization_comparison.py` | Comparación AWQ vs FP16 |

### Resultados del Test Comprehensivo

| Modelo | Social | Tools | Thinking | Legal Gen | RAG | Total |
|--------|--------|-------|----------|-----------|-----|-------|
| **Qwen 2.5 7B** | 100% | 100% | 100% | 92% | 100% | **98%** |
| Qwen3 8B | 75% | 100% | 35% | 62% | 100% | 74% |
| LLaMA 3.1 8B | 100% | 67% | 100% | 49% | 100% | 83% |
| Gemma 2 9B | 100% | 0% | 78% | 92% | 100% | 74% |
| Mistral 7B | 75% | 0% | 100% | 83% | 100% | 72% |

### Conclusiones

1. **Qwen 2.5 supera a Qwen3** para este caso de uso (legal + social en español)
2. **Qwen3 falla en Thinking** (35%) - no usa bien el modo `<think>`
3. **Mistral y Gemma no soportan Tool Calling** via OpenRouter
4. **FP16 elimina el language mixing** que ocurría con AWQ

---

## 4. Ubicación por Defecto

### Cambio
Actualizada ubicación de Madrid a Molina de Segura, Murcia.

### Configuración

```bash
# .env
DEFAULT_LOCATION_CITY=Molina de Segura
DEFAULT_LOCATION_REGION=Región de Murcia
DEFAULT_LOCATION_COUNTRY=España
DEFAULT_LOCATION_TIMEZONE=Europe/Madrid
```

---

## 5. Verificación

### Test del Social Agent

```bash
# Via Emma API
curl -X POST "http://localhost:8009/emma/query" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "query": "¿Qué tiempo hace hoy?",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "context": {"social_channel_mode": true}
  }'

# Respuesta esperada:
# "Hoy en Molina de Segura, la temperatura máxima será alrededor de 15°C
#  con viento de 16 km/h. ☀️🌡️"
```

### Logs a Verificar

```bash
# Tavily funcionando
docker compose logs emma-agent-service | grep "Tavily search"
# → "🔍 Tavily search: '...' → 3 results"

# Modelo FP16 cargado
docker compose logs vllm | grep "Model loading"
# → "Model loading took 14.2488 GiB"
```

---

## Rollback

Si necesitas volver a AWQ:

```bash
# .env
VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ

# docker-compose.onpremise.yml - añadir:
- "--quantization"
- "awq"

# Cambiar gpu-memory-utilization a 0.65

docker compose up -d vllm emma-agent-service
```

---

## 6. Social Agent: Respuestas Completas (Fix)

### Problema
Emma respondía "Voy a buscar los contratos que expiran pronto..." pero no proporcionaba detalles cuando el usuario pedía "más información". El prompt tenía una regla de brevedad excesiva: "1-2 oraciones máximo".

### Solución
Eliminada restricción de brevedad. El Social Agent ahora:
- Mantiene tono amigable y conversacional
- Proporciona respuestas detalladas cuando se solicitan
- Adapta la longitud según el tipo de consulta

### Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `emma-agent-service/app/agents/langgraph/nodes/specialists/social.py` | Prompt sin límite de oraciones, `quick_document_search` (ahora `smart_search`) con detalles completos |

### Antes vs Después

**Antes (limitado):**
```
Usuario: "Dame más información de los contratos que expiran"
Emma: "Voy a buscar los contratos que expiran pronto. 📄"
```

**Después (completo):**
```
Usuario: "Dame más información de los contratos que expiran"
Emma: "He encontrado 3 contratos próximos a expirar:

📄 **Contrato de Mantenimiento - ACME Corp**
   - Vencimiento: 15 marzo 2026
   - Tipo: Servicio

📄 **Acuerdo de Confidencialidad - TechSolutions**
   - Vencimiento: 22 marzo 2026
   - Extracto: Este acuerdo establece las obligaciones...

¿Necesitas que profundice en alguno de ellos?"
```

---

## 7. Apache AGE: Fix Query Aggregation (Bug Fix)

### Problema
Error en consulta Cypher que cuenta documentos por carpeta:
```
ERROR: could not find rte for doc_count at character 413
```

### Causa
Apache AGE no permite usar aliases de agregaciones (`count(d) as doc_count`) directamente en `ORDER BY`.

### Solución
Usar `WITH` para materializar la agregación antes del `RETURN`:

```cypher
-- Antes (error):
RETURN f.name as name, count(d) as doc_count
ORDER BY doc_count DESC

-- Después (correcto):
WITH f.name as name, count(d) as doc_count
RETURN name, doc_count
ORDER BY doc_count DESC
```

### Archivo Modificado
`knowledge-tree-service/app/services/tenant_knowledge_service.py` - Función `get_top_folders()`

---

## 8. Memoria de Conversación en Canales (Critical Fix)

### Problema
Emma no mantenía el contexto de conversación en Slack/Telegram. Cada mensaje generaba un nuevo `session_id` aleatorio:

```python
# ANTES (bug):
session_id = f"bg-{uuid.uuid4().hex[:12]}"  # Nuevo ID cada vez!
```

### Solución
Session_id **determinístico** basado en el canal y thread:

```python
# DESPUÉS (fix):
# Slack: slack:{channel_id}:{thread_ts}:{user_id}
# Telegram: telegram:{chat_id}:{user_id}
session_id = ":".join([channel_type, channel_id, thread_or_chat, user_id])
```

### Archivos Modificados

| Archivo | Cambio |
|---------|--------|
| `channels/slack_channel.py` | Añadido `thread_ts` al parsed output |
| `services/channel_router.py` | Genera session_id determinístico |
| `services/emma_background_service.py` | Acepta session_id externo |

### Flujo de Memoria

```
Slack Message → channel_router builds session_id
                          ↓
              emma_background_service.channel_query(session_id=...)
                          ↓
              emma_service.execute_query()
                          ↓
    ┌─────────────────────┴─────────────────────┐
    ↓                                           ↓
memory.get_conversation_history()     memory.add_exchange()
    (carga historial de Redis)        (guarda en Redis, TTL 30min)
```

### Verificación

```bash
# Logs mostrarán session_id determinístico:
docker compose logs emma-agent-service | grep "Session ID"
# → "📝 Session ID for conversation memory: slack:C123456:1738657200.123:user123"
# → "🧠 Executing Emma with session_id: slack:C123456:1738657200.123:user123"
```

---

## Próximos Pasos

1. [ ] Monitorear estabilidad del FP16 en producción
2. [ ] Evaluar Qwen 2.5 14B si se necesita más calidad
3. [ ] Configurar alertas para uso de VRAM
4. [x] ~~Fix Social Agent para respuestas detalladas~~
5. [x] ~~Fix Apache AGE aggregation query~~
6. [x] ~~Fix memoria de conversación en canales~~
7. [x] ~~Fix respuesta a hilos de Slack sin mención~~
