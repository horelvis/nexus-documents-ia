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
│         │                                                    │
│         └──→ YAML Fallback (si Langfuse no disponible)      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Langfuse (Puerto 3002)                    │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Prompts   │  │  Versions   │  │   Observability     │  │
│  │   (32+)     │  │  & Labels   │  │   & Metrics         │  │
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

## Migración de Prompts

### Migrar prompts de YAML a Langfuse

Los prompts de Emma están originalmente en `emma_prompts.yaml`. Para migrarlos a Langfuse:

```bash
cd backend

# Preview (sin cambios)
LANGFUSE_HOST=http://localhost:3002 \
LANGFUSE_PUBLIC_KEY=<tu-public-key> \
LANGFUSE_SECRET_KEY=<tu-secret-key> \
python3 scripts/migrate_prompts_to_langfuse.py --dry-run

# Migración real
LANGFUSE_HOST=http://localhost:3002 \
LANGFUSE_PUBLIC_KEY=<tu-public-key> \
LANGFUSE_SECRET_KEY=<tu-secret-key> \
python3 scripts/migrate_prompts_to_langfuse.py
```

### Prompts migrados (32 total)

| Categoría | Prompts |
|-----------|---------|
| **Core** | `emma_context_root` |
| **Actions** | `emma_action_generate`, `emma_action_retrieve` |
| **System** | `emma_planning`, `emma_synthesis` |
| **Sectors** | `emma_sector_legal`, `emma_sector_medical`, `emma_sector_documental` (+ generation variants) |
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
# Habilitar Langfuse
LANGFUSE_ENABLED=true
USE_LANGFUSE_PROMPTS=true

# Conexión
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx

# Caché
LANGFUSE_PROMPT_CACHE_TTL=300
```

### Fallback a YAML

Si Langfuse no está disponible, Emma usa automáticamente el archivo YAML:

```
microservices/emma-agent-service/config/prompts/emma_prompts.yaml
```

Este fallback es transparente y no requiere configuración.

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
