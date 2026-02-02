# Informe de Benchmark RAG — NouxCubeIA Emma

**Fecha**: 2 de febrero de 2026
**Modelos evaluados**:
- `horelvis/boe-legal-qwen-7b-awq` — Fine-tuned BOE legal, AWQ 4-bit (~4GB VRAM), vLLM v0.8.5.post1 local
- `qwen/qwen-2.5-7b-instruct` — Modelo base sin fine-tune, vía OpenRouter API
**Evaluador**: Keyword Recall (sin LLM-as-judge)
**Preguntas**: 15 preguntas de dominio legal español (6 dominios)

---

## 1. Resumen Ejecutivo

Se identificó y corrigió un defecto crítico en el pipeline RAG que causaba una **degradación del -40%** en la calidad de respuestas respecto al modelo directo. Tras el fix, el RAG **mejora al modelo en un +12%**.

Además, se comparó el modelo fine-tuneado contra el modelo base Qwen2.5-7B sin fine-tuning vía OpenRouter, revelando que **el fine-tuning no mejora el keyword recall** (-7%).

### Tabla comparativa de los 4 escenarios

| Escenario | Keyword Recall | Latencia p50 | Latencia p90 | Δ vs Base |
|---|---|---|---|---|
| **Qwen2.5-7B base** (OpenRouter) | 0.457 | 5,531 ms | 18,891 ms | — |
| **boe-legal-qwen-7b-awq** (vLLM local) | 0.427 | 407 ms | 1,136 ms | -7% |
| **RAG + AWQ** (antes del fix) | 0.241 | ~2,100 ms | ~3,500 ms | -47% |
| **RAG + AWQ** (después del fix) | **0.479** | 9,741 ms | 13,761 ms | **+5%** |

---

## 2. Causa Raíz Identificada: Tool Call Contamination

### Problema

El nodo `general_agent` del pipeline RAG pasaba 4 herramientas (`structural_query`, `document_search`, `document_summary`, `web_search`) al LLM en todas las consultas, incluso las de conocimiento público legal.

El prompt del sistema incluía la directiva:
> "Para preguntas de CONTEO o LISTADO, usa SIEMPRE `structural_query` primero"

El modelo 7B AWQ, al recibir herramientas + esta instrucción, interpretaba preguntas legales (ej. "¿Cuáles son las causas de despido disciplinario?") como "listados" y generaba tokens `<tool_call>` **como texto plano** en vez de responder directamente:

```
<tool_call>{"name": "structural_query", "arguments": {"query": "causas despido disciplinario"}}</tool_call>
<tool_call>{"name": "structural_query", "arguments": {"query": "causas despido disciplinario"}}</tool_call>
<tool_call>{"name": "structural_query", "arguments": {"query": "causas despido disciplinario"}}</tool_call>
<tool_call>{"name": "structural_query", "arguments": {"query": "causas despido disciplinario"}}</tool_call>
Fuentes:
```

Esta salida basura se propagaba al nodo `synthesize`, que intentaba sintetizar texto sin contenido útil.

### Flujo del Bug

```
query → retrieve (5 docs ✓) → graph_expand (2 conceptos ✓)
    → specialist/general_agent:
        ├─ Recibe tools=[structural_query, document_search, document_summary, web_search]
        ├─ Prompt: "usa SIEMPRE structural_query para LISTADO"
        ├─ Modelo genera <tool_call> como TEXTO (no como API tool_call)
        └─ Output: basura de tool_calls repetidos (~30 seg desperdiciados)
    → synthesize: recibe basura, genera respuesta inútil
```

### Archivo Afectado

**`emma-agent-service/app/agents/langgraph/nodes/specialists/general.py:774`**

### Fix Aplicado

```python
# ANTES (causaba tool call contamination):
return await create_specialist_node(
    agent_name="general_agent",
    system_prompt=GENERAL_SYSTEM_PROMPT,
    tools=general_tools,       # ← 4 herramientas confundían al modelo 7B
    state=state,
)

# DESPUÉS (fix):
return await create_specialist_node(
    agent_name="general_agent",
    system_prompt=GENERAL_SYSTEM_PROMPT,
    tools=[],                  # ← Sin herramientas para consultas de conocimiento
    state=state,
)
```

**Lógica**: Cuando la consulta llega a esta línea, ya se descartaron los 3 short-circuits (structural_query, document_id, uploaded_texts). Es una consulta de conocimiento público — el modelo debe responder usando su conocimiento paramétrico + el contexto de documentos recuperados por el pipeline RAG, sin necesidad de herramientas adicionales.

`base.py:190` ya maneja `tools=[]` correctamente: `tool_schemas = [...] if tools else None` → pasa `None` al LLM.

---

## 3. Resultados Detallados por Pregunta

### 3.1 Comparativa Modelo vs RAG (post-fix)

| # | Dominio | Pregunta | Modelo | RAG | Δ |
|---|---|---|---|---|---|
| 1 | labor | Causas despido disciplinario | 0.50 | 0.33 | -34% |
| 2 | labor | Indemnización despido improcedente | 0.00 | **0.33** | +∞ |
| 3 | labor | Periodo de prueba | 0.25 | **0.75** | **+200%** |
| 4 | labor | Requisitos ERE | 0.00 | 0.00 | = |
| 5 | fiscal | Tramos IRPF | 0.17 | 0.17 | = |
| 6 | fiscal | Tipos de IVA | 0.75 | **1.00** | **+33%** |
| 7 | fiscal | Impuesto Sociedades | 0.67 | 0.33 | -50% |
| 8 | contract | Duración alquiler vivienda | 0.50 | 0.25 | -50% |
| 9 | contract | Fianza alquiler | 0.67 | 0.67 | = |
| 10 | privacy | Derechos RGPD | 1.00 | **1.00** | = |
| 11 | privacy | DPO obligatorio | 0.40 | 0.20 | -50% |
| 12 | compliance | Compliance penal | 0.00 | 0.00 | = |
| 13 | civil | Recurso contencioso | 0.50 | **0.75** | **+50%** |
| 14 | civil | Prescripción delitos | 0.60 | 0.60 | = |
| 15 | contract | Constitución SL | 0.40 | **0.80** | **+100%** |
| | | **PROMEDIO** | **0.427** | **0.479** | **+12%** |

### 3.2 Análisis por Dominio

| Dominio | Modelo (avg) | RAG (avg) | Δ | Preguntas |
|---|---|---|---|---|
| labor | 0.188 | 0.353 | **+88%** | 4 |
| fiscal | 0.529 | 0.500 | -5% | 3 |
| contract | 0.523 | 0.573 | **+10%** | 3 |
| privacy | 0.700 | 0.600 | -14% | 2 |
| compliance | 0.000 | 0.000 | = | 1 |
| civil | 0.550 | 0.675 | **+23%** | 2 |

### 3.3 Victorias Destacadas del RAG

| Pregunta | Modelo | RAG | Por qué mejoró |
|---|---|---|---|
| **Periodo de prueba** | 0.25 | 0.75 | RAG recuperó el ET art. 14 con datos exactos (6 meses técnicos, 2 meses resto) |
| **Constitución SL** | 0.40 | 0.80 | RAG inyectó la Ley de Sociedades de Capital con capital mínimo 3.000€ |
| **Recurso contencioso** | 0.50 | 0.75 | RAG recuperó la Ley 39/2015 con plazos y silencio administrativo |
| **Tipos de IVA** | 0.75 | 1.00 | RAG completó con los 3 tipos (general/reducido/superreducido) |

### 3.4 Debilidades Observadas

| Pregunta | Modelo | RAG | Problema |
|---|---|---|---|
| **Despido disciplinario** | 0.50 | 0.33 | RAG generó lista repetitiva (25 items, los últimos idénticos) — modelo entra en loop de generación |
| **DPO obligatorio** | 0.40 | 0.20 | RAG citó la LOPDGDD pero con contenido repetitivo y sin mencionar "gran escala" |
| **Impuesto Sociedades** | 0.67 | 0.33 | RAG omitió el tipo reducido del 15% para empresas nuevas |
| **Duración alquiler** | 0.50 | 0.25 | RAG respondió "1 año" (incorrecto), el modelo respondió "5 años" (correcto) |

---

## 4. Comparativa: Modelo Fine-tuned vs Base (sin fine-tune)

Se ejecutó el modelo base `qwen/qwen-2.5-7b-instruct` (sin fine-tuning para dominio legal) vía [OpenRouter](https://openrouter.ai/qwen/qwen-2.5-7b-instruct) para evaluar el impacto real del fine-tuning.

### 4.1 Resultados por Pregunta: Base vs Fine-tuned

| # | Dominio | Pregunta | Base (Qwen2.5) | Fine-tuned (AWQ) | Δ |
|---|---|---|---|---|---|
| 1 | labor | Despido disciplinario | 0.33 | 0.50 | +50% FT |
| 2 | labor | Indemnización despido | **0.33** | 0.00 | Base gana |
| 3 | labor | Periodo de prueba | 0.25 | 0.25 | = |
| 4 | labor | Requisitos ERE | **0.50** | 0.00 | Base gana |
| 5 | fiscal | Tramos IRPF | **0.50** | 0.17 | Base gana |
| 6 | fiscal | Tipos de IVA | 0.50 | **0.75** | FT gana |
| 7 | fiscal | Impuesto Sociedades | 0.67 | 0.67 | = |
| 8 | contract | Duración alquiler | 0.00 | **0.50** | FT gana |
| 9 | contract | Fianza alquiler | 0.67 | 0.67 | = |
| 10 | privacy | Derechos RGPD | 1.00 | 1.00 | = |
| 11 | privacy | DPO obligatorio | 0.40 | 0.40 | = |
| 12 | compliance | Compliance penal | **0.20** | 0.00 | Base gana |
| 13 | civil | Recurso contencioso | 0.50 | 0.50 | = |
| 14 | civil | Prescripción delitos | 0.60 | 0.60 | = |
| 15 | contract | Constitución SL | 0.40 | 0.40 | = |
| | | **PROMEDIO** | **0.457** | 0.427 | **Base +7%** |

### 4.2 Análisis del Fine-tuning

**El modelo base gana en 4 preguntas, el fine-tuned gana en 2, empatan en 9.**

| Observación | Detalle |
|---|---|
| **Base superior en ERE** | 0.50 vs 0.00 — el base menciona "período de consultas" y "causas ETOP", el FT no |
| **Base superior en IRPF** | 0.50 vs 0.17 — el base identifica más tramos correctos |
| **FT superior en IVA** | 0.75 vs 0.50 — el FT identifica los 3 tipos + porcentajes |
| **FT superior en alquiler** | 0.50 vs 0.00 — el FT conoce la LAU y los 5 años |

**Conclusión**: El fine-tuning sobre legislación BOE no mejoró significativamente el keyword recall. El modelo base Qwen2.5-7B ya tiene conocimiento legal español razonable. El fine-tuning parece haber reforzado algunos temas (IVA, LAU) a costa de otros (ERE, IRPF). Se recomienda evaluación semántica con LLM-as-judge para determinar si la calidad narrativa y la precisión de citas mejoraron con el fine-tuning.

---

## 5. Problemas de Infraestructura Resueltos

### 4.1 vLLM v0.13.0 incompatible con AWQ

**Problema**: vLLM v0.13.0 (V1 Engine con EngineCore subprocess) cuelga durante la carga de pesos AWQ. Probados: `awq_marlin`, `awq`, `bitsandbytes` — todos cuelgan en `FLASH_ATTN`.

**Solución**: Pin a `vllm/vllm-openai:v0.8.5.post1` en `docker-compose.onpremise.yml`.

### 4.2 Docker Compose incorrecto

**Problema**: Se editaba `docker-compose.yml` (base) en lugar de `docker-compose.onpremise.yml` (override activo).

**Solución**: Documentado en `CLAUDE.md` que `docker-compose.onpremise.yml` es el archivo activo para on-premise.

### 4.3 BitsAndBytes no carga pesos

**Problema**: BnB NF4 en vLLM v0.8.5.post1 muestra proceso activo pero solo lee 31MB de los 14GB del modelo.

**Solución**: Revertido a AWQ que funciona correctamente.

---

## 6. Próximos Pasos

### 5.1 Prioridad Alta

#### A. Mitigar loops de generación del modelo 7B
**Problema**: En varias respuestas RAG, el modelo entra en loops repetitivos (ej. "Sentencia judicial de inhabilitación..." repetido 25 veces en despido disciplinario).

**Solución propuesta**:
- Añadir `repetition_penalty=1.2` en la configuración de vLLM
- Implementar detección de repetición en `base.py` con early-stop cuando se detecten 3+ frases consecutivas idénticas
- Reducir `max_tokens` del specialist agent de ~2000 a ~800 para respuestas más concisas

#### B. Activar LLM-as-Judge para evaluación semántica
**Problema**: Keyword recall es una métrica limitada — no captura corrección semántica.

**Solución propuesta**:
- Ejecutar benchmark con `--judge-provider openai --judge-model gpt-4o-mini`
- Evaluar 5 dimensiones: correctness, completeness, relevance, citation_accuracy, coherence
- Comparar si las preguntas donde RAG "pierde" por keywords realmente tienen peor calidad semántica

#### C. Investigar hybrid search 500 errors
**Problema**: Las búsquedas hybrid de documentos de tenant devuelven HTTP 500 desde weaviate-service.

**Impacto**: El RAG solo usa knowledge público (legislación BOE), no aprovecha documentos del usuario.

**Solución propuesta**:
- Revisar logs de weaviate-service durante benchmark
- Verificar que la colección de tenant existe y tiene datos
- Puede ser un problema de schema o de filtros en la query Weaviate

### 5.2 Prioridad Media

#### D. Mejorar retrieval con sector-specific prompts
**Problema**: El prompt del specialist es genérico. Para consultas legales específicas (ERE, compliance penal), los chunks recuperados pueden no ser los más relevantes.

**Solución propuesta**:
- Ajustar `hybrid_alpha` por tipo de consulta (más keyword para datos numéricos, más semántico para conceptos)
- Añadir re-ranking con cross-encoder antes del specialist
- Aumentar `top_k` de 12 a 15-20 para consultas complejas

#### E. Fine-tuning del modelo para RAG
**Problema**: El modelo `boe-legal-qwen-7b-awq` fue fine-tuneado para respuesta directa, no para responder con contexto RAG inyectado.

**Solución propuesta**:
- Crear dataset de entrenamiento con formato `(pregunta, contexto_RAG, respuesta_esperada)`
- Fine-tune con LoRA/QLoRA sobre el escenario RAG
- Evaluar si mejora la capacidad de integrar contexto recuperado con conocimiento paramétrico

#### F. Habilitar herramientas selectivamente
**Problema**: El fix actual desactiva TODAS las herramientas para consultas de conocimiento. Esto es correcto para preguntas legales generales, pero podría limitar funcionalidad futura (ej. web_search para datos actualizados).

**Solución propuesta**:
- Implementar clasificación de intent en `general_node`: `knowledge_query` vs `document_operation`
- Solo pasar herramientas cuando el intent es `document_operation`
- Usar el Intent Router existente (FastEmbed) para esta clasificación

### 5.3 Prioridad Baja

#### G. Optimizar latencia del pipeline RAG
**Problema**: p50 de ~10s es aceptable pero mejorable. La mayor parte del tiempo se gasta en el specialist (~5-8s de inferencia LLM).

**Solución propuesta**:
- Paralelizar retrieve + graph_expand (actualmente secuenciales)
- Cache de respuestas del specialist para preguntas frecuentes
- Evaluar modelo más pequeño (4B) para el specialist, reservando el 7B para synthesize

#### H. Ampliar benchmark a 50+ preguntas
**Problema**: 15 preguntas es insuficiente para conclusiones estadísticas robustas.

**Solución propuesta**:
- Expandir a 50 preguntas cubriendo más subdominios (penal, mercantil, procesal)
- Añadir preguntas de dificultad mixta (easy/medium/hard en proporciones iguales)
- Incluir preguntas que requieran razonamiento multi-hop (combinar varias leyes)

---

## 7. Configuración Actual del Sistema

```yaml
# Modelo
modelo: horelvis/boe-legal-qwen-7b-awq
quantización: AWQ 4-bit (awq_marlin en runtime)
vllm_version: v0.8.5.post1
max_model_len: 16384
gpu_memory_utilization: 0.65

# RAG Pipeline
sector: legal
hybrid_alpha: 0.7
top_k: 12
chunk_strategy: legal_sections (1500/200)
min_relevance_score: 0.45

# Pipeline Flow
coordinator → context_tree → retrieve → graph_expand → specialist → synthesize → END
specialist_tools: [] (desactivadas para knowledge queries)
```

---

## 8. Archivos Modificados

| Archivo | Cambio | Línea |
|---|---|---|
| `emma-agent-service/app/agents/langgraph/nodes/specialists/general.py` | `tools=general_tools` → `tools=[]` | 774-780 |
| `backend/docker/docker-compose.onpremise.yml` | vLLM pinned a v0.8.5.post1, AWQ config | vllm service |
| `backend/docker/.env` | `VLLM_MODEL=horelvis/boe-legal-qwen-7b-awq` | 148-149 |
| `CLAUDE.md` | Documentación Docker Compose on-premise | Sección Docker |

---

*Informe generado automáticamente. Benchmark ejecutado el 2026-02-02 a las 13:35 UTC.*
