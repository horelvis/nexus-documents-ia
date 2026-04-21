# Roadmap — User-Created Agents

**Estado:** Propuesta · mock navegable en frontend · sin backend real
**Última actualización:** 2026-04-21
**Rama de referencia:** `refactor/remove-multi-tenancy` (HEAD `11f41b89`)

> Objetivo: permitir al usuario final crear agentes personalizados sobre Emma, sin instalar LangSmith ni LangGraph Platform. Aprovechar la infra existente (LangGraph ReAct agent, Langfuse, tool registry, checkpointer).

---

## Principios de diseño

1. **Data-first, no tool-first.** El comportamiento de un agente se define por el subconjunto de datos al que accede (carpetas, semantic_types, fechas, conectores, entidades, calidad). La tool list se habilita por defecto; se desactiva solo como caso borde.
2. **Sin taxonomías prescriptivas.** Eliminar `domain` como filtro elegible en UI y como propiedad persistida. Los sectores ya fueron eliminados (2026-03-31); `domain` es su residuo y debe caer.
3. **Una conversación = un agente.** No hay multi-agente dentro de un thread. Cambiar de agente inicia un nuevo thread. El checkpointer (AsyncPostgresSaver) es per-thread.
4. **Scope siempre visible.** El usuario ve en todo momento qué corpus usa su agente. Transparencia frente a "caja negra".
5. **Hand-off explícito.** Un agente puede recomendar a otro, pero el usuario aprueba con clic. Jamás hand-off silencioso.
6. **El agente obligatorio al iniciar chat.** La home es un picker, no Emma general directa. "Emma general" pasa a ser un agente más (seed, `scope={}`, `visibility='public'`).

---

## Dependencias y bloqueantes

### Pre-requisito · Remover `domain` del stack

Mapa de impacto (ver survey `2026-04-21`):

| Categoría | Archivos | Servicio |
|---|---:|---|
| Origen (classifier.py FILENAME_PATTERNS) | 1 | intelligence-docs |
| Schema Weaviate | 2 | weaviate-service |
| Schema BD (KnowledgeEntity.domain) | 2 | backend/app + alembic |
| Escritores en indexing_pipeline | 5 | weaviate-service |
| Lectores (domain_filter) | 9 | emma-agent + weaviate |
| Prompts/reglas con `domain` | 2 | emma-agent |
| Tests del classifier | 1 | intelligence-docs |

**PRs propuestos** (una rama `refactor/remove-domain-taxonomy`):

- **PR 1 · Stop-write.** `classifier.py` deja de asignar `domain`; `indexing_pipeline` no escribe. Lectores ya toleran `null` vía fallback progresivo.
- **PR 2 · Remove-readers.** Eliminar `domain_filter` de `smart_search`, `specialists`, `memorag`, `weaviate_client`. Migrar reglas de prompts en Langfuse.
- **PR 3 · Drop-schema.** Alembic migration remove `KnowledgeEntity.domain` + update Weaviate schema. Re-indexación opcional.

---

## Fases de entrega

### Fase 0 — Eliminación de `domain`  *(bloqueante de Fase 3)*

Los 3 PRs descritos arriba. Sin esto, el builder data-first queda contaminado por una dimensión prescriptiva.

### Fase 1 — Mock navegable frontend  *(COMPLETADO · 2026-04-21)*

Entregado:
- Galería `/agents` con 3 agentes seed + búsqueda + filtros.
- Builder `/agents/new` y `/agents/[id]/edit` con:
  - Identidad (icono, color, nombre, descripción)
  - System prompt (a reducir en Fase 2 a "persona")
  - Tool picker (a mover a "Avanzado" en Fase 2)
  - Scope con folders y roles (ampliar en Fase 2)
  - Modelo (PLANNER/CHAT + temperatura)
  - Visibilidad (private/shared)
- Playground simulado con SSE mock (thinking, tool_call, token).
- Grupo "Agentes" en `AppSidebar`.
- Persistencia en `localStorage` (`nouxcube.user_agents.v1`).

Archivos:
- `frontend/src/lib/mocks/agents-mock.ts`
- `frontend/src/components/agents/agent-builder-form.tsx`
- `frontend/src/components/agents/agent-playground-mock.tsx`
- `frontend/src/app/agents/{page,new/page,[id]/edit/page}.tsx`
- `frontend/src/components/layout/app-sidebar.tsx` (+24 líneas)

### Fase 2 — Refactor UX hacia "data-first" puro

Ajustar el mock actual:

| Cambio | Razón |
|---|---|
| Mover "Herramientas" a sección "Avanzado" colapsable | Tools están siempre disponibles; el usuario no debe elegirlas |
| Sustituir "System prompt" de 7 líneas por **Persona** (estilo, idioma, instrucciones breves) | Reducir complejidad cognitiva |
| Ampliar "Scope" a 7 dimensiones reales: folders, semantic_types (auto-sugeridos desde folders), person_filter, entity_filters, date_range, quality_min, connector_ids, doc_roles_filter | Reflejar los filtros reales de Weaviate/smart_search |
| **Eliminar `domain` como dimensión elegible** | Sector con otro nombre |
| Añadir **"Vista previa de corpus"** con contador en vivo ("verás 346 docs") | Feedback inmediato al usuario |
| Añadir **"Ver muestra de 10 documentos"** | Diagnóstico previo a publicar |

### Fase 3 — Home como picker obligatorio

Refactor de rutas:

| Antes | Después |
|---|---|
| `/` = chat Emma general | `/` = **picker de agentes** |
| — | `/chat/:agentId` = nuevo thread con ese agente |
| — | `/chat/:agentId/:threadId` = conversación existente |

Features del picker:
- "Tu último agente" (Enter lo selecciona)
- Favoritos con teclas 1-9
- Buscador con Cmd/Ctrl+K
- Acceso rápido a "Crear agente nuevo"
- "Emma general" como agente más (no special-cased)

Effects:
- Eliminar rama `if agent_id is None` del loader backend — siempre hay agente.
- Telemetría `usage_count` gratuita para ordenar galería.

### Fase 4 — Backend real (tabla + API + loader)

**Modelo** (`backend/app/db/user_agent_models.py`):

```python
class UserAgent(Base):
    id, owner_id, name, description, icon, color
    persona = JSON          # {style, language, instructions}
    scope   = JSON          # {folders, semantic_types, person_filter,
                            #  entity_filters, date_range, quality_min,
                            #  connector_ids, doc_roles_filter}
    visibility, shared_with_roles
    disabled_tools = ARRAY  # whitelist invertida (vacío = todos activos)
    model_role, temperature
    usage_count, created_at, updated_at
```

**Migración**: `python scripts/create_migration.py -m "add user_agents" --autogenerate`

**API CRUD** (`backend/app/api/v1/agents.py` — reescribir el stub existente):
- `GET /api/v1/agents` — lista accesibles al usuario
- `POST /api/v1/agents` — crear
- `GET /api/v1/agents/:id` — detalle
- `PUT /api/v1/agents/:id` — actualizar
- `DELETE /api/v1/agents/:id` — eliminar
- `POST /api/v1/agents/:id/duplicate`
- `GET /api/v1/agents/:id/corpus-preview` — "verás N docs + M entidades"

**Loader** (`emma-agent-service/app/agents/user_agent_loader.py`):
- Fetch agent config del Main API
- Fetch prompt de Langfuse (convención `user_agent_{id}_system`)
- Inyectar scope en `tool_context` del ReAct graph

**Extender `ToolRegistry.get_tools_for_context()`**:
- Aceptar `disabled_tools: Set[str]` (whitelist invertida)

**Extender `/emma/query/stream`**:
- Campo `agent_id` obligatorio en request
- Loader antes de compilar grafo

### Fase 5 — UX runtime

Elementos del chat cuando hay un agente custom activo:

- **Header con scope visible**: "📁 Legal/Laboral + RRHH · 346 docs"
- **Cada respuesta del asistente lleva badge del agente** (icono + nombre + mini-scope)
- **Primera vez que se usa un agente**: modal con resumen de scope + "Ver muestra de 10 docs"
- **Respuesta con 0 resultados dentro del scope**: mensaje explícito + sugerencias de otros agentes (modo 3 del handoff)
- **Historial scoped por agente** con filtro "todos / solo este agente"
- **Footer con "↻ Ask Emma general"** y **"🔀 Otro agente"**

### Fase 6 — Hand-off MVP (modo 1 — manual)

- Botón "🔀 Otro agente" en el footer de cada respuesta
- Modal con top-3 agentes relevantes (ver algoritmo en Fase 7)
- Payload estructurado al cambiar:
  ```json
  {
    "from_agent_id": "...",
    "source_thread_id": "...",
    "task_summary": "1 frase",
    "entities": ["...", "..."]
  }
  ```
- Nuevo thread con agente destino, payload inyectado como system message
- Historial con cadena visible: `⚖️ thread-A ↔ 💰 thread-B`

### Fase 7 — Hand-off auto (modo 3 — detección fuera de scope)

Heurística determinista en `synthesize_react_node`:

```
if smart_search devolvió 0 resultados:
    entities = extract_entities(query)
    candidates = rank_agents_by_scope_overlap(entities, user)
    if candidates and top_score > threshold:
        emit handoff_suggestion_card(candidates[:3])
```

Algoritmo de ranking (`suggest_agents`):
1. Filtro ACL (`user_can_access`)
2. Overlap entidades query ↔ folders del agente (peso 2.0)
3. Match semantic_type query ↔ agent.scope.semantic_types (peso 1.5)
4. Cosine similarity embedding(query) ↔ embedding(agent.description) (peso 1.0)

Coste: ~10ms, sin LLM.

### Fase 8 — Canales sociales

Extender tabla `channels` de Emma Reactive para vincular `channel_id → agent_id`:

| Modelo | Comportamiento |
|---|---|
| Slack `#legal-laboral` → `juridico-laboral` | Toda mención usa ese agente |
| Telegram chat `/set-agent X` | Per-user default en ese chat |
| WhatsApp pairing | Agente configurado al hacer pairing |

### Fase 9 — Opcionales / futuros

- **Modo rápido**: sugerir agente automáticamente mientras el usuario escribe (requiere intent_router adaptado)
- **Hand-off modo 2**: tool `recommend_agent` invocable por el LLM (requiere entrenar Qwen 9B o heurística híbrida)
- **ACL filter sobre entidades citadas en handoff**: redactar/omitir entidades que el usuario destino no puede ver
- **Plantillas públicas**: biblioteca de agentes "oficiales" (Laboral, Fiscal, Cumplimiento...) que el admin puede instalar con un clic
- **Métricas por agente**: latencia media, coste por query, tasa de "fuera de scope"
- **Versionado de agente**: cambios en scope/persona generan nueva versión; conversaciones antiguas mantienen la versión usada

---

## Decisiones tomadas

- Una conversación = un agente. No Swarm cross-agent (Swarm queda para multi-especialista interno de Emma).
- Agente obligatorio al iniciar chat. "Emma general" es un agente más.
- Tool list como opt-out, no opt-in.
- Persona reemplaza al system prompt largo.
- Hand-off transfiere **intención y entidades**, nunca mensajes en bruto.
- `domain` se elimina del stack antes de Fase 3.

---

## Preguntas abiertas

1. **Prompt versioning en Langfuse**: ¿cada agente tiene un prompt propio (`user_agent_{id}_system`) o un prompt base compartido con variables? → Decidir en Fase 4.
2. **Límite de agentes por usuario**: ¿hay cap? → Inicialmente sin cap, observar telemetría.
3. **Agentes compartidos vs fork**: si el owner modifica un agente compartido, ¿afecta a quienes lo usan activamente? → Proponer: cambios en persona afectan inmediato; cambios en scope crean versión nueva, usuarios quedan en la anterior hasta re-seleccionar.
4. **Detección de "fuera de scope"**: ¿cuál es el threshold correcto de 0 resultados antes de sugerir hand-off? → Instrumentar en Fase 7.
5. **Hand-off loops A→B→C→A**: ¿cuántos hops máximos? → Propuesta: 3 hops, después desactivar auto-suggestions.

---

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Usuarios crean agentes redundantes/ruidosos | Galería con filtros + ranking por `usage_count` |
| Hand-off erosiona confianza ("me pasan el marrón") | Modo auto solo en 0-resultados, nunca sobre respuestas sustantivas |
| ACL leak en `task_summary` del handoff | Filtro de intersección ACL entre entidades citadas y accesos del usuario destino |
| Deep-link `/chat/:id/:thread` con agente eliminado | Fallback a picker con mensaje "este agente ya no existe" |
| Corpus vacío tras configurar scope (filtros demasiado estrictos) | "Vista previa" en el builder alerta si el corpus queda < 10 docs |
| Performance del loader en cada query | Cache del `UserAgentConfig` en Redis con TTL 60s + invalidación on update |

---

## Referencias cruzadas

- [CLAUDE.md](../../CLAUDE.md) — arquitectura global
- [TRUSTGRAPH](../architecture/TRUSTGRAPH.md) — graph_rag pipeline (herramienta usada por todos los agentes)
- [EMMA_REACTIVE](../architecture/EMMA_REACTIVE.md) — canales y triggers (Fase 8)
- [PROMPT_MANAGEMENT](../architecture/PROMPT_MANAGEMENT.md) — Langfuse (prompts por agente)
- [USER_MEMORY](../architecture/USER_MEMORY.md) — memoria persistente (ortogonal a agentes)
