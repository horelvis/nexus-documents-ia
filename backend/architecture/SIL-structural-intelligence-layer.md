# Structural Intelligence Layer (SIL)

## Visión General

El **Structural Intelligence Layer (SIL)** es un componente revolucionario que representa un cambio de paradigma en la arquitectura RAG de NexusDocs360. En lugar de aprender el **contenido** de los documentos, el SIL aprende su **estructura** - dónde están, cómo se relacionan, qué tipo son.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PARADIGMA ANTERIOR (RAG Clásico)          →    NUEVO PARADIGMA (SIL)       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ❌ Aprender CONTENIDO de documentos       →    ✅ Aprender ESTRUCTURA       │
│  ❌ Embeddings de texto completo           →    ✅ Embeddings de estructura  │
│  ❌ Buscar documentos, luego razonar       →    ✅ Razonar estructuralmente  │
│  ❌ LLM recibe documentos completos        →    ✅ LLM recibe contexto       │
│                                                 estructural                  │
│                                                                              │
│  Idea Central:                                                               │
│  ───────────────────────────────────────────────────────────────────────    │
│  El sistema NO debe aprender "qué dice el documento"                         │
│  El sistema DEBE aprender "dónde está, cómo se relaciona, qué tipo es"      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Beneficios Clave

| Métrica | Objetivo | Descripción |
|---------|----------|-------------|
| Reducción de tokens | 70-90% | Menos contenido enviado al LLM |
| Tiempo de respuesta | < 500ms | Para queries estructurales |
| Precisión de intent | > 90% | Detección correcta del tipo de pregunta |
| Queries multi-hop | < 3s | Hasta 5 saltos en el grafo |

## Arquitectura de 5 Capas

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STRUCTURAL INTELLIGENCE LAYER (SIL)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CAPA 1: STRUCTURAL METADATA EXTRACTION                                     │
│  ═══════════════════════════════════════                                    │
│  • Extrae SOLO metadata estructural (no contenido de texto)                 │
│  • Ubicación: carpeta, site, tenant                                         │
│  • Tipo semántico: contrato, expediente, factura                            │
│  • Relaciones: versión_de, relacionado_con, hijo_de                         │
│  • Propiedades clave: fechas, identificadores, autores                      │
│                                                                              │
│  CAPA 2: STRUCTURAL GRAPH (Apache AGE)                                      │
│  ══════════════════════════════════════                                     │
│  • Grafo de ESTRUCTURA, no de contenido                                     │
│  • Nodos: Folders, Sites, Documents (solo metadata)                         │
│  • Edges: contains, version_of, relates_to, sibling_of                      │
│  • Propiedades: semantic_type, domain, importance                           │
│                                                                              │
│  CAPA 3: STRUCTURAL EMBEDDINGS (Weaviate)                                   │
│  ══════════════════════════════════════════                                 │
│  • Embeddings de DESCRIPCIONES de estructura                                │
│  • Ejemplo: "Contrato de cliente ACME en /Clientes/ACME/2024/Contratos"     │
│  • NO embeddings del texto del documento                                    │
│  • Permite búsqueda semántica sobre la estructura                           │
│                                                                              │
│  CAPA 4: PRE-LLM REASONING ENGINE                                           │
│  ═════════════════════════════════                                          │
│  • Motor de razonamiento ANTES del LLM                                      │
│  • Consultas Cypher para responder preguntas estructurales                  │
│  • "¿Cuántos contratos tiene ACME?" → Query directo, sin LLM                │
│  • "¿Qué expedientes están en RRHH?" → Navegación de grafo                  │
│                                                                              │
│  CAPA 5: LLM AS INTERPRETER                                                 │
│  ══════════════════════════                                                 │
│  • LLM recibe structural_context, NO documentos completos                   │
│  • Solo invoca RAG cuando realmente necesita CONTENIDO                      │
│  • Reduce tokens 70-90%                                                     │
│  • Respuestas más precisas basadas en contexto                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Flujo de Procesamiento

### Query Estructural Puro (BYPASS RAG)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Usuario: "¿Cuántos contratos tiene el cliente ACME del 2024?"              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PASO 1: Intent Detection                                                   │
│  ────────────────────────                                                   │
│  Tipo: STRUCTURAL (no necesita contenido)                                   │
│  Entidades: cliente=ACME, tipo=contrato, año=2024                           │
│                                                                              │
│  PASO 2: Pre-LLM Reasoning (Cypher)                                         │
│  ──────────────────────────────────                                         │
│  MATCH (d:structural_document)                                              │
│  WHERE d.tenant_id = 'xxx' AND d.prop_client = 'ACME'                       │
│    AND d.semantic_type = 'contract' AND d.prop_year = '2024'                │
│  RETURN count(d), collect(d.prop_title)                                     │
│  → Resultado: 5 contratos                                                   │
│                                                                              │
│  PASO 3: LLM Interpreta (sin RAG)                                           │
│  ────────────────────────────────                                           │
│  Input:                                                                      │
│    structural_context:                                                       │
│      query_result: {count: 5, titles: [...]}                                │
│      folder_path: /Clientes/ACME/2024/Contratos                             │
│      semantic_domain: legal                                                  │
│                                                                              │
│  Output:                                                                     │
│    "ACME tiene 5 contratos del 2024:                                        │
│     1. Contrato de servicios (firmado)                                      │
│     2. Contrato de mantenimiento (vigente)                                  │
│     ..."                                                                     │
│                                                                              │
│  🎯 NO SE LEYÓ NINGÚN DOCUMENTO - Solo metadata estructural                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Query con RAG Focalizado

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Usuario: "¿Cuáles son las cláusulas de penalización del contrato ACME?"   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PASO 1: Intent Detection                                                   │
│  ────────────────────────                                                   │
│  Tipo: CONTENT_REQUIRED (necesita leer documento)                           │
│  Contexto estructural: cliente=ACME, tipo=contrato                          │
│                                                                              │
│  PASO 2: Pre-LLM Reasoning (ubica documento)                                │
│  ───────────────────────────────────────────                                │
│  MATCH (d:structural_document {prop_client: 'ACME', semantic_type: 'contract'})│
│  RETURN d.document_id, d.folder_path                                        │
│  → doc_id: "abc123", path: /Clientes/ACME/Contratos/Master.pdf              │
│                                                                              │
│  PASO 3: RAG Focalizado (solo el documento relevante)                       │
│  ─────────────────────────────────────────────────────                      │
│  • Recupera SOLO chunks del doc_id específico                               │
│  • Busca chunks con "penalización", "penalty", "multa"                      │
│  • NO busca en todo el corpus                                               │
│                                                                              │
│  PASO 4: LLM Interpreta                                                     │
│  ─────────────────────                                                      │
│  Input:                                                                      │
│    structural_context: {document: "Contrato Master ACME", path: ...}        │
│    content_chunks: [chunk sobre cláusulas de penalización]                  │
│                                                                              │
│  🎯 RAG FOCALIZADO - Menos tokens, más precisión                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Componentes del SIL

### Ubicación del Código

```
backend/microservices/weaviate-service/app/services/sil/
├── __init__.py              # Exports y documentación del paquete
├── schemas.py               # Modelos de datos (IntentType, ReasoningType, etc.)
├── structural_extractor.py  # Extracción de metadata estructural
├── structural_embedder.py   # Embeddings de descripciones estructurales
├── intent_detector.py       # Clasificación de queries (16 tipos)
├── cypher_builder.py        # Constructor de queries Cypher
├── pre_llm_reasoning.py     # Motor de razonamiento Pre-LLM
├── temporal_reasoning.py    # Razonamiento temporal
├── multihop_planner.py      # Planificador de queries multi-hop
├── multihop_executor.py     # Ejecutor de queries multi-hop
├── sil_engine.py            # Orquestador principal
├── structural_collection.py # Colección Weaviate StructuralDocument
├── structural_graph.py      # Operaciones de grafo Apache AGE
└── rag_integration.py       # Integración con pipeline RAG
```

### Tipos de Intent Soportados

| Intent Type | Descripción | Requiere RAG |
|-------------|-------------|--------------|
| `STRUCTURAL_COUNT` | ¿Cuántos documentos de tipo X? | No |
| `STRUCTURAL_EXISTS` | ¿Existe documento X? | No |
| `STRUCTURAL_LOCATION` | ¿Dónde está el documento X? | No |
| `STRUCTURAL_LIST` | Lista de documentos en carpeta X | No |
| `TEMPORAL_POINT` | ¿Qué había en fecha X? | No |
| `TEMPORAL_RANGE` | ¿Qué cambió esta semana? | No |
| `TEMPORAL_EVOLUTION` | ¿Cómo evolucionó la carpeta? | No |
| `MULTIHOP_SIMPLE` | Documentos relacionados con X | No |
| `MULTIHOP_COMPLEX` | Contratos de clientes con tickets | No |
| `CONTENT_SUMMARY` | Resume el documento X | Sí (focalizado) |
| `CONTENT_EXTRACT` | Extrae cláusula X del contrato | Sí (focalizado) |
| `CONTENT_COMPARE` | Compara documentos X e Y | Sí (focalizado) |
| `CONTENT_SEARCH` | Busca información sobre tema X | Sí (full) |
| `HYBRID` | Combinación de estructural + contenido | Parcial |
| `UNKNOWN` | No clasificado | Sí (full) |

### Tipos de Razonamiento

| Reasoning Type | Descripción | RAG Mode |
|----------------|-------------|----------|
| `STRUCTURAL` | Respuesta puramente estructural | BYPASS |
| `TEMPORAL` | Respuesta temporal del grafo | BYPASS |
| `MULTIHOP` | Respuesta por traversal de grafo | BYPASS |
| `FOCUSED_RAG` | RAG sobre documentos específicos | FOCUSED |
| `FULL_RAG` | RAG sobre todo el corpus | FULL |
| `HYBRID` | Combinación estructural + RAG | AUGMENTED |

## API Endpoints

### POST `/sil/query`

Query estructural con Pre-LLM Reasoning.

**Request:**
```json
{
  "query": "¿Cuántos contratos tiene ACME?",
  "tenant_id": "tenant-123",
  "include_context": true
}
```

**Response:**
```json
{
  "original_query": "¿Cuántos contratos tiene ACME?",
  "reasoning_type": "structural",
  "requires_rag": false,
  "answer": "ACME tiene 5 contratos.",
  "answer_confidence": 0.92,
  "structural_context": "...",
  "target_document_ids": [],
  "processing_time_ms": 45.2,
  "tokens_saved": 12500,
  "success": true
}
```

### POST `/sil/index-structural`

Indexar metadata estructural de un documento.

**Request:**
```json
{
  "document_id": "doc-123",
  "tenant_id": "tenant-123",
  "file_path": "/Clientes/ACME/2024/Contratos/Master.pdf",
  "connector_metadata": {
    "title": "Contrato Master ACME",
    "author": "Legal Department"
  },
  "learned_context": {
    "domain": "legal",
    "folder_semantics": {"department": "ventas"}
  }
}
```

### GET `/sil/structure/{document_id}`

Obtener metadata estructural de un documento.

### GET `/sil/graph/stats`

Estadísticas del grafo estructural.

**Response:**
```json
{
  "tenant_id": "tenant-123",
  "total_documents": 1250,
  "total_folders": 89,
  "types_breakdown": {
    "contract": 245,
    "invoice": 412,
    "report": 198,
    "unknown": 395
  }
}
```

### POST `/sil/search-structural`

Búsqueda semántica sobre descripciones estructurales.

### GET `/sil/folder/{folder_path}`

Contenido de una carpeta estructural.

### GET `/sil/related/{document_id}`

Documentos relacionados via traversal de grafo.

## Modelo de Datos

### Weaviate: StructuralDocument Collection

```python
properties = [
    # Identificadores
    "document_id",           # UUID del documento original
    "weaviate_document_id",  # UUID en colección de chunks
    "tenant_id",
    "connector_id",

    # Clasificación estructural
    "semantic_type",         # contract, invoice, report, etc.
    "domain",                # legal, hr, finance, etc.
    "importance",            # 0.0-1.0

    # Jerarquía y ubicación
    "folder_path",           # /Clientes/ACME/2024/Contratos
    "folder_hierarchy",      # ["Clientes", "ACME", "2024", "Contratos"]
    "site_name",

    # Descripción estructural (vectorizada)
    "structural_description",  # Texto para embedding

    # Propiedades extraídas
    "prop_title",
    "prop_client",
    "prop_year",
    "prop_author",
    "prop_version",
    "prop_status",
    "prop_expiry_date",

    # Semántica de carpeta (aprendida)
    "folder_department",
    "folder_purpose",
    "folder_confidentiality",

    # Propiedades temporales
    "valid_from",            # Cuándo entró en la estructura
    "valid_to",              # Cuándo salió (null = actual)
    "created_at",
    "modified_at",
    "source_modified_at",

    # Relaciones
    "related_document_ids",
    "version_of_id",
    "version_number",
]
```

### Apache AGE: Graph Schema

**Vertex Labels:**
- `structural_document` - Nodo de documento
- `structural_folder` - Nodo de carpeta
- `structural_site` - Nodo de site/fuente

**Edge Labels:**
- `contains` - Carpeta contiene documento/subcarpeta
- `version_of` - Documento es versión de otro
- `relates_to` - Documentos relacionados semánticamente
- `sibling_of` - Documentos en la misma carpeta

**Propiedades de Nodos:**
```cypher
CREATE (d:structural_document {
  document_id: 'doc-123',
  tenant_id: 'tenant-123',
  weaviate_id: 'wv-abc',
  semantic_type: 'contract',
  domain: 'legal',
  folder_path: '/Clientes/ACME/2024/Contratos',
  prop_title: 'Contrato Master ACME',
  prop_client: 'ACME',
  prop_year: '2024',
  importance: 0.9,
  valid_from: '2024-01-15T10:30:00',
  valid_to: null,
  created_at: '2024-01-15T10:30:00',
  modified_at: '2024-06-20T14:00:00'
})
```

## Temporal Awareness

El SIL soporta queries temporales que aprovechan los campos `valid_from` y `valid_to`:

### Point-in-Time Queries
```
"¿Qué documentos tenía RRHH el 1 de enero?"
```

### Range Queries
```
"¿Qué documentos se añadieron esta semana?"
"¿Qué cambió desde mi última sesión?"
```

### Evolution Queries
```
"¿Cómo ha evolucionado la carpeta de Contratos este año?"
```

### Diff Queries
```
"Compara la estructura ahora vs hace 3 meses"
```

## Multi-Hop Reasoning

El SIL permite queries que atraviesan múltiples relaciones del grafo:

### Ejemplo: 2 Hops
```
"Contratos de clientes que también tienen tickets de soporte"
→ Cliente -[HAS_CONTRACT]-> Contrato
→ Cliente -[HAS_TICKET]-> Ticket
→ Intersección: clientes con ambos
```

### Ejemplo: 3 Hops
```
"Documentos creados por personas del departamento de Juan"
→ Juan -[WORKS_IN]-> Departamento
→ Departamento -[HAS_MEMBER]-> Personas
→ Personas -[CREATED]-> Documentos
```

### Límites y Timeouts

| Complejidad | Timeout | Max Results |
|-------------|---------|-------------|
| 1 hop | 1000ms | 100 |
| 2 hops | 2000ms | 100 |
| 3 hops | 3000ms | 100 |
| 4 hops | 4000ms | 100 |
| 5 hops | 5000ms | 100 |

## Integración con RAG Pipeline

El SIL se integra como "Layer 4.5" en el pipeline RAG existente:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RAG Pipeline                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 0: Graph-Enhanced Query Expansion (Knowledge Graph)          │
│  Layer 1: Dense Vector Search (50 candidates)                       │
│  Layer 2: Sparse BM25 Search (50 candidates)                        │
│  Layer 3: RRF Fusion (combine results)                              │
│  Layer 4: Semantic Reranking (20 results)                           │
│                                                                      │
│  ▶ Layer 4.5: SIL Pre-LLM Reasoning (NUEVO)                         │
│     │                                                                │
│     ├─ BYPASS: Respuesta estructural, sin RAG                       │
│     ├─ FOCUSED: RAG solo sobre documentos identificados             │
│     ├─ AUGMENTED: RAG completo + contexto estructural               │
│     └─ FULL: RAG normal (SIL no aplicable)                          │
│                                                                      │
│  Layer 5: Context Fusion (group by document, diversify)             │
│  Layer 6: Context Assembly (format for LLM)                         │
│  Layer 7: Response Generation (LLM)                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### RAG Modes

| Mode | Descripción | Tokens |
|------|-------------|--------|
| `BYPASS` | No RAG, respuesta directa del grafo | ~200 |
| `FOCUSED` | RAG solo sobre docs específicos | ~2000-5000 |
| `AUGMENTED` | RAG full + contexto estructural | ~8000-12000 |
| `FULL` | RAG tradicional sin SIL | ~12000-28000 |

## Uso Programático

### Query Estructural

```python
from app.services.sil import sil_engine

# Process a query
result = await sil_engine.process_query(
    query="¿Cuántos contratos tiene ACME del 2024?",
    tenant_id="tenant-123",
)

# Check result
if result.reasoning_result.type == ReasoningType.STRUCTURAL:
    # Pure structural answer - no RAG needed
    print(f"Answer: {result.answer}")
    print(f"Confidence: {result.answer_confidence}")
    print(f"Tokens saved: {result.tokens_saved}")
else:
    # Need RAG, but possibly focused
    target_docs = result.reasoning_result.target_document_ids
    context = result.context_for_llm
```

### Indexar Metadata Estructural

```python
from app.services.sil import structural_extractor, structural_collection, structural_graph

# Extract metadata
metadata = await structural_extractor.extract_structural_metadata(
    document_id="doc-123",
    file_path="/Clientes/ACME/2024/Contratos/Master.pdf",
    connector_metadata={"title": "Contrato Master"},
    learned_context={"domain": "legal"},
)

# Index to Weaviate
weaviate_id = await structural_collection.index_structural_metadata(
    metadata=metadata,
    document_id="doc-123",
    tenant_id="tenant-123",
)

# Index to Graph
await structural_graph.add_structural_document(
    document_id="doc-123",
    tenant_id="tenant-123",
    metadata=metadata,
)
```

### Integración con RAG

```python
from app.services.sil import sil_rag_integration, RAGMode

# Pre-process query through SIL
sil_result = await sil_rag_integration.pre_process(
    query="¿Cuál es la cláusula de penalización?",
    tenant_id="tenant-123",
)

if sil_result.mode == RAGMode.BYPASS:
    # Return direct answer
    return sil_result.direct_answer

elif sil_result.mode == RAGMode.FOCUSED:
    # Use document filter for RAG
    filter = sil_rag_integration.create_document_filter(sil_result)
    # Pass to retriever with filter...

else:
    # Full RAG with optional structural context
    context = sil_result.structural_context
    # Include context in assembled prompt...
```

## Migración de Base de Datos

El SIL incluye una migración Alembic para crear los labels de Apache AGE:

```
backend/alembic/versions/20260120_add_sil_graph_schema.py
```

Esta migración:
1. Verifica que Apache AGE esté disponible
2. Crea vertex labels: `structural_document`, `structural_folder`, `structural_site`
3. Crea edge labels: `contains`, `version_of`, `relates_to`, `sibling_of`

## Testing

### Tests de Integración Sugeridos

1. **Query estructural puro:**
   ```
   Input: "¿Cuántos contratos tiene ACME?"
   Expected: Respuesta vía Cypher, 0 tokens de contenido
   ```

2. **Query que requiere contenido:**
   ```
   Input: "¿Cuál es la cláusula de penalización del contrato ACME?"
   Expected: RAG focalizado a 1 documento, no todo el corpus
   ```

3. **Query temporal (punto en tiempo):**
   ```
   Input: "¿Cuántos documentos tenía RRHH el 1 de enero?"
   Expected: Query con filtro temporal, resultado histórico correcto
   ```

4. **Query multi-hop:**
   ```
   Input: "Contratos de clientes que tienen tickets abiertos"
   Expected: Query Cypher de 2 saltos, < 500ms
   ```

## Monitoreo y Métricas

El SIL genera logs estructurados para monitoreo:

```
🧠 SIL Processing: 'How many contracts...' → Intent: STRUCTURAL_COUNT (confidence: 0.95)
📊 SIL Summary:
  Type: structural
  Requires RAG: false
  Time: 45ms
  Tokens saved: ~12500
  Direct answer: ACME tiene 5 contratos.
```

### Métricas Clave

- `sil_queries_total` - Total de queries procesados
- `sil_bypass_ratio` - % queries respondidos sin RAG
- `sil_processing_time_ms` - Tiempo de procesamiento
- `sil_tokens_saved_total` - Tokens ahorrados acumulados
- `sil_intent_detection_accuracy` - Precisión de detección

## Consideraciones de Seguridad

1. **Tenant Isolation**: Todas las queries incluyen `tenant_id` como filtro
2. **SQL Injection**: Los valores se escapan antes de Cypher
3. **Timeout Protection**: Queries multi-hop tienen timeouts adaptativos
4. **Result Limits**: Máximo 100 resultados para prevenir memory issues

## Roadmap Futuro

1. **Aprendizaje de patrones estructurales** - Detectar automáticamente convenciones de nombrado
2. **Predicción de relaciones** - Sugerir documentos relacionados
3. **Optimización de queries** - Cache de queries frecuentes
4. **Visualización de grafo** - UI para explorar estructura

---

*Documentación actualizada: 2026-01-20*
