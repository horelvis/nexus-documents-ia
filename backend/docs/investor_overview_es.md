# NexusDocs360 – Resumen para Inversores

## Visión y Propuesta de Valor
- **Misión**: Convertir el conocimiento empresarial en un activo inteligente listo para la acción mediante comprensión documental autónoma.
- **Problema que resolvemos**: Las compañías pierden ~30 % del tiempo de su talento buscando o validando documentos. NexusDocs360 unifica ingestión, IA y orquestación de flujos para que legal, finanzas y operaciones tomen decisiones en minutos.
- **Por qué ahora**: Las empresas nativas de IA exigen automatización explicable y auditable. Nuestra plataforma combina RAG, agentes especializados y herramientas de cumplimiento en un stack multi-tenant desplegable en cualquier proyecto de GCP.

## Fotografía del Producto
| Dimensión | Detalles |
|-----------|----------|
| **Usuarios clave** | Equipos legales, de compliance y operaciones (50–5 000 empleados) |
| **Trabajos principales** | Revisión contractual, automatización de políticas, colaboración multiárea, orquestación de firmas |
| **Despliegue** | Backend FastAPI + frontend Next.js en Cloud Run con secretos endurecidos y CI/CD |
| **Modelo de negocio** | Suscripciones escalonadas con Stripe (Starter, Professional, Enterprise) + add-ons de IA por uso |

## Pilares Funcionales
1. **Workspace documental inteligente**
   - Soporte para PDF, DOCX, XLSX, imágenes; canal OCR + chunking.
   - Etiquetado automático, enriquecimiento de metadatos y versionado por tenant.
2. **Búsqueda cognitiva e insights**
   - Búsqueda híbrida semántica + keyword (Weaviate + Elasticsearch) aislada por tenant.
   - Q&A contextual, resúmenes y detección de anomalías con Ollama/OpenAI/Anthropic.
3. **Agentes y workflows autónomos**
   - Agentes para revisión legal, cumplimiento LGPD, firmas digitales, onboarding y extracción financiera.
   - Workflows con Temporal.io y monitoreo/alertas para jobs de larga duración.
4. **Colaboración, Compartición y Equipos**
   - Compartición segura de documentos (links expirables, marcas de agua, legal hold) y acceso federado para invitados.
   - Espacios por equipos/departamentos con aprobaciones, cuotas y feeds de actividad.
   - Directorio de proveedores de firma con reglas de ruteo, dashboards de estado y evidencias de cumplimiento.
5. **Seguridad y cumplimiento**
   - Validación de secretos al arrancar, cifrado en reposo/en tránsito, servicio de borrado GDPR/LGPD, logging estructurado y métricas Prometheus.

## Arquitectura Técnica (Resumen)
```
Clientes (UI Next.js, portal admin, clientes API)
        │
        ▼
Gateway FastAPI (Auth, Documentos, Búsqueda, Agentes, Firmas, Tenants)
        │
        ├── Servicios Core: Seguridad, Config, Cache (Redis), Métricas, Logging estructurado
        ├── Servicios de negocio: Auth, Documentos, Búsqueda, Firmas, Suscripción, Agentes IA
        │
        ▼
Capa de Datos + Tejido IA
  - PostgreSQL multi-tenant + migraciones Alembic
  - Redis (cache + rate limiting)
  - Weaviate + proxy Elysia (búsqueda semántica)
  - Cluster Elasticsearch híbrido
  - Google Cloud Storage para binarios y URLs firmadas
        │
        ▼
Microservicios (todos protegidos por `MICROSERVICES_API_KEY`)
  - CAG Service (agentes contextuales)
  - LangExtract / TextExtract (extracción LLM + determinística)
  - Temporalio Service (workflows duraderos)
  - Storage Service (abstracción GCS)
  - Engine Template Service (editor colaborativo)
  - Elasticsearch Service (analytics + búsquedas híbridas)
  - Signature Service, conversión Gotenberg, host Ollama
```

### Patrones de Resiliencia
- **Secretos zero-trust**: una revisión de Cloud Run falla si falta `MICROSERVICES_API_KEY`, `POSTGRES_*`, `REDIS_URL` o `SIGNATURE_ENCRYPTION_KEY`.
- **Operaciones estilo CQRS**: índices optimizados para lectura (Weaviate/Elasticsearch) alimentados de forma asíncrona desde Postgres.
- **Circuit breakers y fallback**: el cliente de Elasticsearch cae a consultas directas si el microservicio no responde.
- **Observabilidad total**: métricas Prometheus, logging estructurado y orquestador de health-checks con resultado por dependencia.

### Capacidades de Microservicios (Detalle)
| Servicio | Funciones | Ejemplos de entrega |
|----------|-----------|---------------------|
| **CAG Service** | Orquesta agentes contextuales (legal, fiscal, compliance) con memoria compartida. | Matriz de riesgos de un contrato, plan de onboarding para asesoría. |
| **LangExtract Service** | Extracción de entidades vía LLM con payload explicable. | Partes, importes, fechas, cláusulas, códigos médicos (ICD-10). |
| **TextExtract Service** | Parser determinista + OCR para escaneos complejos. | Texto estructurado, tablas normalizadas, mapa de redacciones. |
| **Temporalio Service** | Workflows duraderos (firmas, renovaciones, procesos asesoría). | Máquinas de estado con SLA, acciones compensatorias, alertas. |
| **Storage Service** | URLs firmadas, políticas de ciclo de vida y retención por tenant en GCS. | Endpoints de subida, snapshots de “legal hold”. |
| **Engine Template Service** | Editor colaborativo con variables, aprobaciones y auditoría. | Plantilla de carta asesoría, consentimiento hospitalario con campos dinámicos. |
| **Elasticsearch Service** | Búsqueda híbrida + analytics (keyword, semántica, agregaciones). | “Ver reportes oncológicos firmados la última semana”, puntajes de anomalía. |
| **Signature Service** | Cifra credenciales, gestiona catálogo de proveedores (YouSign en producción, DocuSign/Signaturit en beta) y enruta sobres. | Workflows multi-firma, callbacks regulatorios, paneles SLA. |
| **Gotenberg / Ollama Hosts** | Conversión a PDF y LLMs de baja latencia para reasoning. | Dossieres listos para impresión, trazas de razonamiento de agentes. |

### Workflow Clave: Firmas de Asesoría
1. **Intake** – El cliente sube estados financieros, contratos o políticas; Temporalio abre un workflow asociado al proyecto.
2. **Triaging** – LangExtract + TextExtract normalizan contenido; CAG aplica agentes fiscales/legales para detectar bloqueos.
3. **Colaboración** – Engine Template genera entregables (ej. memo al consejo). Asesores editan mientras Storage mantiene retenciones.
4. **Aprobación y Firma** – Signature Service enruta el documento a stakeholders y registra evidencia para auditorías.
5. **Entrega y Seguimiento** – El workflow emite KPIs (SLA cumplido, riesgos cerrados) y expone resúmenes al portal del cliente.

### Casos de Uso por Industria
- **Consultorías y Asesorías**
  - Due diligence: ingestión de datarooms, detección de incumplimientos, resúmenes ejecutivos.
  - ESG/Compliance: agentes validan disclosures, rellenan plantillas regulatorias, coordinan aprobaciones con el cliente.
- **Hospitales y Redes de Salud**
  - Documentación clínica: extracción de diagnósticos, tratamientos y consentimientos para EMR/billing.
  - Cumplimiento: monitoreo de políticas de retención, automatización de borrado GDPR/LGPD.
  - Juntas médicas: compartir informes anotados, firmar protocolos, archivar con trazabilidad.
- **Despachos y Departamentos Legales**
  - Ciclo contractual: extracción de cláusulas, sugerencias de redlines, firmas y búsqueda clause-level.
  - Preparación litigios: vectorizar expedientes, preguntar sobre evidencias, generar cronologías.
  - Programas de privacidad: ejecutar workflows LGPD, verificar DSARs, registrar evidencia para reguladores.

## Ventajas Competitivas
- **Stack de IA unificado**: combinamos extracción determinística y razonamiento LLM mediante agentes reutilizables.
- **Multi-tenant desde el diseño**: tenant_id atraviesa API, storage e índices vectoriales; onboarding instantáneo por organización.
- **Listo para despliegue**: pipelines de Cloud Build, plantillas de secretos y scripts Terraform reducen la puesta en marcha a <1 h.
- **Microservicios extensibles**: cada capacidad (firmas, extracción, búsqueda) escalan de forma independiente pero comparten autenticación.
- **Emma como hub inteligente**: asistente móvil respaldado por CAG + Temporal que concentra solicitudes de datos, aprobaciones, y firmas con biometría (voz/FaceID) para procesos de alta confianza.

## Tracción y Próximos Hitos
- **Estado actual**: entorno pre-producción sirviendo tenants beta con flujo ingestión → revisión por agente → firma.
- **Próximos dos trimestres**  
  1. Dashboard de analítica para inversores (uso + ROI).  
  2. Llevar los conectores de DocuSign y Signaturit a producción (YouSign ya está operativo).  
  3. Políticas de autoescalado endurecidas para Ollama/Weaviate/Elasticsearch.  
  4. Paquete de automatización de cumplimiento (borrado LGPD/GDPR + actas).

### Cumplimiento LGPD / Privacidad de Datos
- **Minimización y etiquetado de datos**: cada chunk documenta tenant_id y nivel de sensibilidad; solo los agentes permitidos acceden a él.
- **Control de consentimiento y ciclo de vida**: Storage Service aplica reglas de retención y los workflows de Temporalio registran capturas/renovaciones con checkpoints auditables.
- **Derecho al olvido automatizado**: el Servicio de Eliminación LGPD coordina apagados en Postgres, GCS, Weaviate y Elasticsearch, firmando evidencias con `SIGNATURE_ENCRYPTION_KEY`.
- **Gobernanza de acceso**: políticas basadas en roles, identidad con Clerk y caches Redis para garantizar mínimo privilegio.
- **Monitoreo y alertas**: logging estructurado + Prometheus detectan lecturas anómalas; las violaciones disparan workflows de asesoría y alertas Slack/PagerDuty.

## Llamado
Buscamos capital para acelerar go-to-market, completar certificaciones (SOC 2, ISO 27001) y escalar la infraestructura de IA. La inversión se destina a:
- Clústeres dedicados de inferencia para agentes de baja latencia.
- Conectores adicionales (SAP, Salesforce, Google Workspace) para expansión.
- Equipo de crecimiento que impulse estrategias land-and-expand en industrias reguladas.

**Contacto**: founders@nexusdocs360.app | Demo: https://pre.nexusdocs360.app

---

### Capturas sugeridas (guardar en `docs/screenshots/`)
| Archivo | Descripción |
|---------|-------------|
| `tenant-dashboard.png` | Tablero principal con métricas multi-tenant e insights de IA. |
| `document-workspace.png` | Workspace documental con metadatos, historial y controles de compartir. |
| `agent-review.png` | Vista del agente IA resaltando riesgos y recomendaciones. |
| `signature-providers.png` | Gestión de proveedores de firma (DocuSign/YouSign/Signaturit). |
| `workflow-temporal.png` | Línea de tiempo de un workflow de asesoría en Temporalio. |
| `lgpd-deletion.png` | Evidencia de borrado LGPD con estado multi-sistema. |
| `search-hybrid.png` | Resultados de búsqueda híbrida con filtros semánticos y keyword. |
| `emma-mobile.png` | Emma en app móvil mostrando solicitud de datos y aprobación biométrica (voz/FaceID). |
