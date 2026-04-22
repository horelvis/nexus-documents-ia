# Langfuse Setup Guide

Guía para configurar y usar Langfuse como sistema de gestión de prompts para Emma.

## Índice

- [¿Qué es Langfuse?](#qué-es-langfuse)
- [Arquitectura](#arquitectura)
- [Instalación Inicial](#instalación-inicial)
- [Migración de Prompts](#migración-de-prompts)
- [Uso Diario](#uso-diario)
- [Configuración de Emma](#configuración-de-emma)
- [Troubleshooting](#troubleshooting)

---

## ¿Qué es Langfuse?

Langfuse es una plataforma open-source para observabilidad y gestión de LLMs. En NouxCubeIA lo usamos para:

| Función | Descripción |
|---------|-------------|
| **Gestión de Prompts** | Editar prompts sin tocar código |
| **Versionado** | Historial de cambios con rollback |
| **A/B Testing** | Probar variantes con labels (`production`, `staging`) |
| **Observabilidad** | Métricas de uso, latencia, tokens |

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    Emma Agent Service                        │
│                                                              │
│  LangfusePromptClient ──→ Langfuse API ──→ Prompt Content   │
│                            │                                 │
│                            └── PromptNotFoundError raised    │
│                                on miss (fail-fast, no YAML) │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Langfuse (Puerto 3002)                    │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Prompts   │  │  Versions   │  │   Observability     │  │
│  │   (~90)     │  │  & Labels   │  │   & Metrics         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    PostgreSQL (langfuse DB)
```

## Instalación Inicial

### 1. Iniciar Langfuse

Langfuse se inicia automáticamente con docker-compose:

```bash
cd backend/docker
docker compose up -d langfuse
```

### 2. Crear cuenta de administrador

1. Accede a: `http://nouxcube.local.es:3002/auth/sign-up`
2. Crea tu cuenta con:
   - Email: `admin@nouxcube.com`
   - Password: (el que prefieras)

### 3. Crear proyecto y obtener API Keys

1. En Langfuse, ve a **Settings → API Keys**
2. Crea nuevas API Keys
3. Copia `Public Key` y `Secret Key`

### 4. Configurar variables de entorno

Edita `backend/docker/.env`:

```bash
# Langfuse Configuration
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
USE_LANGFUSE_PROMPTS=true

# Deshabilitar registro público (después de crear admin)
LANGFUSE_DISABLE_SIGNUP=true
```

### 5. Reiniciar servicios

```bash
docker compose restart emma-agent-service langfuse
```

## Seeding Prompts into Langfuse

Prompts are pushed to Langfuse via individual migration scripts in `backend/microservices/emma-agent-service/scripts/`. Each script is self-contained and push-idempotent (safe to re-run with `--force` to create new versions).

Available scripts (verified against filesystem):

```bash
# Core prompt optimization (Qwen3.5-9B tuning):
docker compose exec emma-agent-service python scripts/migrate_9b_prompt_optimization.py

# Emma's humanized reasoning prompts:
docker compose exec emma-agent-service python scripts/migrate_explain_prompts.py

# Knowledge report generation prompts:
docker compose exec emma-agent-service python scripts/migrate_knowledge_report_prompt.py

# Entity extraction (NER) prompts:
docker compose exec emma-agent-service python scripts/migrate_ner_prompts.py

# Retrieval intelligence prompts:
docker compose exec emma-agent-service python scripts/migrate_retrieval_intelligence_prompts.py

# TrustGraph phase 2 prompts:
docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py

# Guardrails (not prompts, but related):
docker compose exec emma-agent-service python scripts/seed_guardrails.py
```

Each accepts `--dry-run` (no changes), `--force` (overwrite existing), and optionally `--diff` flags. See individual script headers for details.

After seeding, promote prompts to the `production` label in the Langfuse UI (see "Production Label Pinning" below).

### Prompts (~90 total in registry)

| Categoría | Ejemplos |
|-----------|---------|
| **Core** | `emma_context_root`, `emma_planning`, `emma_synthesis` |
| **Actions** | `emma_action_generate`, `emma_action_retrieve` |
| **Sectors** | `emma_sector_legal`, `emma_sector_medical`, `emma_sector_documental` (+ generation variants) *(legacy — sectors removed 2026-03-31, unified config active)* |
| **Agents** | `emma_agent_labor`, `emma_agent_fiscal`, `emma_agent_contract`, `emma_agent_compliance`, etc. |
| **Social** | `emma_social_system_prompt`, `emma_social_group_relevance_prompt` |

## Uso Diario

### Editar un prompt

1. Accede a Langfuse: `http://nouxcube.local.es:3002`
2. Ve a **Prompts** en el menú lateral
3. Selecciona el prompt (ej: `emma_agent_labor`)
4. Edita el contenido
5. Guarda → Se crea una nueva versión automáticamente

### Usar labels para A/B testing

```
production  → Versión estable en producción
staging     → Versión en pruebas
experiment  → Versión experimental
```

Para activar una versión específica, añade el label `production` a esa versión.

### Rollback a versión anterior

1. En el prompt, ve a **Versions**
2. Selecciona la versión deseada
3. Click en **Promote to Production**

### Caché de prompts

Emma cachea los prompts por 5 minutos. Para forzar recarga:

```bash
curl -X POST "http://localhost:8009/prompts/cache/invalidate" \
  -H "X-API-Key: $MICROSERVICES_API_KEY"
```

O configura el TTL en `.env`:

```bash
LANGFUSE_PROMPT_CACHE_TTL=300  # segundos (default: 5 min)
```

## Configuración de Emma

### Variables de entorno relevantes

```bash
# Habilitar Langfuse (config.py field: langfuse_enabled)
LANGFUSE_ENABLED=true

# Prompt source toggle (passed via docker-compose.onpremise.yml)
USE_LANGFUSE_PROMPTS=true

# Conexión
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx

# Label usado por get_prompt() en runtime (default: production)
LANGFUSE_PROMPT_LABEL=production

# Caché
LANGFUSE_PROMPT_CACHE_TTL=300
```

### Missing Prompts — Fail-Fast Behavior

If a prompt is not found in Langfuse at the specified label (default `production`), `LangfusePromptClient.get_prompt()` raises `PromptNotFoundError`. There is no automatic YAML fallback — missing prompts are a hard error.

Rationale: silent fallback would mask misconfigurations. Fail-fast surfaces missing/mislabeled prompts during deployment rather than at request time.

Mitigation: always run the Langfuse seed/migration workflow (see "Seeding Prompts into Langfuse" above) after deploying a new version that introduces new prompt names.

## Production Label Pinning

All `get_prompt()` calls default to `label="production"` via the `LANGFUSE_PROMPT_LABEL` env var (default: `"production"`).

### How it works

- Admin edits a prompt in the Langfuse UI → new version is tagged `"latest"`
- Runtime `get_prompt(name)` fetches the version with label `"production"`
- New versions DO NOT reach runtime until explicitly promoted to the `"production"` label

### Why

Prevents accidentally pushing untested drafts live. Edits are staged; promotion is deliberate.

### How to promote a prompt

1. Open Langfuse UI → Prompts → select prompt
2. Switch to the **Versions** tab
3. Pick the version to promote (usually "latest")
4. Add the `"production"` label (or use the promote button)
5. Save. The change takes effect on the next `get_prompt()` call (after the cache TTL expires, typically 5 min)

### Override the label

Set `LANGFUSE_PROMPT_LABEL=staging` (or any label name) to pull prompts from a different label. Useful for dev/staging environments that want to test non-promoted versions.

## Troubleshooting

### Langfuse no arranca

```bash
# Ver logs
docker logs docker-langfuse-1 --tail=50

# Verificar base de datos
docker exec docker-db-1 psql -U nexus_user -d langfuse -c "\dt"
```

### Error "Invalid credentials"

Las API keys no coinciden. Verifica:

1. En Langfuse UI → Settings → API Keys
2. Compara con las keys en `.env`
3. Reinicia Emma: `docker restart docker-emma-agent-service-1`

### Prompts no se actualizan

El caché puede estar activo. Opciones:

```bash
# Opción 1: Esperar 5 minutos

# Opción 2: Invalidar caché
curl -X POST "http://localhost:8009/prompts/cache/invalidate"

# Opción 3: Reiniciar Emma
docker restart docker-emma-agent-service-1
```

### Login redirige a localhost

Verifica `NEXTAUTH_URL` en docker-compose:

```yaml
- NEXTAUTH_URL=http://nouxcube.local.es:3002
```

Luego recrea el contenedor:

```bash
docker compose up -d --force-recreate langfuse
```

---

## Enlaces útiles

- [Langfuse Documentation](https://langfuse.com/docs)
- [Langfuse GitHub](https://github.com/langfuse/langfuse)
- [Emma Prompts YAML](../microservices/emma-agent-service/config/prompts/emma_prompts.yaml)
- [Prompt Management Architecture](./architecture/PROMPT_MANAGEMENT.md)
