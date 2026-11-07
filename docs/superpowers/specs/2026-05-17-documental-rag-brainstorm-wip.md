# Documental RAG — Clean Rewrite Brainstorm (WIP)

**Status**: PAUSED 2026-05-17 — resume next session
**Skill in use**: `superpowers:brainstorming`
**Owner**: hcastillo.mendoza@gmail.com (horelvis)

## Motivación

El backend actual (`emma-agent-service` + 13 microservicios alrededor) ha acumulado deuda
tras múltiples pivotes arquitectónicos (sectors removed 2026-03-31, multi-tenancy removed,
ACL rewrite 2026-05-08, agents catalog, heartbeat, social agent, swarm, etc.). El objetivo
es **crear una nueva rama** (backend only) e implementar un **producto documental RAG limpio**
inspirado en patrón Corrective RAG pero abierto a Agentic o ContextGraph.

Referencia inicial considerada: [`04_corrective_rag.py`](https://github.com/horelvis/rag_patterns/blob/claude/create-sequential-examples-ZD52z/04_corrective_rag.py).
El usuario aclaró que CRAG es **sugerencia, no contrato** — el caso de uso es documental,
abierto a Agentic o ContextGraph.

## Course correction durante la sesión

El usuario interrumpió la deriva hacia arquitectura prematura con la frase clave:

> *"Estás otra vez construyendo por el tejado, debemos centrarnos en las funcionalidades
> documentales que puede necesitar el usuario final, contratos, vencimientos, facturas,
> resúmenes."*

A partir de ese punto el brainstorming se reorientó hacia requisitos funcionales antes
de continuar con shape arquitectónico. **Al retomar, NO volver a saltar a decisiones
arquitectónicas sin queries textuales concretas en mano.**

## Decisiones tomadas (confirmadas por el usuario)

| Eje | Decisión |
|---|---|
| Patrón de query dominante | **Mixto**: factual + síntesis + relacional |
| Capa de grafo | Mantener `knowledge-tree-service` independiente; extracción async post-ingest |
| Forma de sesión | **Multi-turn chat** con `AsyncPostgresSaver` + `thread_id` |
| Documentos en MVP | Colección Weaviate **nueva** (`crag_documents` o similar) + endpoint `POST /documents` desde día 1 |
| Funcionalidades MUST-HAVE MVP | **Las 4** marcadas (ver sección siguiente) |
| Conectores | Consolidar los 4 `mcp-*-server` actuales en **un solo `ingestion-service` con arquitectura de plugins** (alfresco, gdrive, onedrive, upload); MCP protocol no se conserva (overhead innecesario para uso interno) |

### Funcionalidades MUST-HAVE marcadas

Las 4 familias fueron marcadas como must-have. Implicación: MVP ambicioso (~11-17 semanas
si todo en v0; ~6-8 semanas con phasing realista).

1. **Consulta sobre 1 documento conocido** — Q&A factual + resumen
   (*"¿cuándo vence este contrato?"*, *"resúmeme este informe"*)
2. **Búsqueda + listado en el corpus** — filtros estructurados
   (*"facturas de proveedor X en Q1"*)
3. **Tracking proactivo de eventos** — vencimientos, renovaciones
   (*"avísame cuando contrato vaya a vencer en 30 días"*) — implica `background-worker` reincorporado
4. **Análisis cruzado / extracción estructurada** — multi-doc synthesis, export
   (*"compara cláusulas de penalización de estos 3 contratos"*, *"Excel con todos los importes"*)

## Microservicios — veredicto del podado

Aplicando "test de los 3 motivos" (escalado distinto / cadencia de deploy distinta / runtime distinto):

| Servicio actual | Veredicto |
|---|---|
| `intelligence-docs-service` | ✅ **Mantener** — GPU, perfil de escalado independiente |
| `knowledge-tree-service` | ✅ **Mantener** — extracción async post-ingest, batch re-extract, distinta cadencia |
| `weaviate-service` | ❌ **Cortar → librería** — wrapper fino sobre Weaviate client |
| `storage-service` | ❌ **Cortar → librería** — wrapper sobre MinIO |
| `engine-template-service` | ❌ **Cortar** — solapa con `document-forge-service` |
| `langextract-service` | ❌ **Cortar** — solapa con extractores de `knowledge-tree-service` |
| `ollama-service` | ❌ **Cortar** — duplicado de vLLM/sglang |
| `document-forge-service` | ⚠️ **Mantener solo si deps pesadas** (LibreOffice headless); si solo python-docx/reportlab, librería |
| `mcp-alfresco-server` | 🔀 **Consolidar en `ingestion-service` como plugin** |
| `mcp-google-drive-server` | 🔀 **Consolidar en `ingestion-service` como plugin** |
| `mcp-onedrive-server` | 🔀 **Consolidar en `ingestion-service` como plugin** |
| `mcp-storage-server` | ❌ **Cortar** — wrapper de MinIO bajo flag MCP, duplicado |
| `background-worker` (Celery) | ✅ **Reincorporar** — el tracking proactivo (Funcionalidad #3) lo hace MUST |
| `emma-agent-service` | ❌ **No reusar** — escribir orquestador nuevo limpio |

## Topología target

```
┌────────────────────────────────────────────────────────────────┐
│ Infraestructura (Docker, sin LOC propio)                       │
│   Postgres │ Weaviate │ FalkorDB │ MinIO │ vLLM (sglang)       │
└────────────────────────────────────────────────────────────────┘
   ▲             ▲                ▲                ▲          ▲
   │             │                │                │          │
┌──┴────────┐ ┌─┴─────────┐ ┌────┴──────┐ ┌──────┴────────┐ ┌─┴──────────────┐
│ intel-    │ │ knowledge-│ │ ingestion-│ │ rag-           │ │ background-    │
│ docs (GPU)│ │ tree      │ │ service   │ │ orchestrator   │ │ worker         │
│           │ │ (async    │ │ (NEW)     │ │ (NEW)          │ │ (Celery)       │
│ Docling + │ │ triples)  │ │ plugins:  │ │ query-only     │ │ scheduled jobs │
│ BGE-M3    │ │           │ │  upload,  │ │ FastAPI +      │ │ - vencimientos │
│           │ │           │ │  alfresco,│ │ LangGraph      │ │ - renovaciones │
│           │ │           │ │  gdrive,  │ │                │ │ - re-extract   │
│           │ │           │ │  onedrive │ │                │ │                │
└───────────┘ └───────────┘ └───────────┘ └────────────────┘ └────────────────┘
```

**Net**: 14 microservicios → **5 servicios aplicativos** (4 + worker) + infra Docker.

## Tres enfoques arquitectónicos presentados (decisión pendiente)

### Enfoque 1 — CRAG faithful con hybrid retrieval underneath
- ~5 nodos: `load_history` → `retrieve_hybrid` → `grade` → [`answer` | `rewrite_retry` | `web_fallback`]
- Pro: brutalmente simple, pocos prompts.
- Con: paga coste de grafo siempre; queries de síntesis flojas (sin decompose).

### Enfoque 2 ⭐ — Router + sub-pipelines + grader por rama (recomendado por Claude)
- ~10-12 nodos. Router clasifica `factual | synthesis | relational` → sub-pipeline optimizado → grader CRAG común → 3 branches finales.
- Pro: cada rama optimizada para su patrón, auditable, testeable por rama.
- Con: más superficie de prompts (router + decompose + rewrite + answer).

### Enfoque 3 — Agentic ReAct con CRAG self-grade por paso
- Planner LLM con tools, grader CRAG por step.
- Pro: máxima flexibilidad.
- Con: **es esencialmente lo que hay hoy en `emma-agent-service`**, re-introduce los problemas de complejidad que se quieren escapar.

> **Pendiente**: usuario aún no eligió. La última pregunta sobre arquitectura fue
> redirigida por el usuario hacia funcionalidades concretas. No volver a presionar
> esta pregunta hasta tener queries textuales en mano.

## Pregunta abierta al retomar

> **Dame 5-8 queries CONCRETAS (textuales, como las escribiría un usuario real) que el
> día 1 del producto debería responder bien, y dime quién las haría (rol/persona/depto).**
>
> Ejemplos para inspirar:
> - *"¿Cuándo vence el contrato con TELCO S.A.?"* — admin de oficina
> - *"Resúmeme este NDA en 5 puntos clave"* — abogado in-house
> - *"Lista todas las facturas del proveedor X en Q1 2026"* — controller financiero
> - *"Compara las cláusulas de penalización de estos 3 contratos"* — director legal
> - *"Avísame cuando un contrato esté a 30 días de vencer"* — operations manager

Con esa lista de queries reales se puede:
1. Decidir qué metadata estructurada hay que extraer al ingestar (proveedor, fecha_vencimiento, importe, partes, tipo_doc, etc.)
2. Decidir qué tools necesita el orquestador (lookup_metadata, vector_search, graph_walk, aggregate, compare, schedule_notification)
3. Validar si conectores Drive/Alfresco son MUST en MVP o pueden esperar
4. Elegir entre Enfoques 1/2/3 con criterio basado en evidencia real

## Decisiones aplazadas (no preguntar hasta tener queries reales)

- Auth: KeyCloak desde día 1 vs API-key simple primero
- Streaming: SSE vs JSON sync only
- Web search fallback en MVP: sí / no
- LLM grader vs heurístico
- Cómo se exponen las funcionalidades en la API (un solo `/query` vs endpoints específicos)
- Estructura de phasing (todo en v0 vs phasing 1-4)

## TaskList state al pausar

| # | Status | Tarea |
|---|---|---|
| 1 | ✅ completed | Explorar contexto del proyecto y código de referencia CRAG |
| 2 | ✅ completed | Preguntas de clarificación sobre alcance y requisitos |
| 3 | 🔄 in_progress | Proponer 2-3 enfoques con trade-offs (presentados, pendiente elección informada) |
| 4 | pending | Presentar diseño por secciones con aprobación incremental |
| 5 | pending | Escribir y commitear documento de diseño |
| 6 | pending | Invocar writing-plans para plan de implementación |

## Cómo retomar

1. Re-invocar skill `superpowers:brainstorming` (la sesión nueva la cargará desde cero).
2. Leer este archivo.
3. Pedir al usuario las **5-8 queries textuales + persona** (ver "Pregunta abierta").
4. NO saltar a arquitectura sin esas queries. NO repetir las 7 preguntas ya respondidas.
5. Continuar con tasks #3→#6.
