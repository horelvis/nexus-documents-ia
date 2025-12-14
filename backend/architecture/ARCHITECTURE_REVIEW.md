# Backend Architecture Review (NexusDocs360)

Fecha: 2025-12-13

## Resumen ejecutivo

El backend está bien encaminado hacia una arquitectura modular (FastAPI + routers + `services/` + microservicios). Ya se corrigieron puntos críticos de consistencia (auth Clerk y DB async), pero aún quedan **áreas parcialmente homogenizadas** (clientes HTTP y organización por bounded contexts). También se alineó configuración hacia **vLLM** y se eliminaron referencias a microservicios retirados (Temporalio/Ollama) en los artefactos de despliegue.

Este documento lista mejoras **priorizadas** para simplificar componentes, endurecer límites y mejorar resiliencia sin reescrituras grandes.

## Estado de implementación (por fases)

- Fase 0 (alineación de auth interna): **Parcial** (dependency acepta `X-API-Key` y `Authorization: Bearer`).
- Fase 1 (Auth Clerk unificada): **Aplicada** (un solo módulo, usado por sync/async).
- Fase 2 (DB async como fuente de verdad): **Aplicada** (sin `database_proxy.py`, sesiones async consistentes).
- Fase 3 (SDK HTTP común): **Parcial** (`app/clients/*` existe; migración de clientes en curso).
- Fase 4 (Startup seguro): **Parcial** (sin side-effects y con redacción de credenciales; falta endurecer “readiness”).
- Fase 5 (bounded contexts): **Pendiente** (servicios siguen planos).

## Observaciones clave

### 1) Autenticación y dependencias duplicadas
- La verificación Clerk está **unificada** en `app/core/auth/clerk.py` y se consume desde:
  - `backend/app/api/async_dependencies.py` (principal para endpoints async)
  - `backend/app/api/dependencies.py` (legacy, deprecado)
  - `backend/app/services/auth_service.py` (delegación)
- El camino sync permanece por compatibilidad, pero el flujo recomendado es **async end-to-end**.

Pendiente:
- Reducir uso del árbol sync a casos estrictamente necesarios (y documentar el “por qué”).

### 2) Contrato inconsistente de auth entre microservicios
- `require_microservice_api_key` ahora acepta únicamente:
  - `X-API-Key: <api_key>`
- Aún hay clientes no migrados que construyen headers manualmente en `backend/app/services/*_client.py`.

Pendiente:
- Migrar todos los clientes internos a `X-API-Key` + headers de contexto.
- Eliminar cualquier dependencia de `Authorization: Bearer` para auth interna (retirado del backend y microservicios principales; revisar wrappers legacy si existieran).

### 3) Capa de clientes HTTP sin base común
Ya existe un SDK interno base en `backend/app/clients/`:
- `backend/app/clients/base.py` (`BaseHTTPClient`, retries/backoff, headers estándar)
- `backend/app/clients/config.py` (timeouts/retries/headers)
- `backend/app/clients/exceptions.py` (errores tipados)

Estado:
- Migrados a `BaseHTTPClient`:
  - `backend/app/services/template_editor_client.py`
  - `backend/app/services/cag_client.py`
  - `backend/app/services/langextract_client.py`
  - `backend/app/services/weaviate_client.py`
  - `backend/app/services/text_extraction_client.py`
  - `backend/app/services/signature_microservice_client.py`
  - `backend/app/services/elasticsearch_client.py`
  - `backend/app/services/gotenberg_microservice_client.py` (GotenbergClient)
  - `backend/app/services/async_storage_client.py` (AsyncStorageClient)

- Endpoints migrados de StorageService (sync) a AsyncStorageService:
  - `backend/app/api/v1/storage.py`
  - `backend/app/api/v1/signature_ai.py`
  - `backend/app/api/v1/admin.py`
  - `backend/app/services/document_preview_service.py`

- Deprecated (pendientes de eliminar en próxima iteración):
  - `backend/app/services/storage_client.py` (sync) → usar AsyncStorageClient
  - `backend/app/services/storage_service.py` (sync) → usar AsyncStorageService
  - `backend/app/services/storage_factory.py` (sync) → usar AsyncStorageServiceFactory

Pendiente:
- Migrar `document_service.py` y `reindex_service.py` para usar versiones async del storage.

### 4) Persistencia: 3 formas de DB (alto riesgo)
Se consolidó `backend/app/db/async_database.py` como fuente de verdad para el API:
- `database_proxy.py` eliminado.
- `get_async_db` único y `async_session_context()` para uso fuera de dependencias de FastAPI.

### 5) Startup/lifespan hace tareas “de provisioning”
En `app/core/app_config.py` antes se hacía:
- conexión + `create_all` + migraciones (condicionales)

Estado:
- Startup ahora solo valida conectividad de DB (sin `create_all`/migraciones en boot).
- Logs de DB redaccionados para evitar fuga de credenciales.

Recomendación:
- En producción: startup solo valida conectividad + readiness.
- Migrations/DDL: en pipeline (job) o herramienta operativa, no en boot.
- Mantener un flag de bootstrap para dev/local (ya existe `DB_AUTO_MIGRATE`).

### 6) Observabilidad/logging redundante
Existe:
- middleware de request logging detallado
- `StructuredLogger` + `RequestContextMiddleware`
- logs “verbosos” en dependencias (`get_current_user`) y en `AuthService.verify_clerk_token`

Impacto: ruido, costo, potencial de filtrar información sensible, dificultad para correlacionar.

Recomendación:
- Centralizar logging de auth en un solo lugar:
  - log level `DEBUG` para headers/contexto
  - nunca loggear tokens completos ni payloads completos
- Normalizar “correlation id” (`X-Request-Id`) y propagarlo a microservicios.

### 7) Configuración (`Settings`) demasiado amplia
`app/core/config.py` concentra muchas variables de negocio e infraestructura.

Impacto: mayor acoplamiento, más difícil de testear, mayor riesgo de “config drift”.

Recomendación:
- Separar settings por dominio, sin romper imports:
  - `SettingsDatabase`, `SettingsAuth`, `SettingsServices`, `SettingsAI`, etc.
- Mantener un “facade” `settings` que compone para no cambiar todo el codebase en una sola PR.

### 8) Alineación de servicios (Temporalio/Ollama retirados; vLLM)
Estado:
- Se retiraron referencias a `TEMPORALIO_SERVICE_URL` y `OLLAMA_BASE_URL` en despliegue y ejemplos (`backend/cloud-run-backend.yaml`, `backend/.env.example`, `backend/docker/docker-compose.yml`).
- `LLM_PROVIDER` por defecto pasa a `vllm` en `backend/app/core/config.py`.

## Recomendaciones priorizadas (próximas 1–3 iteraciones)

### P0 (seguridad/correctitud)
1. Unificar verificación de Clerk (un solo módulo, cache de JWKS, sin logs sensibles).
2. Estandarizar header de auth entre microservicios (y soportar transición si hace falta).
3. Consolidar estrategia DB (quitar fuentes alternativas de engine/session).

### P1 (mantenibilidad/resiliencia)
4. SDK HTTP común para microservicios (timeouts + retries + errores tipados).
5. Router composition sin imports con side-effects (función `register_routes(app)` y módulos por dominio).
6. Rate limiting real en Redis para producción (el in-memory actual es solo dev).

### P2 (evolución)
7. Separar `services/` por bounded contexts (documents/search/tenants/billing/integrations) y reducir clases “god service”.
8. Contratos de microservicios (OpenAPI/JSON schema) versionados y validados.

## Pasos de mejora (plan incremental)

Objetivo: mejorar arquitectura **sin reescrituras grandes**, manteniendo compatibilidad y reduciendo riesgo.

### Fase 0 — Alineación (0.5–1 día)
1. Definir estándar de auth interna entre microservicios:
   - Decidir `X-API-Key` **o** `Authorization: Bearer`.
   - Definir headers de contexto: `X-Tenant-Id`, `X-User-Id`, `X-Request-Id`.
2. Congelar criterios de “done”:
   - Todos los clientes usan el mismo esquema.
   - Todos los endpoints internos aceptan el esquema (y opcionalmente uno legacy durante transición).

### Fase 1 — Auth unificada (1–2 días)
1. Crear un módulo único de Clerk:
   - Nuevo: `app/core/auth/clerk.py` (verificar JWT, cache JWKS, errores normalizados).
2. Reemplazar duplicados:
   - `app/services/auth_service.py` y `app/api/async_dependencies.py` deben delegar al módulo común.
3. Reducir logs sensibles:
   - No loggear tokens ni payloads completos.
   - Loggear solo `request_id`, `clerk_user_id` (si aplica) y resultado.

Checklist:
- [x] Un solo verificador Clerk usado por sync/async
- [x] Misma semántica de errores `401/403` para endpoints equivalentes
- [x] Logs de auth sin PII/token

### Fase 2 — DB: una sola “fuente de verdad” (1–3 días)
1. Elegir estrategia predominante:
   - Recomendado: **async end-to-end** (FastAPI + SQLAlchemy async).
2. Consolidar sesiones:
   - Mantener `app/db/async_database.py` como fuente principal.
   - Reducir/eliminar `database_proxy.py` (o dejarlo solo para resolver URL, no para crear engines alternativos).
3. Ajustar dependencias:
   - Endpoints y servicios deben depender de `AsyncSession` cuando sea posible.
   - Mantener un “compat layer” temporal si quedan endpoints sync.

Checklist:
- [x] Un solo engine por modo (sync/async) y un solo `get_*_db` por modo
- [x] No hay creación de engines “ad-hoc” en runtime

### Fase 3 — SDK HTTP común para microservicios (1–3 días)
1. Crear cliente base:
   - Ya existe: `backend/app/clients/base.py` + `backend/app/clients/config.py` + `backend/app/clients/exceptions.py`.
2. Estandarizar errores y retries:
   - Retries con backoff en fallos transitivos (timeouts, 5xx).
   - Errores tipados (`UpstreamError`, `ServiceUnavailableError`).
3. Migrar clientes existentes:
   - `WeaviateClient`, `CAGClient`, `LangExtractClient`, `TextExtractionClient`, `QueueService`, etc.

Checklist:
- [x] Todos los clientes usan el mismo handler de auth interna (X-API-Key via BaseHTTPClient)
- [x] Timeouts/retries coherentes (presets: fast/default/document/ai/long/upload)
- [x] Respuesta/errores consistentes (excepciones tipadas en `app/clients/exceptions.py`)
- Progreso: **COMPLETADO** - todos los clientes migrados a BaseHTTPClient; sync storage deprecated.

### Fase 4 — Startup seguro y operable (0.5–1 día)
1. Limitar side-effects en startup:
   - `create_all`/migraciones solo en dev/local con flag explícito.
2. Mover migraciones a pipeline/job:
   - Documentar comando operativo.
3. Añadir “readiness” real:
   - Healthcheck que valide dependencias críticas sin mutarlas.

Checklist:
- [x] Startup sin side-effects (sin DDL/migraciones en boot)
- [x] Redacción de credenciales en logs de DB
- [ ] Readiness que valide dependencias críticas (por ejemplo: Redis/Weaviate/Elasticsearch según flags)

### Fase 5 — Modularidad por bounded contexts (iterativo)
1. Reorganizar `services/`:
   - `services/documents/*`, `services/search/*`, `services/billing/*`, etc.
2. Reducir acoplamiento:
   - Interfaces/ports para microservicios y repositorios.
3. Contratos versionados:
   - OpenAPI por microservicio y validación de payloads.

## “Señales” concretas en el código (para navegar rápido)
- Auth/Dependencias: `backend/app/api/dependencies.py`, `backend/app/api/async_dependencies.py`, `backend/app/services/auth_service.py`
- DB: `backend/app/db/async_database.py` (principal) y `backend/app/db/database.py` (legacy sync)
- Clientes microservicios: `backend/app/services/*_client.py`, `backend/app/services/queue_service.py`
- Lifespan/Startup: `backend/app/core/app_config.py`
- Logging: `backend/app/core/middlewares.py`, `backend/app/core/structured_logging.py`
