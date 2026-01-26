# BOE Legal Knowledge Base - Sistema de Ingesta de Legislación Española

**Fecha**: Enero 2026
**Estado**: Producción
**Versión**: 1.0

---

## Resumen Ejecutivo

El sistema **BOE Legal Knowledge Base** permite la ingesta automática de legislación consolidada del Boletín Oficial del Estado (BOE) de España. Esta base de conocimiento legal proporciona a Emma AI contexto jurídico actualizado para análisis de documentos, compliance y asesoramiento legal.

### Capacidades Principales

| Capacidad | Descripción |
|-----------|-------------|
| **Descarga Automática** | Legislación consolidada desde API oficial del BOE |
| **Detección de Cambios** | Sincronización periódica con diff a nivel de artículo |
| **13 Dominios Legales** | Laboral, Fiscal, Civil, Mercantil, RGPD, etc. |
| **47+ Leyes Indexadas** | Cobertura de legislación empresarial española |
| **Grafo de Conocimiento** | Relaciones entre leyes en Apache AGE |
| **Búsqueda Semántica** | Consultas en lenguaje natural via Weaviate |

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BOE Legal Knowledge Base                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    BOE Official API (datosabiertos)                  │    │
│  │              https://www.boe.es/datosabiertos/api                   │    │
│  └────────────────────────────┬────────────────────────────────────────┘    │
│                               │                                              │
│                               │ XML (metadata + texto consolidado)          │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              BOE Legislation Downloader Service                      │    │
│  │  • Descarga por ID (BOE-A-XXXX-XXXXX)                               │    │
│  │  • Presets por dominio (laboral, fiscal, civil...)                  │    │
│  │  • Parsing XML → Estructura de artículos                            │    │
│  │  • Extracción de materias y referencias                             │    │
│  └───────────┬─────────────────────────────────┬───────────────────────┘    │
│              │                                 │                             │
│              ▼                                 ▼                             │
│  ┌───────────────────────────┐   ┌───────────────────────────────────┐      │
│  │    Weaviate Service       │   │     Apache AGE (PostgreSQL)       │      │
│  │   (PublicKnowledge)       │   │      (Legal Knowledge Graph)      │      │
│  │                           │   │                                   │      │
│  │ • Embeddings BGE-M3       │   │ • legal_law nodes                 │      │
│  │ • Vector search           │   │ • legal_article nodes             │      │
│  │ • Hybrid queries          │   │ • references edges                │      │
│  │ • Jurisdicción/Categoría  │   │ • amends/governed_by edges        │      │
│  └───────────┬───────────────┘   └───────────────┬───────────────────┘      │
│              │                                   │                          │
│              └───────────────┬───────────────────┘                          │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │               Legislation Sync Service                               │    │
│  │  • Polling periódico al BOE                                         │    │
│  │  • Detección de cambios (SHA256 hash)                               │    │
│  │  • Diff a nivel de artículo                                         │    │
│  │  • Clasificación de severidad                                        │    │
│  │  • Historial de versiones (Redis)                                   │    │
│  │  • Resúmenes de cambios (LLM)                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Componentes del Sistema

### 1. BOE Legislation Downloader

**Ubicación**: `backend/scripts/boe_legislation_downloader.py`

Script principal para descarga de legislación consolidada del BOE.

#### Funcionalidades

- Descarga por ID específico (BOE-A-XXXX-XXXXX)
- Descarga masiva por preset (13 categorías)
- Parsing de XML del BOE (metadata, texto, análisis)
- Extracción estructurada de artículos
- Indexación automática en Weaviate
- Detección de dominio legal desde materias

#### Uso CLI

```bash
# Descargar una ley específica
python backend/scripts/boe_legislation_downloader.py --id BOE-A-2015-11430

# Descargar todas las leyes laborales
python backend/scripts/boe_legislation_downloader.py --preset laboral

# Descargar todos los presets
python backend/scripts/boe_legislation_downloader.py --preset all

# Listar legislación disponible en BOE
python backend/scripts/boe_legislation_downloader.py --list --limit 50

# Solo descargar sin indexar
python backend/scripts/boe_legislation_downloader.py --id BOE-A-2015-11430 --no-index
```

### 2. BOE Legislation API

**Ubicación**: `backend/microservices/weaviate-service/app/api/boe_legislation.py`

API REST para gestión de legislación desde la aplicación.

#### Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/boe/presets` | GET | Listar presets disponibles |
| `/boe/presets/{name}` | GET | Detalle de un preset |
| `/boe/legislation/{boe_id}` | GET | Información de una ley |
| `/boe/download` | POST | Descargar ley por ID |
| `/boe/download/preset` | POST | Descargar preset completo |
| `/boe/search` | GET | Buscar en BOE |
| `/boe/sync/{boe_id}` | POST | Sincronizar ley y detectar cambios |
| `/boe/sync/preset/{name}` | POST | Sincronizar preset |
| `/boe/sync/all` | POST | Sincronizar toda la legislación indexada |
| `/boe/updates` | GET | Obtener actualizaciones pendientes |
| `/boe/legislation/{boe_id}/versions` | GET | Historial de versiones |
| `/boe/legislation/{boe_id}/compare` | POST | Comparar dos versiones |
| `/boe/all-legislation-ids` | GET | Obtener todos los IDs indexados |

#### Ejemplos de Uso

```bash
# Obtener información de una ley
curl http://localhost:8007/boe/legislation/BOE-A-2015-11430

# Listar presets
curl http://localhost:8007/boe/presets

# Buscar legislación
curl "http://localhost:8007/boe/search?query=contrato+laboral"

# Sincronizar una ley (requiere autenticación)
curl -X POST http://localhost:8007/boe/sync/BOE-A-2015-11430 \
  -H "Authorization: Bearer YOUR_API_KEY"

# Descargar e indexar nueva ley
curl -X POST http://localhost:8007/boe/download \
  -H "Content-Type: application/json" \
  -d '{"boe_id": "BOE-A-2015-11430", "index_to_weaviate": true}'
```

### 3. Legislation Sync Service

**Ubicación**: `backend/microservices/weaviate-service/app/services/legislation_sync_service.py`

Servicio de sincronización y detección de cambios.

#### Funcionalidades

| Funcionalidad | Descripción |
|---------------|-------------|
| **Detección de cambios** | Compara versiones usando SHA256 hash |
| **Diff de artículos** | Identifica artículos añadidos, eliminados o modificados |
| **Clasificación de severidad** | CRITICAL, HIGH, MEDIUM, LOW según impacto |
| **Historial de versiones** | Almacena todas las versiones en Redis |
| **Resúmenes automáticos** | Genera descripciones de cambios con LLM |
| **Alertas** | Notifica cambios relevantes |

#### Tipos de Cambio

```python
class ChangeType(Enum):
    ADDED = "added"           # Nuevo artículo/sección
    REMOVED = "removed"       # Artículo eliminado
    MODIFIED = "modified"     # Contenido modificado
    RENUMBERED = "renumbered" # Renumeración
    DEROGATED = "derogated"   # Derogación total/parcial
```

#### Clasificación de Severidad

| Severidad | Criterio | Ejemplo |
|-----------|----------|---------|
| **CRITICAL** | Derogación, nuevo régimen | Derogación de artículo completo |
| **HIGH** | Obligaciones, plazos, sanciones | Cambio en cuantía de multas |
| **MEDIUM** | Procedimientos, requisitos | Nuevo requisito documental |
| **LOW** | Redacción, clarificaciones | Corrección ortográfica |

### 4. Legal Knowledge Graph

**Ubicación**: `backend/scripts/sync_public_knowledge_to_legal_graph.py`

Sincronización con el grafo de conocimiento legal en Apache AGE.

#### Esquema del Grafo

**Nodos (Vertex Labels)**:

| Label | Descripción | Propiedades |
|-------|-------------|-------------|
| `legal_law` | Ley española | boe_id, title, short_name, domain, status, eli_uri |
| `legal_article` | Artículo de ley | article_id, article_number, title, summary |
| `legal_jurisdiction` | Jurisdicción | name (SPAIN, EU, REGIONAL) |
| `legal_obligation` | Obligación extraída | description, deadline, penalty |

**Relaciones (Edge Labels)**:

| Edge | Desde | Hacia | Descripción |
|------|-------|-------|-------------|
| `governed_by` | Document | legal_law | Documento regulado por ley |
| `contains_article` | legal_law | legal_article | Ley contiene artículo |
| `references` | legal_law | legal_law | Referencia entre leyes |
| `amends` | legal_law | legal_law | Ley modifica otra |
| `creates_obligation` | legal_article | legal_obligation | Artículo crea obligación |

#### Uso

```bash
# Sincronizar PublicKnowledge → Legal Graph
python backend/scripts/sync_public_knowledge_to_legal_graph.py

# Preview sin cambios
python backend/scripts/sync_public_knowledge_to_legal_graph.py --dry-run

# Limitar documentos
python backend/scripts/sync_public_knowledge_to_legal_graph.py --limit 10

# Detectar referencias entre leyes
python backend/scripts/sync_public_knowledge_to_legal_graph.py --detect-refs
```

---

## Dominios Legales y Presets

El sistema organiza la legislación en 13 dominios legales con presets predefinidos:

### Presets Disponibles

| Preset | Dominio | Leyes Incluidas |
|--------|---------|-----------------|
| `laboral` | Derecho Laboral | ET, LPRL, LISOS, LETA, LGSS, LOI, LTD |
| `fiscal` | Derecho Fiscal | LGT, LIRPF, LIS, LIVA, Reglamento Facturación |
| `civil` | Derecho Civil | Código Civil, LEC |
| `mercantil` | Derecho Mercantil | LSC, Código de Comercio, LSP |
| `administrativo` | Derecho Administrativo | LPACAP, LRJSP, LCSP |
| `proteccion_datos` | Privacidad | LOPDGDD |
| `compliance` | Compliance | LPBC, Código Penal, Ley Concursal, LSE, LAC |
| `propiedad_intelectual` | PI | LPI, Ley de Marcas, Ley de Patentes |
| `comercio_consumidores` | Consumo | LGDCU, LCD, LSSI |
| `emprendimiento` | Emprendedores | Ley de Emprendedores, Ley de Startups |
| `inmobiliario` | Inmobiliario | LAU, LPH, Ley Hipotecaria |
| `contabilidad` | Contabilidad | PGC, PGC Pymes |
| `educacion` | Educación | LOMLOE, LOU |

### Leyes Principales Indexadas

| BOE ID | Nombre Corto | Ley |
|--------|--------------|-----|
| BOE-A-2015-11430 | ET | Estatuto de los Trabajadores |
| BOE-A-2018-16673 | LOPDGDD | Protección de Datos |
| BOE-A-2003-23186 | LGT | Ley General Tributaria |
| BOE-A-1889-4763 | CC | Código Civil |
| BOE-A-2010-10544 | LSC | Ley de Sociedades de Capital |
| BOE-A-2015-10565 | LPACAP | Procedimiento Administrativo |
| BOE-A-1995-24292 | LPRL | Prevención de Riesgos Laborales |
| BOE-A-2007-20555 | LGDCU | Defensa de Consumidores |
| BOE-A-2010-6737 | LPBC | Prevención Blanqueo de Capitales |
| BOE-A-1995-25444 | CP | Código Penal |

*Total: 47+ leyes con nombres cortos mapeados*

---

## Modelo de Datos

### LegislationDocument

```python
@dataclass
class LegislationDocument:
    # Identificación
    id: str                        # BOE-A-XXXX-XXXXX
    title: str                     # Título oficial

    # Contenido
    content: str                   # Texto consolidado completo
    summary: str                   # Resumen
    bloques: List[Dict]            # Texto estructurado por secciones

    # Metadatos
    rango: str                     # Ley, Real Decreto, Orden...
    ambito: str                    # Estatal, Autonómico
    departamento: str              # Ministerio emisor

    # Fechas
    fecha_disposicion: datetime    # Fecha de la disposición
    fecha_publicacion: datetime    # Fecha de publicación en BOE
    fecha_vigencia: datetime       # Fecha de entrada en vigor

    # Estado
    estatus_derogacion: str        # N = vigente, S = derogada
    vigencia_agotada: str          # Si la vigencia ha terminado

    # URLs
    url_eli: str                   # European Legislation Identifier
    url_html: str                  # URL al texto HTML en BOE
    url_pdf: str                   # URL al PDF

    # Análisis
    materias: List[str]            # Clasificación temática
    notas: List[str]               # Notas del BOE
    referencias_anteriores: List[str]  # Leyes que modifica
    referencias_posteriores: List[str] # Leyes que la modifican
```

### ArticleChange (Detección de Cambios)

```python
@dataclass
class ArticleChange:
    article_number: str        # "34", "31bis", "DA 1ª"
    article_title: str         # Título del artículo
    change_type: ChangeType    # ADDED, REMOVED, MODIFIED...
    severity: ChangeSeverity   # CRITICAL, HIGH, MEDIUM, LOW
    old_text: str              # Texto anterior
    new_text: str              # Texto nuevo
    diff_html: str             # Diff visual HTML
    summary: str               # Resumen del cambio (LLM)
```

---

## Integración con Emma AI

El sistema BOE Legal Knowledge se integra con Emma AI a través de:

### 1. Agentes Especializados

| Agente | Uso de BOE |
|--------|-----------|
| **LaborAgent** | ET, LPRL, LISOS, LETA para análisis laboral |
| **FiscalAgent** | LGT, LIRPF, LIVA para análisis fiscal |
| **ComplianceAgent** | LOPDGDD, LPBC para verificación de compliance |
| **ContractAgent** | CC, CCom, LSC para análisis de contratos |
| **PrivacyAgent** | LOPDGDD para evaluación de privacidad |

### 2. RAG Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Query del Usuario                             │
│          "¿Qué dice el ET sobre despido improcedente?"              │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SLM Router                                      │
│  • Detecta: dominio=LABOR, ley=ET                                   │
│  • Route: HYBRID (Graph + Vector)                                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│   Apache AGE (Graph)      │  │    Weaviate (Vector)        │
│  MATCH (l:legal_law)      │  │  nearText: "despido"        │
│  WHERE l.short_name='ET'  │  │  filter: domain=LABOR       │
│  RETURN l.articles        │  │  + category=LEGISLATION     │
└──────────────────────────┘  └──────────────────────────────┘
              │                             │
              └──────────────┬──────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Context Assembly                                  │
│  • Artículos 54-56 del ET (despido disciplinario)                   │
│  • Artículo 56 ET (indemnización por despido improcedente)          │
│  • Referencias a jurisprudencia relacionada                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       LLM Response                                   │
│  "Según el artículo 56 del Estatuto de los Trabajadores..."        │
└─────────────────────────────────────────────────────────────────────┘
```

### 3. Consultas al Grafo Legal

```cypher
-- Encontrar todas las leyes que regulan contratos laborales
MATCH (l:legal_law)-[:contains_article]->(a:legal_article)
WHERE l.domain = 'LABOR' AND a.summary CONTAINS 'contrato'
RETURN l.short_name, a.article_number, a.title

-- Encontrar referencias entre leyes
MATCH (l1:legal_law)-[r:references]->(l2:legal_law)
WHERE l1.short_name = 'ET'
RETURN l1.title, r.reference_type, l2.title

-- Documentos regulados por una ley específica
MATCH (d:structural_document)-[:governed_by]->(l:legal_law)
WHERE l.boe_id = 'BOE-A-2015-11430'
RETURN d.title, d.document_type
```

---

## Configuración

### Variables de Entorno

```bash
# Weaviate (vector search)
WEAVIATE_URL=http://weaviate:8080
WEAVIATE_API_KEY=your-api-key

# Redis (version storage)
REDIS_URL=redis://redis:6379/0

# PostgreSQL + Apache AGE (graph)
POSTGRES_HOST=postgres
POSTGRES_DB=nexusdocs
AGE_GRAPH_NAME=legal_knowledge

# LLM para resúmenes de cambios
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_MODEL=Qwen/Qwen3-4B
```

### Sincronización Programada

Para mantener la legislación actualizada, configurar un cron job:

```bash
# Sincronizar toda la legislación cada domingo a las 3:00 AM
0 3 * * 0 cd /app && python scripts/boe_legislation_downloader.py --preset all

# Sincronizar leyes laborales diariamente (más frecuente)
0 4 * * * cd /app && python scripts/boe_legislation_downloader.py --preset laboral
```

---

## Flujo de Ingesta Completo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUJO DE INGESTA BOE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. DESCARGA                                                                │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  boe_legislation_downloader.py --preset laboral                  │    │
│     │     │                                                            │    │
│     │     ├─► GET /legislacion-consolidada/id/{boe_id}  (metadata)     │    │
│     │     ├─► GET /legislacion-consolidada/id/{boe_id}/texto (content) │    │
│     │     └─► GET /legislacion-consolidada/id/{boe_id}/analisis        │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  2. PROCESAMIENTO                                                           │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  • Parse XML → LegislationDocument                               │    │
│     │  • Extraer artículos con regex                                   │    │
│     │  • Detectar dominio legal desde materias                         │    │
│     │  • Generar short_name (ET, LOPDGDD, etc.)                        │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  3. INDEXACIÓN                                                              │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  Weaviate (PublicKnowledge):                                     │    │
│     │     • Crear documento con embeddings BGE-M3                      │    │
│     │     • Categoría: LEGISLATION                                     │    │
│     │     • Jurisdicción: SPAIN                                        │    │
│     │     • Metadata: boe_id, domain, dates, etc.                      │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  4. GRAFO LEGAL                                                             │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  sync_public_knowledge_to_legal_graph.py:                        │    │
│     │     • Crear nodo legal_law en Apache AGE                         │    │
│     │     • Link weaviate_uuid para conexión                           │    │
│     │     • Detectar y crear edges de referencias                      │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  5. SINCRONIZACIÓN (Periódica)                                              │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │  legislation_sync_service.sync_all():                            │    │
│     │     • Comparar hash SHA256 del texto                             │    │
│     │     • Si cambió: generar diff de artículos                       │    │
│     │     • Clasificar severidad del cambio                            │    │
│     │     • Almacenar nueva versión en Redis                           │    │
│     │     • Generar resumen con LLM                                    │    │
│     │     • Actualizar Weaviate y grafo                                │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Problemas Comunes

| Problema | Causa | Solución |
|----------|-------|----------|
| Error de conexión al BOE | Rate limiting o timeout | Añadir delay entre requests, reintentar |
| XML parsing error | Estructura inesperada | Verificar versión de API del BOE |
| Ley no encontrada | ID incorrecto | Verificar formato BOE-A-XXXX-XXXXX |
| Weaviate timeout | Documento muy largo | Incrementar timeout, chunking |
| Graph sync failed | AGE no configurado | Verificar migración de esquema |

### Verificación del Sistema

```bash
# Verificar conectividad con BOE
curl https://www.boe.es/datosabiertos/api/legislacion-consolidada?limit=1

# Verificar Weaviate
curl http://localhost:8080/v1/schema

# Verificar Apache AGE
psql -d nexusdocs -c "SELECT * FROM ag_catalog.ag_graph;"

# Contar documentos indexados
curl http://localhost:8007/public-knowledge/stats
```

---

## Referencias

1. **API del BOE**: https://www.boe.es/datosabiertos/api
2. **Documentación API**: https://www.boe.es/datosabiertos/documentos/APIconsolidada.pdf
3. **ELI (European Legislation Identifier)**: https://eur-lex.europa.eu/eli-register/about.html
4. **Weaviate Documentation**: https://weaviate.io/developers/weaviate
5. **Apache AGE**: https://age.apache.org/

---

*Documento generado: Enero 2026*
*Última actualización: 2026-01-26*
*Versión: 1.0*
