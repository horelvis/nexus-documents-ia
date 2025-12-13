# Backend Architecture Review (NexusDocs360)

Fecha: 2025-12-13

## Resumen ejecutivo

El backend está bien encaminado hacia una arquitectura modular (FastAPI + routers + `services/` + microservicios), pero hoy hay **duplicidad de caminos** (sync vs async, dos verificadores de Clerk, varios “clientes HTTP” con headers distintos, 3 formas de manejar DB). Eso incrementa coste de mantenimiento, riesgo de bugs sutiles y dificulta observabilidad y seguridad consistente.

Este documento lista mejoras **priorizadas** para simplificar componentes, endurecer límites y mejorar resiliencia sin reescrituras grandes.

## Observaciones clave

### 1) Autenticación y dependencias duplicadas
- Hay dos implementaciones para validar tokens Clerk:
  - `app/services/auth_service.py` (`AuthService.verify_clerk_token`)
  - `app/api/async_dependencies.py` (`_verify_clerk_token`)
- También hay dos árboles de dependencias:
  - Sync: `app/api/dependencies.py` + `app/db/database.py`
  - Async: `app/api/async_dependencies.py` + `app/db/async_database.py`
- Además, `async_dependencies.py` declara “NO JIT Provisioning”, pero conserva helpers de JIT (`_create_user_jit`) que contradicen el flujo documentado.

Impacto: divergencia de comportamiento, dobles fixes, distinta telemetría/errores según endpoint.

Recomendación:
- Unificar verificación de Clerk en **un solo módulo** (ej. `app/core/auth/clerk.py`) y reutilizarlo desde sync/async.
- Elegir una estrategia predominante para el API (ideal: **async end-to-end**), y deprecatear el camino alternativo gradualmente.
- Eliminar o aislar el código de JIT si ya no se usa (o moverlo a un módulo explícito “legacy”).

### 2) Contrato inconsistente de auth entre microservicios
- Los clientes usan headers distintos:
  - `Authorization: Bearer <api_key>` (p.ej. `WeaviateClient`, `TemplateEditorClient`, `ElasticsearchClient`)
  - `X-API-Key: <api_key>` (p.ej. `QueueService`, `LangExtractClient`, `TextExtractionClient`, `GotenbergMicroserviceClient`)
- La dependencia `require_microservice_api_key` valida únicamente `Authorization: Bearer ...` (`app/api/dependencies.py`), pero varios servicios ya están usando `X-API-Key`.

Impacto: fricción de integración, fallos “intermitentes” por header, migraciones más costosas.

Recomendación:
- Definir un estándar único (“internal auth”) y aplicarlo:
  - Opción A (simple): `X-API-Key` + `X-Tenant-ID` + `X-User-ID`
  - Opción B (HTTP auth): `Authorization: Bearer`
- Si hay transición, soportar **ambos** temporalmente en middleware/dependency y loggear deprecación.

### 3) Capa de clientes HTTP sin base común
Patrón actual:
- Varios clientes crean `httpx.AsyncClient()` por request; otros reciben un `http_client` externo.
- Timeouts/retries/backoff no están estandarizados.
- Manejo de errores no es homogéneo: algunos devuelven `{"success": False}`; otros lanzan `HTTPException`; otros retornan `None`.

Impacto: consumo extra de sockets/handshakes, comportamiento distinto ante fallos, difícil de monitorear.

Recomendación:
- Crear un “SDK interno” mínimo: `app/clients/http.py` con:
  - `AsyncClient` único por proceso (creado en lifespan) o pool controlado
  - timeouts estándar
  - retries con backoff (p.ej. `tenacity`)
  - tipado de respuestas + errores (`ServiceUnavailableError`, `UpstreamError`, etc.)
- Los clientes concretos (weaviate/cag/langextract/...) se vuelven “thin wrappers” sobre ese SDK.

### 4) Persistencia: 3 formas de DB (alto riesgo)
Actualmente coexisten:
- `app/db/database.py` (sync engine + session + `get_async_db` ad-hoc)
- `app/db/async_database.py` (async engine + session)
- `app/db/database_proxy.py` (auto-detección + engine propio)

Impacto: posibilidad de engines distintos en runtime, pooling incoherente, bugs por “dos fuentes de verdad”.

Recomendación:
- Definir una sola fuente de verdad:
  - `app/db/async_database.py` para operaciones del API (recomendado si el proyecto ya usa async ampliamente)
  - `app/db/database.py` solo si hay endpoints sync inevitables
- Deprecar `database_proxy.py` o convertirlo en una capa pequeña que solo seleccione el URL, no que cree engines alternativos.

### 5) Startup/lifespan hace tareas “de provisioning”
En `app/core/app_config.py` se hace:
- conexión + `create_all` + migrations (condicionales)

Impacto: en producción puede generar side-effects y condiciones de carrera; en entornos escalados múltiples instancias podrían competir.

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
- [ ] Un solo verificador Clerk usado por sync/async
- [ ] Misma semántica de errores `401/403` para endpoints equivalentes
- [ ] Logs de auth sin PII/token

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
- [ ] Un solo engine por modo (sync/async) y un solo `get_*_db` por modo
- [ ] No hay creación de engines “ad-hoc” en runtime

### Fase 3 — SDK HTTP común para microservicios (1–3 días)
1. Crear cliente base:
   - Nuevo: `app/clients/http.py` con `httpx.AsyncClient` compartido + timeouts estándar.
2. Estandarizar errores y retries:
   - Retries con backoff en fallos transitivos (timeouts, 5xx).
   - Errores tipados (`UpstreamError`, `ServiceUnavailableError`).
3. Migrar clientes existentes:
   - `WeaviateClient`, `CAGClient`, `LangExtractClient`, `TextExtractionClient`, `QueueService`, etc.

Checklist:
- [ ] Todos los clientes usan el mismo handler de auth interna
- [ ] Timeouts/retries coherentes
- [ ] Respuesta/errores consistentes (sin mezclar `None`/dict/HTTPException arbitrariamente)

### Fase 4 — Startup seguro y operable (0.5–1 día)
1. Limitar side-effects en startup:
   - `create_all`/migraciones solo en dev/local con flag explícito.
2. Mover migraciones a pipeline/job:
   - Documentar comando operativo.
3. Añadir “readiness” real:
   - Healthcheck que valide dependencias críticas sin mutarlas.

### Fase 5 — Modularidad por bounded contexts (iterativo)
1. Reorganizar `services/`:
   - `services/documents/*`, `services/search/*`, `services/billing/*`, etc.
2. Reducir acoplamiento:
   - Interfaces/ports para microservicios y repositorios.
3. Contratos versionados:
   - OpenAPI por microservicio y validación de payloads.

## “Señales” concretas en el código (para navegar rápido)
- Auth/Dependencias: `backend/app/api/dependencies.py`, `backend/app/api/async_dependencies.py`, `backend/app/services/auth_service.py`
- DB: `backend/app/db/database.py`, `backend/app/db/async_database.py`, `backend/app/db/database_proxy.py`
- Clientes microservicios: `backend/app/services/*_client.py`, `backend/app/services/queue_service.py`
- Lifespan/Startup: `backend/app/core/app_config.py`
- Logging: `backend/app/core/middlewares.py`, `backend/app/core/structured_logging.py`
