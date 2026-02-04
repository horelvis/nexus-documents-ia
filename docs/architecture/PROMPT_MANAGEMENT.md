# Prompt Management Architecture

Sistema de gestión dinámica de prompts para Emma, el agente de IA de NouxCubeIA.

## Índice

1. [Visión General](#visión-general)
2. [Arquitectura](#arquitectura)
3. [Langfuse - Gestión del Ciclo de Vida](#langfuse---gestión-del-ciclo-de-vida)
4. [Rules Engine - Inyección Dinámica](#rules-engine---inyección-dinámica)
5. [Guardrails - Validación de Salidas](#guardrails---validación-de-salidas)
6. [Few-Shot Examples - Aprendizaje por Ejemplos](#few-shot-examples---aprendizaje-por-ejemplos)
7. [API Endpoints](#api-endpoints)
8. [Configuración](#configuración)
9. [Ejemplos de Uso](#ejemplos-de-uso)

---

## Visión General

El sistema de Prompt Management permite:

| Funcionalidad | Descripción |
|---------------|-------------|
| **Langfuse** | Versionado, A/B testing, rollback de prompts |
| **Rules** | Inyección dinámica de contenido según contexto |
| **Guardrails** | Validación post-LLM (PII, keywords, formato) |
| **Few-Shot** | Ejemplos similares por búsqueda semántica |

### Beneficios

- **Sin redespliegue**: Cambios en prompts sin reiniciar servicios
- **Trazabilidad**: Historial completo de versiones en Langfuse
- **Multi-tenant**: Reglas y guardrails por tenant
- **Observabilidad**: Métricas de uso y rendimiento

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend / API                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Emma Agent Service (8009)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │PromptComposer│  │  RuleEngine  │  │  GuardrailService    │   │
│  │              │  │              │  │                      │   │
│  │ • Langfuse   │  │ • Evaluate   │  │ • Validate           │   │
│  │ • YAML       │  │ • Apply      │  │ • Redact             │   │
│  │ • Cache      │  │ • Cache      │  │ • Block              │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                      │               │
│         │         ┌───────┴──────────────────────┘               │
│         │         │  HTTP Proxy (no DB directo)                  │
└─────────┼─────────┼─────────────────────────────────────────────┘
          │         │
          ▼         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Main API (8000)                             │
│                                                                  │
│  /api/v1/prompts/rules      → emma_prompt_rules                 │
│  /api/v1/prompts/few-shot   → emma_few_shot_examples            │
│  /api/v1/prompts/guardrails → emma_guardrails                   │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PostgreSQL                                  │
│                                                                  │
│  • emma_prompt_rules        (condiciones, acciones)             │
│  • emma_few_shot_examples   (Q&A + embeddings pgvector)         │
│  • emma_guardrails          (validación post-LLM)               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Langfuse (3002)                             │
│                                                                  │
│  • Prompt versioning        • A/B testing                       │
│  • LLM tracing             • Rollback                           │
│  • Web UI                  • Métricas                           │
└─────────────────────────────────────────────────────────────────┘
```

### Patrón de Comunicación

Emma Agent Service **NO** accede directamente a PostgreSQL. Toda operación de base de datos pasa por Main API:

```
Emma Service → HTTP Request → Main API → PostgreSQL
     ↓
  Cache local (TTL: 5 min)
```

---

## Langfuse - Gestión del Ciclo de Vida

### Acceso Web UI

- **URL**: http://localhost:3002
- **Usuario**: admin@nouxcube.com
- **Password**: LangfuseAdmin2024!

### Funcionalidades

| Feature | Descripción |
|---------|-------------|
| **Versionado** | Cada cambio crea nueva versión |
| **Rollback** | Restaurar versión anterior con un click |
| **A/B Testing** | Probar variantes con % de tráfico |
| **Tracing** | Ver inputs/outputs de cada llamada LLM |
| **Métricas** | Latencia, tokens, costos por prompt |

### Crear/Editar Prompts en Langfuse

1. Acceder a http://localhost:3002
2. Ir a **Prompts** → **Create Prompt**
3. Configurar:
   - **Name**: Identificador único (ej: `emma_system_prompt`)
   - **Prompt**: Contenido con variables Jinja2 `{{variable}}`
   - **Config**: Parámetros opcionales (temperature, max_tokens)

### Variables Jinja2 Soportadas

```jinja2
{{user_query}}         - Pregunta del usuario
{{context}}            - Contexto RAG recuperado
{{sector}}             - Sector activo (legal, medical, documental)
{{agent_name}}         - Nombre del agente especialista
{{language}}           - Idioma detectado
{{today}}              - Fecha actual
```

### Sincronización con Emma

```bash
# Forzar sincronización desde Langfuse
curl -X POST "http://localhost:8009/prompts/sync" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt_names": ["emma_system_prompt"]}'
```

---

## Rules Engine - Inyección Dinámica

Las reglas permiten modificar prompts dinámicamente según el contexto de la solicitud.

### Tipos de Acciones

| action_type | Descripción | Ejemplo de uso |
|-------------|-------------|----------------|
| `inject_block` | Añade contenido al prompt | Instrucciones específicas por tipo de documento |
| `skip_block` | Omite sección del prompt | Desactivar funcionalidad para ciertos usuarios |
| `modify_context` | Modifica variables de contexto | Cambiar temperatura según complejidad |
| `set_variable` | Establece variable específica | Forzar idioma de respuesta |

### Estructura de una Regla

```json
{
  "rule_name": "labor_contract_analysis",
  "description": "Instrucciones especiales para contratos laborales",
  "conditions": {
    "document_type": "contrato_laboral",
    "action": "analyze"
  },
  "action_type": "inject_block",
  "action_config": {
    "block_name": "labor_instructions",
    "content": "Analiza especialmente: salario base, jornada laboral, periodo de prueba, cláusulas de confidencialidad.",
    "position": "prepend"
  },
  "priority": 100,
  "is_active": true
}
```

### Condiciones Soportadas

```json
{
  "document_type": "contrato_laboral",    // Tipo exacto
  "document_type": ["contrato", "anexo"], // Lista de tipos
  "action": "analyze",                     // Acción solicitada
  "sector": "legal",                       // Sector activo
  "domain": "labor",                       // Dominio del agente
  "user_role": "admin",                    // Rol del usuario
  "has_attachments": true,                 // Condición booleana
  "query_contains": "despido"              // Substring en query
}
```

### API de Reglas

```bash
API_KEY="JWFu8l5QmBnWz1xk26Y7QMCWYeEKcTtPPzcLyb285Cc"
TENANT_ID="00000000-0000-0000-0000-000000000001"

# Crear regla
curl -X POST "http://localhost:8009/prompts/rules" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "fiscal_docs_extra_care",
    "description": "Mayor precisión para documentos fiscales",
    "conditions": {"document_type": "declaracion_fiscal"},
    "action_type": "modify_context",
    "action_config": {"temperature": 0.1, "require_citations": true},
    "priority": 50
  }'

# Listar reglas
curl -X GET "http://localhost:8009/prompts/rules" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID"

# Evaluar reglas (ver cuáles aplican)
curl -X POST "http://localhost:8009/prompts/rules/evaluate" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"document_type": "declaracion_fiscal", "action": "analyze"}'

# Eliminar regla
curl -X DELETE "http://localhost:8009/prompts/rules/{rule_id}" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID"
```

---

## Guardrails - Validación de Salidas

Los guardrails validan las respuestas del LLM **antes** de enviarlas al usuario.

### Tipos de Guardrails

| guardrail_type | Descripción | Caso de uso |
|----------------|-------------|-------------|
| `keyword` | Detecta palabras bloqueadas/requeridas | Filtrar PII, asegurar disclaimers |
| `regex` | Patrones regex | Detectar formatos sensibles (DNI, tarjetas) |
| `semantic` | Similitud semántica con embeddings | Detectar temas prohibidos |
| `llm_validator` | Validación con otro LLM | Verificar factualidad |
| `length` | Límites de caracteres/palabras | Controlar extensión |
| `format` | Requisitos estructurales | Exigir fuentes, idioma |

### Acciones on Match

| action_on_match | Comportamiento |
|-----------------|----------------|
| `block` | Rechaza la respuesta completamente |
| `warn` | Permite pero registra advertencia |
| `redact` | Reemplaza contenido sensible con `[REDACTED]` |

### Estructura de un Guardrail

```json
{
  "guardrail_name": "pii_blocker",
  "description": "Bloquea información personal identificable",
  "guardrail_type": "keyword",
  "config": {
    "blocked_words": ["DNI", "NIF", "número de cuenta", "tarjeta de crédito"],
    "required_words": []
  },
  "action_on_match": "redact",
  "applies_to": ["*"],
  "priority": 10,
  "is_active": true
}
```

### Configuración por Tipo

#### Keyword
```json
{
  "blocked_words": ["DNI", "contraseña", "PIN"],
  "required_words": ["Nota:", "Fuente:"]
}
```

#### Regex
```json
{
  "pattern": "\\b\\d{8}[A-Z]\\b",
  "flags": "i"
}
```

#### Semantic
```json
{
  "forbidden_topics": ["información médica confidencial", "datos bancarios"],
  "similarity_threshold": 0.8
}
```

#### Length
```json
{
  "min_chars": 100,
  "max_chars": 5000,
  "min_words": 20,
  "max_words": 1000
}
```

#### Format
```json
{
  "must_contain_sources": true,
  "require_spanish": true,
  "require_structure": ["Resumen:", "Conclusión:"]
}
```

### API de Guardrails

```bash
# Crear guardrail
curl -X POST "http://localhost:8009/prompts/guardrails" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "guardrail_name": "dni_detector",
    "description": "Detecta y redacta DNIs españoles",
    "guardrail_type": "regex",
    "config": {"pattern": "\\b\\d{8}[A-Z]\\b", "flags": "i"},
    "action_on_match": "redact",
    "applies_to": ["*"]
  }'

# Probar guardrails contra contenido
curl -X POST "http://localhost:8009/prompts/guardrails/test" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "El DNI del cliente es 12345678A",
    "agent_name": "LegalAgent"
  }'

# Respuesta esperada:
# {
#   "results": [{
#     "guardrail_name": "dni_detector",
#     "matched": true,
#     "action": "redact",
#     "details": "Pattern matched",
#     "matched_content": "12345678A"
#   }],
#   "would_block": false,
#   "overall_action": "redact"
# }
```

---

## Few-Shot Examples - Aprendizaje por Ejemplos

Sistema de ejemplos question-answer que se inyectan dinámicamente usando búsqueda semántica.

### Dominios Soportados

| domain | Descripción |
|--------|-------------|
| `legal` | Derecho, contratos, normativa |
| `medical` | Salud, diagnósticos, tratamientos |
| `documental` | Gestión documental general |
| `general` | Uso general |

### Estructura de un Ejemplo

```json
{
  "question": "¿Cuántos días de preaviso necesito para un despido disciplinario?",
  "answer": "En un despido disciplinario no se requiere preaviso según el artículo 55 del Estatuto de los Trabajadores. El despido puede ser efectivo desde el momento de su comunicación al trabajador.",
  "category": "despido",
  "domain": "legal",
  "tags": ["laboral", "despido", "preaviso"]
}
```

### Funcionamiento

1. Usuario hace una pregunta
2. Sistema genera embedding de la pregunta
3. Búsqueda por similitud coseno en `emma_few_shot_examples`
4. Top-K ejemplos más similares se inyectan en el prompt
5. LLM usa ejemplos como referencia para responder

### API de Few-Shot

```bash
# Crear ejemplo
curl -X POST "http://localhost:8009/prompts/few-shot" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Qué es la indemnización por despido improcedente?",
    "answer": "La indemnización por despido improcedente es de 33 días de salario por año trabajado, con un máximo de 24 mensualidades, según el artículo 56 del ET.",
    "category": "despido",
    "domain": "legal",
    "tags": ["laboral", "indemnización"]
  }'

# Buscar ejemplos similares
curl -X POST "http://localhost:8009/prompts/few-shot/search" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "¿Cuánto me corresponde si me despiden?",
    "limit": 3,
    "domain": "legal"
  }'

# Dar feedback (mejora ranking)
curl -X POST "http://localhost:8009/prompts/few-shot/feedback" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "example_id": "uuid-del-ejemplo",
    "is_positive": true,
    "comment": "Respuesta muy útil"
  }'
```

---

## API Endpoints

### Emma Service (8009)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/prompts/health` | Estado del sistema |
| GET | `/prompts/available` | Lista prompts disponibles |
| POST | `/prompts/sync` | Sincronizar desde Langfuse |
| POST | `/prompts/cache/invalidate` | Limpiar caché |
| POST | `/prompts/reload` | Recargar YAML |
| **Rules** | | |
| GET | `/prompts/rules` | Listar reglas |
| POST | `/prompts/rules` | Crear regla |
| PUT | `/prompts/rules/{id}` | Actualizar regla |
| DELETE | `/prompts/rules/{id}` | Eliminar regla |
| POST | `/prompts/rules/evaluate` | Evaluar reglas contra contexto |
| **Few-Shot** | | |
| GET | `/prompts/few-shot` | Listar ejemplos |
| POST | `/prompts/few-shot` | Crear ejemplo |
| PUT | `/prompts/few-shot/{id}` | Actualizar ejemplo |
| DELETE | `/prompts/few-shot/{id}` | Eliminar ejemplo |
| POST | `/prompts/few-shot/search` | Buscar similares |
| POST | `/prompts/few-shot/feedback` | Enviar feedback |
| **Guardrails** | | |
| GET | `/prompts/guardrails` | Listar guardrails |
| POST | `/prompts/guardrails` | Crear guardrail |
| PUT | `/prompts/guardrails/{id}` | Actualizar guardrail |
| DELETE | `/prompts/guardrails/{id}` | Eliminar guardrail |
| POST | `/prompts/guardrails/test` | Probar contra contenido |

### Headers Requeridos

```
X-API-Key: {MICROSERVICES_API_KEY}
X-Tenant-ID: {tenant_uuid}  # Para operaciones multi-tenant
Content-Type: application/json
```

---

## Configuración

### Variables de Entorno

```bash
# Langfuse
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-emma-dev
LANGFUSE_SECRET_KEY=sk-emma-dev
USE_LANGFUSE_PROMPTS=true

# Feature Flags
RULE_ENGINE_ENABLED=true
FEW_SHOT_ENABLED=true
GUARDRAILS_ENABLED=true

# Cache
LANGFUSE_PROMPT_CACHE_TTL=300  # 5 minutos
```

### Prioridades

Las reglas y guardrails se evalúan en orden de prioridad (menor número = mayor prioridad):

- **1-50**: Críticos (seguridad, compliance)
- **51-100**: Normales (lógica de negocio)
- **101-200**: Opcionales (mejoras UX)

---

## Ejemplos de Uso

### Caso 1: Respuestas en español obligatorio

```bash
# Crear guardrail de idioma
curl -X POST "http://localhost:8009/prompts/guardrails" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "guardrail_name": "spanish_only",
    "guardrail_type": "format",
    "config": {"require_spanish": true},
    "action_on_match": "warn",
    "applies_to": ["*"]
  }'
```

### Caso 2: Instrucciones extra para contratos

```bash
# Crear regla para contratos
curl -X POST "http://localhost:8009/prompts/rules" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "contract_analysis_enhanced",
    "conditions": {"document_type": "contrato"},
    "action_type": "inject_block",
    "action_config": {
      "content": "IMPORTANTE: Identifica y lista todas las cláusulas de penalización, fechas límite y condiciones de rescisión.",
      "position": "prepend"
    },
    "priority": 75
  }'
```

### Caso 3: Bloquear respuestas con datos médicos

```bash
# Crear guardrail de datos médicos
curl -X POST "http://localhost:8009/prompts/guardrails" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "guardrail_name": "medical_data_blocker",
    "guardrail_type": "semantic",
    "config": {
      "forbidden_topics": ["diagnóstico médico específico", "historial clínico", "medicación prescrita"],
      "similarity_threshold": 0.75
    },
    "action_on_match": "block",
    "applies_to": ["*"]
  }'
```

---

## Troubleshooting

### Langfuse no conecta

```bash
# Verificar estado
curl http://localhost:3002/api/public/health

# Ver logs
docker logs docker-langfuse-1
```

### Reglas no se aplican

```bash
# Verificar caché (invalidar si es necesario)
curl -X POST "http://localhost:8009/prompts/cache/invalidate" \
  -H "X-API-Key: $API_KEY"

# Evaluar manualmente
curl -X POST "http://localhost:8009/prompts/rules/evaluate" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"document_type": "tu_tipo", "action": "tu_accion"}'
```

### Guardrails no detectan contenido

1. Verificar que el guardrail está `is_active: true`
2. Verificar que `applies_to` incluye el agente o `["*"]`
3. Para `keyword`: usar `blocked_words` (no `keywords`)
4. Para `regex`: verificar escape de caracteres especiales

---

## Referencias

- [Langfuse Documentation](https://langfuse.com/docs)
- [Pydantic Field Validation](https://docs.pydantic.dev/latest/)
- [Jinja2 Template Syntax](https://jinja.palletsprojects.com/)
