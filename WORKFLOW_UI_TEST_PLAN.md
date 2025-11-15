# Guía de Pruebas UI — Workflows con Temporalio

Este documento describe pasos reproducibles para probar, desde la UI, los workflows basados en Temporalio, junto con validaciones mínimas por API. Enfocado a pruebas manuales durante desarrollo.

## 1) Preparación

- Backend Docker y Temporalio Service corriendo.
- Frontend en modo dev.
- Variables de entorno alineadas (API URLs y API Key de microservicios).

### Comandos de inicio
- Backend + Temporalio:
  - `cd backend/docker`
  - `./start-dev.sh`
- Health checks:
  - Temporalio service: `curl http://localhost:8010/health`
  - API Core: `curl http://localhost:8000/api/v1/docs` (o health del Core si existe)
- Frontend:
  - `cd frontend`
  - Ajustar `frontend/.env.local` (local):
    - `NEXT_PUBLIC_API_URL=http://localhost:8000`
    - `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
    - `INTERNAL_API_URL=http://localhost:8000`
    - `NEXT_PUBLIC_TEMPORALIO_SERVICE_URL=http://localhost:8010`
  - `npm run dev`
  - UI: http://localhost:3000

## 2) Flujo UI básico (por tenant)

1. Inicia sesión (Clerk) y llega al dashboard.
2. Navega a Workflows: menú lateral → “WorkFlow AI” → “Process Library” (ruta `/{tenantId}/workflows`).
3. Pestaña “Plantillas”: verás al menos:
   - “Renovación de Contrato” (`contract_renewal`)
   - “Incorporación de Empleado” (`employee_onboarding`)
4. Pulsa “Iniciar” en una plantilla (usa datos demo precargados). Debe aparecer notificación de éxito.
5. Cambia a “Dashboard”: comprueba el workflow en estado “running”.
6. Opcional: en el menú “…” de la tarjeta, prueba “Cancelar” cuando esté en ejecución.
7. Espera a que complete: estado “completed” + aviso verde.
8. Pestaña “Monitor”: verifica que health y workers estén “healthy” y que la lista de activos se actualice cada 10s.

Notas:
- La página refresca automáticamente el listado (30s en Dashboard, 10s en Monitor).
- Si no aparece nada, revisa credenciales o logs (ver sección troubleshooting).

## 3) Validaciones por API (rápidas)

Usa `MICROSERVICES_API_KEY` como Bearer para el Temporalio Service.

- Listado de ejecuciones (Visibility):
  - `curl -H "Authorization: Bearer $MICROSERVICES_API_KEY" "http://localhost:8010/workflow-executions?limit=20"`
  - Filtros opcionales: `status=RUNNING`, `workflow_type=DynamicWorkflow`.
  - Si registraste Search Attributes, también: `tenant_id=<TENANT>`.
- Historial crudo de un workflow:
  - `curl -H "Authorization: Bearer $MICROSERVICES_API_KEY" "http://localhost:8010/workflow-executions/<WORKFLOW_ID>/history"`
- Plantillas (Core + fallback AI):
  - `curl -H "Authorization: Bearer $MICROSERVICES_API_KEY" "http://localhost:8010/workflow-templates"`

## 4) Aislamiento por Tenant (opcional)

Para validar aislamiento en Visibility por `TenantId`:
- Registrar Search Attributes en Temporal (una vez por clúster):
  - `tctl --namespace nexus-workflows admin cluster register-search-attribute --name TenantId --type Keyword`
- Inicia workflows en 2 tenants distintos (cambia `{tenantId}` en la URL de la app).
- Comprueba listados por tenant con `?tenant_id=<TENANT>` devolviendo sólo los del tenant.

Sin registrar Search Attributes, los workflows funcionan pero el filtro por tenant no aplica en Visibility.

## 5) Criterios de aceptación

- Se puede iniciar cada plantilla desde UI y observar su progreso en Dashboard/Monitor.
- Los workflows completan exitosamente o presentan errores visibles.
- Health del Temporalio Service y workers en “healthy”.
- El microservicio lista ejecuciones y devuelve historial crudo por API.
- Plantillas se obtienen desde Core si está disponible; si no, aparece el fallback AI.

## 6) Problemas comunes y cómo resolver

- 401 desde Temporalio Service:
  - Faltó `Authorization: Bearer <MICROSERVICES_API_KEY>` en llamadas directas.
- No aparecen workflows en UI:
  - Verifica `NEXT_PUBLIC_API_URL` y `INTERNAL_API_URL` → API en localhost:8000.
  - Revisa `docker compose logs -f temporalio-service api`.
  - Abre `http://localhost:8010/health` y confirma `healthy`.
- Filtro por tenant no funciona:
  - Aún no registraste `TenantId` como Search Attribute. Véase sección 4.
- Plantillas sólo AI, sin Core:
  - Core no disponible o sin endpoint service-to-service (`X-API-Key`). El fallback es esperado.

## 7) Datos de ejemplo (UI ya los inyecta)

- contract_renewal:
  - `contract_id`: `CONTRACT_<timestamp>`
  - `employee_name`: “Juan Pérez García”
  - `contract_type`: “Indefinido”
  - `expiration_date`: “2025-12-31”
  - `position`: “Desarrollador Senior”
- employee_onboarding:
  - `employee_id`: `EMP_<timestamp>`
  - `employee_name`: “María González López”, `position`: “Analista de Datos”

---

Checklist rápido
- [ ] Backend/Temporalio levantados y healthy
- [ ] Frontend en dev y sesión activa
- [ ] Iniciar/Cancelar workflows desde UI
- [ ] Ver estado en Dashboard y Monitor
- [ ] Listar ejecuciones por API
- [ ] Obtener historial crudo por API
- [ ] (Opcional) Validar aislamiento por tenant

