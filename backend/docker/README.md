# Docker Setup for Nexus Document Backend

This directory contains Docker configurations for running the Nexus Document Backend microservices architecture.

## Quick Start

### Fast Development Mode (Recommended for active development)
```bash
./start-dev-fast.sh
```
**Best for:** Maximum development speed with instant code changes

### Standard Development Mode
```bash
./start-dev.sh
```
**Best for:** When you need to modify dependencies or Dockerfiles

### Production Mode
```bash
./start-prod.sh
```

---

## 💻 Requisitos de Hardware

### Resumen Ejecutivo

| Escenario | CPU | RAM | GPU VRAM | Almacenamiento | Usuarios |
|-----------|-----|-----|----------|----------------|----------|
| **Desarrollo** | 8 cores | 32GB | 12GB | 100GB SSD | 1-5 |
| **Producción Pequeña** | 16 cores | 64GB | 24GB | 500GB NVMe | 10-50 |
| **Producción Media** | 32 cores | 128GB | 48GB (2x24) | 1TB NVMe | 50-200 |
| **Enterprise** | 64+ cores | 256GB+ | 80GB+ (multi) | 2TB+ NVMe RAID | 200+ |

---

### 🔧 Desarrollo / Pruebas Locales

**Perfil:** Desarrollador individual o equipo pequeño de QA

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MÍNIMO (Funcional pero lento)                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  CPU:         Intel i5-10400 / AMD Ryzen 5 3600 (6 cores)                   │
│  RAM:         16GB DDR4                                                      │
│  GPU:         NVIDIA RTX 3060 12GB                                          │
│  Disco:       256GB SSD SATA                                                │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ⚠️  Limitaciones:                                                           │
│     - Solo modelo Qwen3-4B (no modelos más grandes)                         │
│     - Sin TTS local (usar Google TTS)                                       │
│     - Embeddings en CPU (lento)                                             │
│     - 1-2 usuarios concurrentes máximo                                      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  RECOMENDADO (Experiencia fluida)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  CPU:         Intel i7-12700 / AMD Ryzen 7 5800X (8-12 cores)               │
│  RAM:         32GB DDR4-3200                                                │
│  GPU:         NVIDIA RTX 4070 Ti 12GB o RTX 3090 24GB                       │
│  Disco:       512GB NVMe Gen4                                               │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ✅ Beneficios:                                                              │
│     - Qwen3-4B + BGE-M3 embeddings en GPU                                   │
│     - TTS local (VibeVoice)                                                 │
│     - 3-5 usuarios concurrentes                                             │
│     - Tiempos de respuesta < 3s para RAG                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  ÓPTIMO (Desarrollo intensivo + demos)                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  CPU:         Intel i9-13900K / AMD Ryzen 9 7950X (16-24 cores)             │
│  RAM:         64GB DDR5-5600                                                │
│  GPU:         NVIDIA RTX 4090 24GB                                          │
│  Disco:       1TB NVMe Gen4 + 2TB HDD para datos                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  ✅ Beneficios:                                                              │
│     - Qwen3-8B o modelos más grandes                                        │
│     - Contexto extendido (32K+ tokens)                                      │
│     - 5-10 usuarios concurrentes                                            │
│     - Tiempos de respuesta < 2s para RAG                                    │
│     - Ideal para demos a clientes                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 🏢 Producción On-Premise (Pequeña - 10-50 usuarios)

**Perfil:** PYME, departamento corporativo, startup

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SERVIDOR ÚNICO (Todo-en-uno)                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  CPU:         Intel Xeon W-2255 / AMD EPYC 7313 (16 cores)                  │
│  RAM:         64GB ECC DDR4-3200                                            │
│  GPU:         NVIDIA RTX 4090 24GB o A4000 16GB                             │
│  Disco:       1TB NVMe (OS+Apps) + 2TB NVMe (Datos)                         │
│  Red:         10GbE                                                         │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Distribución de recursos:                                                   │
│     PostgreSQL + AGE:    8GB RAM                                            │
│     Redis:               2GB RAM                                            │
│     Weaviate:            8GB RAM                                            │
│     Elasticsearch:       8GB RAM                                            │
│     vLLM + Embeddings:   16GB RAM + 24GB VRAM                               │
│     Microservicios:      16GB RAM                                           │
│     Sistema:             6GB RAM                                            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Estimación de costos:                                                       │
│     Hardware:           ~$8,000 - $12,000 USD                               │
│     Mantenimiento/año:  ~$1,500 USD                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 🏛️ Producción On-Premise (Media - 50-200 usuarios)

**Perfil:** Empresa mediana, múltiples departamentos

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ARQUITECTURA DISTRIBUIDA (2-3 servidores)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  │
│  │   SERVIDOR APP      │  │   SERVIDOR AI/ML    │  │   SERVIDOR DATA     │  │
│  │   ───────────────   │  │   ───────────────   │  │   ───────────────   │  │
│  │   CPU: 16 cores     │  │   CPU: 16 cores     │  │   CPU: 16 cores     │  │
│  │   RAM: 64GB         │  │   RAM: 64GB         │  │   RAM: 128GB        │  │
│  │   GPU: -            │  │   GPU: 2x RTX 4090  │  │   GPU: -            │  │
│  │   Disco: 500GB NVMe │  │   Disco: 1TB NVMe   │  │   Disco: 4TB NVMe   │  │
│  │   ───────────────   │  │   ───────────────   │  │   ───────────────   │  │
│  │   • Main API        │  │   • vLLM Server     │  │   • PostgreSQL+AGE  │  │
│  │   • Microservices   │  │   • Embeddings      │  │   • Weaviate        │  │
│  │   • Background      │  │   • TTS Service     │  │   • Elasticsearch   │  │
│  │     Worker          │  │                     │  │   • Redis Cluster   │  │
│  │   • KeyCloak        │  │                     │  │   • Backups         │  │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  │
│                                                                              │
│  Estimación de costos:                                                       │
│     Hardware:           ~$25,000 - $40,000 USD                              │
│     Mantenimiento/año:  ~$5,000 USD                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 🏗️ Enterprise (200+ usuarios)

**Perfil:** Gran empresa, despliegue multi-sede, alta disponibilidad

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ARQUITECTURA ENTERPRISE (Kubernetes / HA)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Cluster Kubernetes (mínimo 5 nodos):                                        │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  NODOS CONTROL PLANE (3x)                                             │   │
│  │  CPU: 8 cores | RAM: 32GB | Disco: 256GB NVMe                        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  NODOS WORKER - APP (3-5x)                                            │   │
│  │  CPU: 32 cores | RAM: 128GB | Disco: 1TB NVMe                        │   │
│  │  Servicios: API, Microservices, Workers, KeyCloak                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  NODOS WORKER - GPU (2-4x)                                            │   │
│  │  CPU: 32 cores | RAM: 128GB | GPU: NVIDIA A100 40GB o H100 80GB      │   │
│  │  Servicios: vLLM (replicated), Embedding Service                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  NODOS DATA (3x - HA)                                                 │   │
│  │  CPU: 32 cores | RAM: 256GB | Disco: 8TB NVMe RAID                   │   │
│  │  Servicios: PostgreSQL HA, Weaviate Cluster, ES Cluster, Redis HA    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  ALMACENAMIENTO EXTERNO                                               │   │
│  │  NAS/SAN: 20TB+ | Backup: 50TB+ (offsite)                            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Estimación de costos:                                                       │
│     Hardware:           ~$150,000 - $300,000 USD                            │
│     Mantenimiento/año:  ~$30,000 - $50,000 USD                              │
│     Soporte 24/7:       ~$50,000 - $100,000 USD/año                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 🎮 Guía de Selección de GPU

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONSUMER (Gaming GPUs)                                                      │
├───────────────┬───────────┬─────────────────────────────────────────────────┤
│  Modelo       │  VRAM     │  Uso Recomendado                                │
├───────────────┼───────────┼─────────────────────────────────────────────────┤
│  RTX 3060     │  12GB     │  ❌ Muy limitado - solo desarrollo básico       │
│  RTX 3080     │  10GB     │  ⚠️  Qwen3-4B ajustado, sin TTS local           │
│  RTX 3090     │  24GB     │  ✅ Desarrollo completo, demos                  │
│  RTX 4070 Ti  │  12GB     │  ⚠️  Similar a 3080, mejor rendimiento          │
│  RTX 4080     │  16GB     │  ✅ Producción pequeña (con limitaciones)       │
│  RTX 4090     │  24GB     │  ✅ Desarrollo óptimo, producción pequeña       │
└───────────────┴───────────┴─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  PROFESSIONAL (Workstation GPUs)                                             │
├───────────────┬───────────┬─────────────────────────────────────────────────┤
│  Modelo       │  VRAM     │  Uso Recomendado                                │
├───────────────┼───────────┼─────────────────────────────────────────────────┤
│  RTX A4000    │  16GB     │  ✅ Producción pequeña, rack-friendly           │
│  RTX A5000    │  24GB     │  ✅ Producción media, mejor que 4090 en rack    │
│  RTX A6000    │  48GB     │  ✅ Producción media-grande, modelos grandes    │
└───────────────┴───────────┴─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  DATA CENTER (Server GPUs)                                                   │
├───────────────┬───────────┬─────────────────────────────────────────────────┤
│  Modelo       │  VRAM     │  Uso Recomendado                                │
├───────────────┼───────────┼─────────────────────────────────────────────────┤
│  NVIDIA L4    │  24GB     │  ✅ Eficiente, bajo consumo, cloud-friendly     │
│  NVIDIA L40   │  48GB     │  ✅ Balance rendimiento/costo                   │
│  NVIDIA A100  │  40/80GB  │  ✅ Enterprise, alto throughput                 │
│  NVIDIA H100  │  80GB     │  ✅ Máximo rendimiento, modelos muy grandes     │
└───────────────┴───────────┴─────────────────────────────────────────────────┘
```

### Distribución de VRAM por Componente

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  GPU 24GB (RTX 4090 / A5000 / L4)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░  vLLM Qwen3-4B    (~8GB)      │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  BGE-M3 Embed     (~2GB)      │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  KV Cache         (~4GB)      │
│  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  TTS (opcional)   (~2GB)      │
│  ────────────────────────────────────────────────────────────────────────   │
│  Total: ~16GB usado | ~8GB libre para batching                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  GPU 48GB (A6000 / L40)                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ████████████████████████████░░░░░░░░░░░░░░░░  vLLM Qwen3-14B   (~16GB)     │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  BGE-M3 Embed     (~2GB)      │
│  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  KV Cache (32K)   (~8GB)      │
│  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  TTS              (~2GB)      │
│  ────────────────────────────────────────────────────────────────────────   │
│  Total: ~28GB usado | ~20GB libre para batching concurrente                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### ⚡ Optimizaciones para Hardware Limitado

Si tu hardware está "justo", considera estas optimizaciones:

```bash
# 1. Usar modelo más pequeño
VLLM_MODEL=Qwen/Qwen3-1.7B          # En lugar de 4B
VLLM_MAX_MODEL_LEN=8192             # Reducir contexto

# 2. Embeddings en CPU (libera ~2GB VRAM)
EMBEDDING_DEVICE=cpu

# 3. Desactivar TTS local
TTS_PROVIDER=google                  # Usa API en lugar de local

# 4. Reducir workers de Celery
# En start.sh: celery ... --concurrency=2

# 5. Limitar recursos de contenedores
# En docker-compose.yml:
services:
  weaviate-service:
    deploy:
      resources:
        limits:
          memory: 4G

# 6. Usar quantización (vLLM)
# Añadir --quantization awq al comando de vLLM
```

### Monitoreo de Recursos

```bash
# Ver uso de GPU en tiempo real
watch -n 1 nvidia-smi

# Ver uso de memoria por contenedor
docker stats

# Ver uso de disco
df -h

# Métricas de vLLM
curl http://localhost:8000/metrics | grep -E "vllm_gpu|vllm_cache"
```

---

## Development vs Production

### ⚡ Fast Development Mode (`docker-compose.dev.yml` + `start-dev-fast.sh`)

**Best for:** Maximum development speed with instant code changes

**Features:**
- ✅ **Instant code changes** - No rebuilds, just save and refresh
- ✅ **Volume mounting** - All source code mounted as volumes
- ✅ **Live reloading** - uvicorn `--reload` flag on all services
- ✅ **Smart building** - Only rebuilds when dependencies change
- ✅ **Full debugging** - Source maps and error traces
- ✅ **Hot module replacement** - Changes reflect immediately

**Volume Mounts:**
```
../app                          → /app/app          (main API)
../microservices/*/app          → /app/app          (all microservices)
../credentials                  → /app/credentials  (GCS keys)
../scripts                      → /app/scripts      (utility scripts)
```

### 🔧 Standard Development Mode (`docker-compose.yml` + `start-dev.sh`)

**Best for:** When you need to modify Dockerfiles or dependencies

**Features:**
- ✅ **Traditional Docker** - Rebuilds on every startup
- ✅ **Clean builds** - Ensures consistency
- ✅ **Dependency updates** - Picks up requirements.txt changes
- ✅ **Dockerfile changes** - Applies configuration updates

**When to use:**
- After modifying `requirements.txt`
- After changing `Dockerfile`
- When you want guaranteed clean state
- For CI/CD pipeline testing

### 🚀 Production Mode (`docker-compose.yml`)

**Best for:** Production deployment, performance testing

**Features:**
- ✅ **Optimized images** - Multi-stage builds
- ✅ **Smaller size** - Build deps removed
- ✅ **Better security** - Code copied, not mounted
- ✅ **Production performance** - No volume overhead

**Files:**
- `docker-compose.yml` - Production configuration  
- `Dockerfile` - Production images for each microservice
- `start-prod.sh` - Production startup script

## Services Overview

### Microservices

| Service | Port | Description |
|---------|------|-------------|
| Main API | 8000 | FastAPI main application |
| Storage Service | 8003 | Google Cloud Storage operations |
| Weaviate Service | 8007 | Emma AI + SIL + Verified Generation (Agent Framework + vLLM + RAG) |
| Elasticsearch Service | 8008 | Full-text search & document indexing |
| LangExtract Service | 8009 | Document language extraction |
| TTS Service | 8010 | Text-to-Speech (Google TTS / VibeVoice) |
| Background Worker | 8100 | Celery async task worker (indexing, verification, channels) |

### Infrastructure

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL + AGE | 5432 | Relational database + Apache AGE graph extension |
| Redis | 6379 | Cache, sessions, Celery broker & verified claims cache |
| Weaviate | 8080 | Vector database for semantic search |
| Elasticsearch | 9200 | Full-text search engine |
| vLLM Server | interno | High-throughput GPU inference (Qwen/Qwen3-4B) |
| Gotenberg | 3000 | Document conversion to PDF |
| KeyCloak | 8080 | OIDC Identity Provider (on-premise auth) |

---

## 🧠 Structural Intelligence Layer (SIL)

### Descripción
El SIL es un sistema de **razonamiento pre-LLM** que aprende la **estructura** de los documentos en lugar de su contenido. Esto permite responder consultas estructurales sin invocar el RAG completo, ahorrando hasta un **70-90% de tokens**.

### Arquitectura
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  RAG TRADICIONAL                    →    ENFOQUE SIL                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  ❌ Embeber contenido completo      →    ✅ Embeber descripciones estructurales│
│  ❌ Siempre invocar LLM + RAG       →    ✅ Responder estructuralmente si es posible│
│  ❌ 10K+ tokens por consulta        →    ✅ 500-1000 tokens (70-90% ahorro)  │
│  ❌ Sin consciencia temporal        →    ✅ Historial completo y evolución   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Capas del SIL

| Capa | Descripción |
|------|-------------|
| **1. Extracción Estructural** | Extrae ubicación, tipo, relaciones (no contenido) |
| **2. Grafo Estructural (Apache AGE)** | Grafo consultable con Cypher |
| **3. Embeddings Estructurales** | Embeddings de descripciones estructurales |
| **4. Motor Pre-LLM** | Responde consultas estructurales sin RAG |
| **5. LLM como Intérprete** | LLM recibe contexto estructural, no documentos completos |

### Tipos de Razonamiento

| Tipo | Descripción | Ejemplo |
|------|-------------|---------|
| `STRUCTURAL` | Respuesta directa del grafo | "¿Cuántos contratos tiene ACME?" |
| `TEMPORAL` | Consultas basadas en tiempo | "¿Qué cambió en el último mes?" |
| `MULTIHOP` | Traversar relaciones | "Documentos relacionados con X" |
| `FOCUSED_RAG` | RAG solo en documentos específicos | "Resumen del contrato #123" |
| `FULL_RAG` | RAG tradicional (fallback) | Consultas de contenido general |

### Endpoints SIL

```bash
# Consulta estructural con razonamiento Pre-LLM
POST /sil/query
{
  "query": "¿Cuántos contratos tiene ACME?",
  "tenant_id": "tenant-uuid",
  "reasoning_mode": "auto"
}

# Indexar metadatos estructurales
POST /sil/index-structural
{
  "document_id": "doc-uuid",
  "tenant_id": "tenant-uuid"
}

# Obtener estructura de un documento
GET /sil/structure/{document_id}

# Estadísticas del grafo
GET /sil/graph/stats

# Búsqueda por similitud estructural
POST /sil/search-structural
```

### Flujo de Consulta
```
Usuario: "¿Cuántos contratos tiene ACME?"
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SIL Pre-LLM Reasoning                                                        │
│ Intent: STRUCTURAL_COUNT → No RAG necesario                                  │
│ Cypher: MATCH (d:structural_document {client:'ACME', type:'contract'})       │
│         RETURN count(d) → 5                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
LLM interpreta contexto estructural → "ACME tiene 5 contratos..."
         │
         ▼
🎯 SIN LECTURA DE CONTENIDO - 70% ahorro de tokens
```

---

## ✅ Agent Self-Verifies (Generación Verificada)

### Descripción
Patrón de generación de documentos donde **cada claim se verifica contra Weaviate** antes de ser aceptado. Reduce alucinaciones en un **~70%** comparado con generación estándar.

### Arquitectura
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FLUJO DE VERIFICACIÓN                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Writer Agent        Celery Verifier         Redis Cache                    │
│   (Genera claim)  →   (Busca evidencia)  →   (Almacena si OK)               │
│        │                    │                      │                         │
│        │    ┌───────────────┘                      │                         │
│        │    │                                      │                         │
│        ▼    ▼                                      ▼                         │
│   ┌─────────────────┐                    ┌─────────────────┐                │
│   │ STOP-AND-GO     │                    │ DOCUMENTO FINAL │                │
│   │ (Loop serial)   │                    │ (Claims verificados)             │
│   └─────────────────┘                    └─────────────────┘                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Componentes

| Componente | Ubicación | Descripción |
|------------|-----------|-------------|
| **WriterAgent** | `weaviate-service` | Genera UN claim a la vez usando vLLM |
| **VerifiedCache** | Redis | Almacena claims verificados por sesión |
| **VerificationTask** | `background-worker` | Busca evidencia en Weaviate + evalúa con vLLM |
| **VerifiedDocumentService** | `weaviate-service` | Orquesta el loop stop-and-go |

### Endpoints Verified Generation

```bash
# Generar documento verificado (síncrono)
POST /verified/generate
{
  "query": "Genera un resumen del contrato con ACME",
  "tenant_id": "tenant-uuid",
  "max_claims": 10,
  "confidence_threshold": 0.7
}

# Generar documento verificado (SSE streaming)
POST /verified/generate/stream
{
  "query": "Genera un resumen del contrato con ACME",
  "tenant_id": "tenant-uuid",
  "max_claims": 10
}

# Obtener claims verificados de una sesión
GET /verified/session/{session_id}/claims

# Estadísticas de sesión
GET /verified/session/{session_id}/stats

# Limpiar sesión
DELETE /verified/session/{session_id}
```

### Respuesta de Generación Verificada
```json
{
  "session_id": "uuid",
  "query": "Genera un resumen...",
  "document_text": "El contrato con ACME establece...",
  "claims": [
    {
      "id": "claim-uuid",
      "text": "El contrato fue firmado el 15 de enero",
      "status": "verified",
      "confidence": 0.92,
      "evidence": [
        {
          "document_id": "doc-uuid",
          "document_title": "Contrato ACME 2024",
          "text_excerpt": "...firmado en fecha 15 de enero de 2024...",
          "similarity_score": 0.89
        }
      ]
    }
  ],
  "total_claims_generated": 5,
  "claims_verified": 4,
  "claims_corrected": 1,
  "claims_rejected": 0,
  "average_confidence": 0.88,
  "execution_time_ms": 12500
}
```

### Estados de Claims

| Estado | Descripción |
|--------|-------------|
| `verified` | Claim soportado por evidencia con confianza >= threshold |
| `corrected` | Claim modificado según sugerencia del LLM |
| `rejected` | Claim sin evidencia suficiente (descartado) |
| `error` | Error durante verificación |

### Configuración

```bash
# En .env
VERIFIED_MAX_CLAIMS=20                    # Máximo claims por documento
VERIFIED_CLAIM_TEMPERATURE=0.3            # Temperatura para generación (bajo = más factual)
VERIFIED_TIMEOUT_SECONDS=45               # Timeout por claim
VERIFIED_CONFIDENCE_THRESHOLD=0.7         # Umbral mínimo de confianza
VERIFIED_MAX_CORRECTION_ATTEMPTS=2        # Intentos de corrección
VERIFIED_AUTO_ACCEPT_CORRECTIONS=true     # Auto-aceptar correcciones del LLM
VERIFIED_CACHE_TTL_SECONDS=3600           # TTL del cache en Redis
```

### Cola Celery

Los tasks de verificación usan una cola dedicada:
```python
# En celery_app.py
task_routes = {
    "verification.*": {"queue": "verification"},
}
```

El worker debe escuchar esta cola:
```bash
celery -A worker_app.celery_app worker -Q default,verification,...
```

---

## 🔐 Autenticación On-Premise (KeyCloak)

### Configuración OIDC
```bash
# En .env
DEPLOYMENT_MODE=on_premise
OIDC_ISSUER=http://your-keycloak:8080/realms/nexus
OIDC_CLIENT_ID=emma-app
OIDC_CLIENT_SECRET=your-secret-key
OIDC_SCOPES=openid profile email
OIDC_AUTO_PROVISION=true
```

### Flujo de Autenticación
1. Usuario accede a la aplicación
2. Redirect a KeyCloak para login
3. KeyCloak autentica y retorna JWT
4. Backend valida JWT contra KeyCloak JWKS
5. Si `OIDC_AUTO_PROVISION=true`, usuario se crea automáticamente

---

## Environment Setup

1. **Create `.env` file** (required - in backend root):
```bash
# From backend/docker directory:
cp ../.env.example ../.env
# Edit ../.env with your settings

# Or from backend root directory:
cp .env.example .env
# Edit .env with your settings
```

2. **Credentials setup**:
```bash
# Place GCS credentials in:
../credentials/nexus-document-ia-04252dae0146.json
```

## Usage Commands

### Fast Development Workflow (Recommended)
```bash
# Start fast development environment
./start-dev-fast.sh

# View logs
docker compose -f docker-compose.dev.yml logs -f

# View specific service logs
docker compose -f docker-compose.dev.yml logs -f api

# Stop services
docker compose -f docker-compose.dev.yml down

# Restart a single service
docker compose -f docker-compose.dev.yml restart api
```

### Standard Development Workflow
```bash
# Start standard development environment
./start-dev.sh

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f api

# Stop services
docker compose down

# Restart a single service
docker compose restart api
```

### Production Workflow  
```bash
# Start production environment
./start-prod.sh

# View logs
docker compose logs -f

# Stop services
docker compose down

# Rebuild all images
docker compose build --no-cache
```

### Debugging Commands
```bash
# Execute shell in container
docker compose exec langchain-service bash

# View container status
docker compose ps

# View resource usage
docker stats

# Clean up
docker compose down --volumes --remove-orphans
docker system prune -f
```

## Development Benefits

### Before (Traditional Docker)
- ❌ Full rebuild on every code change
- ❌ 2-5 minutes rebuild time
- ❌ Slow development iteration
- ❌ Container restart required

### After (Volume Mounting)
- ✅ Instant code changes
- ✅ No rebuilds needed
- ✅ Fast development iteration  
- ✅ Auto-reload on save

## Troubleshooting

### Common Issues

**Port conflicts:**
```bash
# Check what's using ports
lsof -i :8000
lsof -i :8001

# Kill processes if needed
sudo kill -9 <PID>
```

**Permission issues:**
```bash
# Fix volume permissions
sudo chown -R $USER:$USER ../microservices/
```

**Dependency issues:**
```bash
# Rebuild images when requirements.txt changes
docker compose -f docker-compose.dev.yml build --no-cache
```

**Database issues:**
```bash
# Reset database
docker compose down --volumes
docker compose up -d db
# Run migrations again from backend root:
cd .. && python -m scripts.init_db
```

**Environment file issues:**
```bash
# Check if .env exists in backend root
ls -la ../.env

# Create from example if missing
cp ../.env.example ../.env
```

### Log Monitoring
```bash
# Monitor all services
docker compose -f docker-compose.dev.yml logs -f

# Monitor specific service
docker compose -f docker-compose.dev.yml logs -f langchain-service

# Monitor with timestamps
docker compose -f docker-compose.dev.yml logs -f -t
```

## Gotenberg Document Conversion

### Overview
Gotenberg is an open-source document conversion service that provides universal PDF generation from various document formats.

### Supported Formats
- **Office Documents**: `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`, `.odt`, `.ods`, `.odp`
- **Text Formats**: `.txt`, `.md`, `.html`, `.htm`
- **Already PDF**: `.pdf` (thumbnail generation)
- **Images**: `.jpg`, `.png`, `.gif`, `.bmp`, `.tiff`

### API Endpoints
```bash
# Generate document preview
GET /api/v1/documents/{doc_id}/preview

# Check existing preview
GET /api/v1/documents/{doc_id}/preview/info

# Force regenerate preview
GET /api/v1/documents/{doc_id}/preview?force_regenerate=true
```

### Preview Response Format
```json
{
  "type": "office_preview",
  "conversion_method": "gotenberg",
  "pdf_available": true,
  "pdf_storage_path": "previews/tenant-id/doc-id/preview.pdf",
  "thumbnails": ["path/to/thumb1.jpg", "path/to/thumb2.jpg"],
  "original_format": ".docx",
  "cached": true,
  "generated_at": 1703123456,
  "file_size": 2048576
}
```

### Features
- ✅ **High-quality PDF conversion** using LibreOffice and Chromium
- ✅ **Thumbnail generation** from PDF pages
- ✅ **Caching system** for faster subsequent requests
- ✅ **Storage integration** for preview persistence
- ✅ **Fallback support** when Gotenberg is unavailable
- ✅ **Custom CSS** for HTML/Markdown conversion

### Health Check
```bash
curl http://localhost:3001/health
```

## Performance Notes

### Recursos del Sistema

| Componente | RAM | GPU VRAM | Notas |
|------------|-----|----------|-------|
| Full Stack (sin GPU) | ~8-12GB | - | Modo CPU |
| vLLM (Qwen3-4B) | ~2GB | ~8GB | Modelo principal |
| BGE-M3 Embeddings | ~1GB | ~2GB | Cargado en weaviate-service |
| PostgreSQL + AGE | ~512MB | - | Con extensión de grafo |
| Weaviate | ~1GB | - | Vector DB |
| Redis | ~256MB | - | Cache + Celery broker |
| Gotenberg | ~512MB-1GB | - | Conversión de documentos |

### Configuración GPU Recomendada (RTX 4090 24GB)
```
┌─────────────────────────────────────────────────────────────┐
│  CONFIGURACIÓN RECOMENDADA                                   │
├─────────────────────────────────────────────────────────────┤
│  vLLM (Qwen3-4B):     ~8GB  (35%)                           │
│  BGE-M3 Embeddings:   ~2GB  (10%)                           │
│  Buffer/KV Cache:     ~4GB  (15%)                           │
│  ─────────────────────────────────────────────────          │
│  Total Usado:         ~14GB (60%)                           │
│  Libre:               ~10GB (40%) - para batching           │
└─────────────────────────────────────────────────────────────┘
```

### Métricas de Rendimiento

| Feature | Tiempo Típico | Tokens |
|---------|---------------|--------|
| RAG Tradicional | 3-8s | 10K+ |
| SIL (Estructural) | 0.5-2s | 500-1K |
| Verified Generation (por claim) | 30-50s | 2-3K |
| Embedding (BGE-M3) | 50-100ms | - |

### Notas de Desarrollo
- **Development mode**: Overhead leve por volume mounting
- **Production mode**: Imágenes optimizadas, menor tamaño
- **SIL**: Ahorra 70-90% de tokens en consultas estructurales
- **Verified Generation**: Reduce alucinaciones ~70%, pero más lento (stop-and-go)