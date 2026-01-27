# NouxCubeIA On-Premise - Self-Hosted Deployment

<div align="center">
  <h3>Full Control, Local GPU Inference, Data Sovereignty</h3>
  <p><strong>Run NouxCubeIA on your own infrastructure</strong></p>
</div>

---

## Overview

NouxCubeIA On-Premise is designed for organizations that require complete control over their data and infrastructure. With local GPU inference via vLLM and Qwen3 models, you get enterprise-grade AI capabilities without sending data to external providers.

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Data Sovereignty** | All data stays on your servers |
| **Local AI Inference** | No API calls to external LLM providers |
| **Full Customization** | Configure models, prompts, and workflows |
| **Predictable Costs** | No per-query API charges |
| **Air-Gap Compatible** | Can run in isolated networks |

---

## Hardware Requirements

> ⚠️ **IMPORTANTE**: Los requisitos de hardware son críticos para el rendimiento. Una configuración "justa" resultará en tiempos de respuesta lentos y posibles errores de memoria.

### Resumen por Escenario

| Escenario | CPU | RAM | GPU VRAM | Disco | Usuarios | Costo Est. |
|-----------|-----|-----|----------|-------|----------|------------|
| **Desarrollo** | 8 cores | 32GB | 12-24GB | 256GB SSD | 1-3 | ~$3,000 |
| **Producción Pequeña** | 16 cores | 64GB | 24GB | 1TB NVMe | 10-50 | ~$10,000 |
| **Producción Media** | 32 cores | 128GB | 48GB | 2TB NVMe | 50-200 | ~$35,000 |
| **Enterprise** | 64+ cores | 256GB+ | 80GB+ | 4TB+ NVMe | 200+ | ~$200,000 |

### Configuración Mínima (Funcional pero LIMITADA)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ⚠️  CONFIGURACIÓN MÍNIMA - Solo desarrollo/pruebas                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  GPU:     NVIDIA RTX 3060 12GB                                              │
│  CPU:     Intel i5-10400 / AMD Ryzen 5 3600 (6 cores)                       │
│  RAM:     16GB DDR4                                                         │
│  Disco:   256GB SSD SATA                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  ❌ LIMITACIONES SEVERAS:                                                    │
│     • Solo Qwen3-1.7B (modelo muy pequeño)                                  │
│     • Contexto máximo 8K tokens                                             │
│     • Embeddings en CPU (muy lento, 2-5 segundos por chunk)                 │
│     • Sin TTS local                                                         │
│     • SLM Router disponible pero lento                                      │
│     • Agent Self-Verifies: ~2-3 minutos por claim                           │
│     • 1-2 usuarios concurrentes máximo                                      │
│     • NO RECOMENDADO para producción                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Configuración Recomendada (Experiencia fluida)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ✅ CONFIGURACIÓN RECOMENDADA - Desarrollo + Demos                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  GPU:     NVIDIA RTX 4090 24GB                                              │
│  CPU:     Intel i7-12700 / AMD Ryzen 7 5800X (8-12 cores)                   │
│  RAM:     32GB DDR4-3200                                                    │
│  Disco:   512GB NVMe Gen4                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Distribución VRAM (24GB total):                                            │
│                                                                              │
│  ████████████████████░░░░░░░░░░░░░░░░░░░░  vLLM Qwen3-4B      8GB   (33%)  │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  BGE-M3 Embeddings  2GB   (8%)   │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  KV Cache           4GB   (17%)  │
│  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  TTS Local          2GB   (8%)   │
│  ────────────────────────────────────────────────────────────────────────   │
│  Total usado: ~16GB (67%) | Libre: ~8GB (33%) para batching                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  ✅ PERMITE:                                                                 │
│     • Qwen3-4B con contexto 16K tokens                                      │
│     • BGE-M3 embeddings en GPU (~50-100ms por chunk)                        │
│     • TTS local (VibeVoice)                                                 │
│     • SLM Router completo con respuestas en <2 segundos                     │
│     • Agent Self-Verifies: 30-50 segundos por claim                         │
│     • RAG completo en <3 segundos                                           │
│     • 3-5 usuarios concurrentes                                             │
│                                                                              │
│  ⚠️  NOTA: Esta configuración va "JUSTA" si activas todas las features      │
│     Si ves errores OOM, desactiva TTS local o usa embeddings en CPU         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Configuración Producción Pequeña (10-50 usuarios)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🏢 PRODUCCIÓN PEQUEÑA - Servidor único                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  GPU:     NVIDIA RTX 4090 24GB (o A5000 24GB para rack)                     │
│  CPU:     Intel Xeon W-2255 / AMD EPYC 7313 (16 cores)                      │
│  RAM:     64GB ECC DDR4-3200                                                │
│  Disco:   1TB NVMe (OS+Apps) + 2TB NVMe (Datos)                             │
│  Red:     10GbE                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Distribución RAM (64GB):                                                    │
│     PostgreSQL + AGE:    8GB                                                │
│     Redis:               2GB                                                │
│     Weaviate:            8GB                                                │
│     Elasticsearch:       8GB                                                │
│     Microservicios:      16GB                                               │
│     vLLM:                16GB + GPU                                         │
│     Sistema:             6GB                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ✅ PERMITE:                                                                 │
│     • Todas las features activas simultáneamente                            │
│     • 10-50 usuarios concurrentes                                           │
│     • SLA de respuesta <5 segundos para 95% de queries                      │
│     • Backups diarios sin impacto                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  💰 Costo estimado: $8,000 - $12,000 USD                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Configuración Producción Media (50-200 usuarios)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🏛️ PRODUCCIÓN MEDIA - 3 servidores distribuidos                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  │
│  │   SERVIDOR APP      │  │   SERVIDOR AI/ML    │  │   SERVIDOR DATA     │  │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤  │
│  │  CPU: 16 cores      │  │  CPU: 16 cores      │  │  CPU: 16 cores      │  │
│  │  RAM: 64GB          │  │  RAM: 64GB          │  │  RAM: 128GB         │  │
│  │  GPU: -             │  │  GPU: 2x RTX 4090   │  │  GPU: -             │  │
│  │  Disco: 500GB NVMe  │  │  Disco: 1TB NVMe    │  │  Disco: 4TB NVMe    │  │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤  │
│  │  • Main API         │  │  • vLLM Server      │  │  • PostgreSQL+AGE   │  │
│  │  • Microservices    │  │  • Embeddings       │  │  • Weaviate         │  │
│  │  • Background       │  │  • TTS Service      │  │  • Elasticsearch    │  │
│  │    Worker           │  │  • Reranker         │  │  • Redis Cluster    │  │
│  │  • KeyCloak         │  │                     │  │  • Backups          │  │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  │
│                                                                              │
│  💰 Costo estimado: $25,000 - $40,000 USD                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Configuración Enterprise (200+ usuarios)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🏗️ ENTERPRISE - Kubernetes HA                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Control Plane (3x):    8 cores | 32GB RAM | 256GB NVMe                     │
│  Workers APP (3-5x):    32 cores | 128GB RAM | 1TB NVMe                     │
│  Workers GPU (2-4x):    32 cores | 128GB RAM | A100 40/80GB o H100          │
│  Workers DATA (3x):     32 cores | 256GB RAM | 8TB NVMe RAID                │
│                                                                              │
│  Storage externo:       NAS/SAN 20TB+ | Backup offsite 50TB+                │
│                                                                              │
│  💰 Costo estimado: $150,000 - $300,000 USD                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Guía de Selección de GPU

| Categoría | Modelo | VRAM | Recomendación |
|-----------|--------|------|---------------|
| **Consumer** | RTX 3060 | 12GB | ❌ Muy limitado |
| | RTX 3080 | 10GB | ❌ Insuficiente |
| | RTX 3090 | 24GB | ⚠️ Solo desarrollo |
| | RTX 4070 Ti | 12GB | ❌ Insuficiente |
| | RTX 4080 | 16GB | ⚠️ Ajustado, sin TTS local |
| | RTX 4090 | 24GB | ✅ Desarrollo + Prod. pequeña |
| **Professional** | A4000 | 16GB | ⚠️ Ajustado, rack-friendly |
| | A5000 | 24GB | ✅ Producción pequeña |
| | A6000 | 48GB | ✅ Producción media-grande |
| **Datacenter** | L4 | 24GB | ✅ Cloud, eficiente |
| | L40 | 48GB | ✅ Balance rendimiento/costo |
| | A100 | 40/80GB | ✅ Enterprise |
| | H100 | 80GB | ✅ Máximo rendimiento |

### Optimizaciones para Hardware Limitado

Si tu hardware está "justo", aplica estas optimizaciones:

```bash
# 1. Usar modelo más pequeño (ahorra ~4GB VRAM)
VLLM_MODEL=Qwen/Qwen3-1.7B
VLLM_MAX_MODEL_LEN=8192

# 2. Embeddings en CPU (libera ~2GB VRAM)
EMBEDDING_DEVICE=cpu

# 3. Desactivar TTS local (libera ~2GB VRAM)
TTS_PROVIDER=google

# 4. Reducir contexto (libera KV cache)
VLLM_MAX_MODEL_LEN=8192

# 5. Reducir workers Celery
# En start.sh: celery ... --concurrency=2

# 6. Limitar memoria de contenedores
# En docker-compose.yml:
deploy:
  resources:
    limits:
      memory: 4G
```

---

## GPU Configuration Options

### Option A: Multimodal RAG (Recommended)

Enables cross-modal search where text queries can find images, diagrams, and tables.

```
┌─────────────────────────────────────────────────────────────────┐
│          MULTIMODAL RAG CONFIGURATION (RTX 4090 24GB)           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  LLM: Qwen/Qwen3-4B-Thinking-2507                       │    │
│  │                                                          │    │
│  │  • VRAM Allocation: ~11GB (45%)                         │    │
│  │  • Context Window: 32K tokens                           │    │
│  │  • Features: Extended reasoning with <think> blocks     │    │
│  │  • Use Case: Analysis, summarization, Q&A               │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Embedding: Qwen/Qwen3-VL-Embedding-2B                  │    │
│  │                                                          │    │
│  │  • VRAM Allocation: ~5GB (20%)                          │    │
│  │  • Dimensions: 1024                                     │    │
│  │  • Features: Unified text + image embedding space       │    │
│  │  • Cross-Modal: Text queries find images/diagrams       │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  VRAM Summary                                           │    │
│  │                                                          │    │
│  │  • LLM:         ~11GB (45%)                             │    │
│  │  • Embedding:    ~5GB (20%)                             │    │
│  │  • Total Used:  ~16GB (65%)                             │    │
│  │  • Buffer:       ~8GB (35%) - for batching              │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  PDF Processing Pipeline:                                        │
│    ✓ Text extraction → Chunking → Text embedding                │
│    ✓ Images/Tables → Visual extraction → Multimodal embedding   │
│    ✓ Cross-modal search: "find diagrams about X" works          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Option B: Text-Only (Maximum Context)

For documents without visual elements, maximize context window.

```
┌─────────────────────────────────────────────────────────────────┐
│          TEXT-ONLY CONFIGURATION (RTX 4090 24GB)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  LLM: Qwen/Qwen3-4B-Thinking-2507                       │    │
│  │                                                          │    │
│  │  • VRAM Allocation: ~16GB (70%)                         │    │
│  │  • Context Window: 256K tokens (full native)            │    │
│  │  • Features: Extended reasoning with <think> blocks     │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Embedding: Qwen/Qwen3-Embedding-0.6B (text-only)       │    │
│  │                                                          │    │
│  │  • VRAM Allocation: ~1.2GB                              │    │
│  │  • Dimensions: 1024                                     │    │
│  │  • Text-only (no image embedding)                       │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Configuration:                                                  │
│    MULTIMODAL_EMBEDDING_ENABLED=false                           │
│    VLLM_MAX_MODEL_LEN=262144                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 NouxCubeIA On-Premise Architecture v2.0                    │
│                    (con SLM Router + Agent Self-Verifies)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     Application Services                             │    │
│  │                                                                      │    │
│  │  ┌──────────┐  ┌─────────────────────────┐  ┌──────────────────┐   │    │
│  │  │   api    │  │    weaviate-service     │  │ background-worker│   │    │
│  │  │ FastAPI  │  │  ┌───────────────────┐  │  │     Celery       │   │    │
│  │  │  :8000   │  │  │ Emma AI (RAG)     │  │  │     :8100        │   │    │
│  │  │          │  │  │ SLM Router        │  │  │  ┌────────────┐  │   │    │
│  │  │          │  │  │ Verified Gen      │  │  │  │verification│  │   │    │
│  │  │          │  │  └───────────────────┘  │  │  │   queue    │  │   │    │
│  │  │          │  │         :8007           │  │  └────────────┘  │   │    │
│  │  └──────────┘  └─────────────────────────┘  └──────────────────┘   │    │
│  │                                                                      │    │
│  │  ┌──────────┐  ┌─────────────────┐  ┌──────────────────┐            │    │
│  │  │langextract│ │  mcp-storage    │  │   tts-service    │            │    │
│  │  │  :8009   │  │     :8003       │  │  (Google/Local)  │            │    │
│  │  └──────────┘  └─────────────────┘  └──────────────────┘            │    │
│  │                                                                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    AI/ML Layer (GPU CUDA)                             │   │
│  │                                                                       │   │
│  │  ┌──────────────────────┐  ┌───────────────────┐                     │   │
│  │  │        vLLM          │  │   BGE-M3 Embed    │                     │   │
│  │  │    Qwen/Qwen3-4B     │  │  (sentence-trans) │                     │   │
│  │  │       :8000          │  │    in weaviate-   │                     │   │
│  │  │    ~8GB VRAM         │  │    service ~2GB   │                     │   │
│  │  └──────────────────────┘  └───────────────────┘                     │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       Data Layer                                      │   │
│  │                                                                       │   │
│  │  ┌────────────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐      │   │
│  │  │  PostgreSQL    │  │  Redis   │  │ Weaviate │  │ KeyCloak  │      │   │
│  │  │    + AGE       │  │  Cache   │  │ VectorDB │  │   OIDC    │      │   │
│  │  │  ┌──────────┐  │  │  :6379   │  │  :8080   │  │   :8080   │      │   │
│  │  │  │Knowledge │  │  │          │  │          │  │           │      │   │
│  │  │  │  Graph   │  │  │ Verified │  │          │  │           │      │   │
│  │  │  │ (Cypher) │  │  │ Claims   │  │          │  │           │      │   │
│  │  │  └──────────┘  │  │ Cache    │  │          │  │           │      │   │
│  │  │    :5432       │  │          │  │          │  │           │      │   │
│  │  └────────────────┘  └──────────┘  └──────────┘  └───────────┘      │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Flujo de Consulta:
─────────────────

Usuario ──▶ API ──▶ weaviate-service
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌──────────┐    ┌───────────┐
    │   SLM   │    │   RAG    │    │ Verified  │
    │ Router  │    │ Pipeline │    │    Gen    │
    │ (TOON)  │    │ (Emma)   │    │  (Stop&Go)│
    └────┬────┘    └────┬─────┘    └─────┬─────┘
         │              │                │
         │         ┌────┴────┐      ┌────┴────┐
         │         │  vLLM   │      │ Celery  │
         │         │ Qwen3-4B│      │Verifier │
         │         └─────────┘      └─────────┘
         │
    ┌────┴─────┐
    │ Apache   │
    │ AGE Graph│
    └──────────┘
```

### Service Ports

| Service | Internal Port | External Port | Description |
|---------|---------------|---------------|-------------|
| api | 8000 | 8000 | Main FastAPI gateway |
| weaviate-service | 8000 | 8007 | RAG + Emma AI |
| langextract-service | 8000 | 8009 | Entity extraction |
| mcp-storage | 8000 | 8003 | File storage operations |
| background-worker | 8100 | - | Celery async tasks |
| vllm | 8000 | - | LLM inference (internal) |
| qwen3-vl-embedding | 8001 | - | Embedding (internal) |
| db (PostgreSQL) | 5432 | 5432 | Database |
| redis | 6379 | 6379 | Cache |
| weaviate | 8080 | 8080 | Vector database |
| keycloak | 8080 | 8081 | SSO (optional) |

---

## Emma AI: Multi-Agent System

Emma is the intelligent assistant built on **Anthropic Skill Custom** framework with multi-pattern orchestration. The system automatically selects the best execution pattern based on query analysis.

### Orchestration Patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     EMMA COORDINATOR - ORCHESTRATION PATTERNS                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Query → Pattern Detection (LLM analysis or keywords)                  │
│                              │                                               │
│         ┌────────────────────┼────────────────────┬─────────────────┐       │
│         ▼                    ▼                    ▼                 ▼       │
│    ┌─────────┐         ┌──────────┐        ┌───────────┐     ┌──────────┐  │
│    │ HANDOFF │         │SEQUENTIAL│        │CONCURRENT │     │ RLM_LONG │  │
│    │(default)│         │ (A→B→C)  │        │ (A|B|C)   │     │ (>50K)   │  │
│    └────┬────┘         └────┬─────┘        └─────┬─────┘     └────┬─────┘  │
│         │                   │                    │                │        │
│    LLM decides         Step-by-step         Multi-view       Recursive    │
│    via tools           analysis             parallel         decomposition │
│                                                                              │
│  Examples:            Examples:            Examples:        Examples:       │
│  • General Q&A        • Due diligence      • Compare docs   • Large PDFs   │
│  • Simple search      • Legal analysis     • Risk assess.   • Long reports │
│  • Summaries          • Compliance audit   • Multi-expert   • >50K tokens  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Specialized Agents

Emma delegates tasks to specialized agents based on the query domain:

| Agent | Domain | Capabilities | Legal Knowledge |
|-------|--------|--------------|-----------------|
| **SearchAgent** | Document Retrieval | Semantic + hybrid search, entity matching | - |
| **ContractAgent** | Contract Law | Clause analysis, risk detection, deadlines | Civil Code, Commercial Code |
| **ComplianceAgent** | Regulatory | GDPR, LOPDGDD verification, audit trails | LOPDGDD, RGPD |
| **SummarizerAgent** | Content Synthesis | Executive summaries, key points, TL;DR | - |
| **AnalystAgent** | Data Analysis | Financial metrics, trends, comparisons | - |
| **LaborAgent** | Employment Law | Contract terms, PRL, working conditions | Workers' Statute, LISOS |
| **FiscalAgent** | Tax Law | IRPF, VAT, corporate tax analysis | Tax regulations |
| **PrivacyAgent** | Data Protection | Personal data handling, consent verification | LOPDGDD, GDPR |
| **LegalAgent** | General Legal | Cross-domain legal analysis | Multiple sources |
| **EducationAgent** | Education Law | LOMLOE, LOE compliance | Education laws |
| **RealEstateAgent** | Property Law | Lease analysis, cadastral data | Property regulations |
| **TaxDeclarationAgent** | Tax Forms | Form validation, deduction identification | Tax forms |

### Agent Configuration

```bash
# backend/docker/.env

# =============================================================================
# Agent System Configuration
# =============================================================================
# Enable/disable the agent system
AGENT_ENABLED=true

# Default orchestration pattern (handoff, sequential, concurrent, rlm_long)
AGENT_DEFAULT_PATTERN=handoff

# Agent timeout (seconds) - increase for complex analysis
AGENT_TIMEOUT_SECONDS=120

# Redis for agent conversation persistence
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Conversation TTL (seconds)
AGENT_CONVERSATION_TTL=3600

# =============================================================================
# RLM (Long Context) Configuration
# =============================================================================
# Token threshold to trigger RLM pattern
RLM_TOKEN_THRESHOLD=50000

# Maximum recursion depth for document decomposition
RLM_MAX_DEPTH=3
```

---

## External Connectors

NouxCubeIA can sync documents from external systems via the **Connector Adapter** system. This enables unified search across your organization's document repositories.

### Supported Connectors

| Connector | Status | Features |
|-----------|--------|----------|
| **Alfresco** | ✅ Implemented | Full sync, incremental updates, health checks |
| **SharePoint** | 🔜 Roadmap | Microsoft Graph API integration |
| **OneDrive** | 🔜 Roadmap | Personal and shared drives |
| **Google Drive** | 🔜 Roadmap | Google Workspace integration |
| **Amazon S3** | 🔜 Roadmap | Bucket-based document storage |
| **Azure Blob** | 🔜 Roadmap | Azure storage containers |

### Connector Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CONNECTOR SYNC PIPELINE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    External Document Sources                         │    │
│  │                                                                      │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │    │
│  │  │ Alfresco │  │SharePoint│  │  Google  │  │    S3    │            │    │
│  │  │   ECM    │  │  Online  │  │  Drive   │  │  Bucket  │            │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘            │    │
│  │       │             │             │             │                   │    │
│  └───────┼─────────────┼─────────────┼─────────────┼───────────────────┘    │
│          │             │             │             │                        │
│          └─────────────┴──────┬──────┴─────────────┘                        │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                  Connector Adapter Factory                           │    │
│  │                                                                      │    │
│  │  • Unified interface (list, download, health_check)                 │    │
│  │  • Strategy pattern for extensibility                               │    │
│  │  • Rate limiting & retry logic                                      │    │
│  │  • Incremental sync support                                         │    │
│  │                                                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                  Unified Indexing Service                            │    │
│  │                                                                      │    │
│  │  1. list_documents() → Discovery (metadata only)                    │    │
│  │  2. download_content() → Fetch file bytes                           │    │
│  │  3. Process → Text extraction, entity extraction                    │    │
│  │  4. Index → Weaviate (vectors) + PostgreSQL (metadata)              │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Configuring Alfresco Connector

```bash
# 1. Create connector via API
curl -X POST http://localhost:8000/api/v1/connectors \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Corporate Alfresco",
    "connector_type": "alfresco",
    "config": {
      "base_url": "https://alfresco.company.com",
      "username": "sync_user",
      "password": "secure_password",
      "site_id": "corporate-docs",
      "sync_path": "/Shared/Documents",
      "include_mime_types": ["application/pdf", "application/msword"],
      "exclude_paths": ["/Shared/Documents/Archive"]
    },
    "sync_schedule": "0 */4 * * *"
  }'

# 2. Trigger manual sync
curl -X POST http://localhost:8000/api/v1/connectors/{connector_id}/sync \
  -H "Authorization: Bearer $TOKEN"

# 3. Check sync status
curl http://localhost:8000/api/v1/connectors/{connector_id}/status \
  -H "Authorization: Bearer $TOKEN"
```

### Connector Environment Variables

```bash
# =============================================================================
# Connector Configuration
# =============================================================================
# Enable connector system
CONNECTORS_ENABLED=true

# Sync configuration
CONNECTOR_SYNC_BATCH_SIZE=50
CONNECTOR_SYNC_TIMEOUT_SECONDS=300
CONNECTOR_MAX_CONCURRENT_DOWNLOADS=3

# Health check interval (seconds)
CONNECTOR_HEALTH_CHECK_INTERVAL=300
```

---

## Knowledge Graph: Entity & Document Relationships

NouxCubeIA includes a **Knowledge Graph** powered by **Apache AGE** (A Graph Extension for PostgreSQL). This enables entity-based document discovery, relationship traversal, and intelligent query expansion.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE GRAPH ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     PostgreSQL + Apache AGE                          │    │
│  │                                                                      │    │
│  │  Graph: knowledge_graph (shared, tenant-isolated via properties)    │    │
│  │                                                                      │    │
│  │  ┌────────────────────────────────────────────────────────────┐     │    │
│  │  │  NODES (Vertices)                                          │     │    │
│  │  │                                                            │     │    │
│  │  │  ┌─────────┐    ┌──────────┐    ┌─────────┐              │     │    │
│  │  │  │ Entity  │    │ Document │    │  Chunk  │              │     │    │
│  │  │  │         │    │          │    │         │              │     │    │
│  │  │  │ PERSON  │    │ contract │    │ chunk_1 │              │     │    │
│  │  │  │ ORG     │    │ invoice  │    │ chunk_2 │              │     │    │
│  │  │  │ DATE    │    │ report   │    │ ...     │              │     │    │
│  │  │  │ AMOUNT  │    │          │    │         │              │     │    │
│  │  │  └─────────┘    └──────────┘    └─────────┘              │     │    │
│  │  │                                                            │     │    │
│  │  └────────────────────────────────────────────────────────────┘     │    │
│  │                                                                      │    │
│  │  ┌────────────────────────────────────────────────────────────┐     │    │
│  │  │  EDGES (Relationships)                                     │     │    │
│  │  │                                                            │     │    │
│  │  │  • APPEARS_IN:  Entity → Document (strength, context)     │     │    │
│  │  │  • RELATED_TO:  Entity → Entity (type, strength)          │     │    │
│  │  │  • REFERENCES:  Document → Document (type, strength)      │     │    │
│  │  │  • CONTAINS:    Document → Chunk (sequence)               │     │    │
│  │  │  • DEPENDS_ON:  Chunk → Chunk (semantic|structural)       │     │    │
│  │  │                                                            │     │    │
│  │  └────────────────────────────────────────────────────────────┘     │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  INDEX TABLES (PostgreSQL - for fast lookups)                        │    │
│  │                                                                      │    │
│  │  • kg_entity_index:   normalized_value → vertex_id                  │    │
│  │  • kg_document_index: document_id → vertex_id                       │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How It Works

When documents are indexed, the system:

1. **Extracts Entities**: Uses LLM to identify PERSON, ORGANIZATION, DATE, AMOUNT, etc.
2. **Normalizes Values**: Deduplicates entities (e.g., "Juan García" = "juan garcia")
3. **Creates Graph Nodes**: Stores entities and documents as vertices in AGE
4. **Establishes Relationships**: Links entities to documents (APPEARS_IN) and entities to each other (RELATED_TO)

During queries:

1. **Entity Detection**: Identifies entities mentioned in the user query
2. **Graph Traversal**: Uses Cypher to find related entities and documents
3. **Query Expansion**: Adds related terms to improve retrieval
4. **Context Enrichment**: Provides document relationships to the LLM

### Entity Types

| Type | Description | Example |
|------|-------------|---------|
| `PERSON` | Individual names | "Juan García Pérez" |
| `ORGANIZATION` | Companies, institutions | "Acme Corp", "Ministerio de Hacienda" |
| `DATE` | Dates and periods | "15 de enero de 2024" |
| `AMOUNT` | Monetary values | "15.000 €", "$50,000" |
| `LOCATION` | Places, addresses | "Madrid", "C/ Gran Vía 25" |
| `CONTRACT_ID` | Contract identifiers | "CNT-2024-001" |
| `LAW_REFERENCE` | Legal citations | "Art. 1 LOPDGDD" |
| `DOCUMENT_REF` | Document references | "Anexo A", "Cláusula 5.2" |

### Cypher Query Examples

```cypher
-- Find all entities in a specific document
MATCH (e:Entity)-[:APPEARS_IN]->(d:Document {id: 'doc-456'})
RETURN e.entity_value, e.entity_type

-- Find related entities (for query expansion)
MATCH (e:Entity {value: 'Juan García', tenant_id: 'tenant-123'})
      -[:RELATED_TO*1..2]-(related)
RETURN related.value, related.type

-- Find documents containing a specific person
MATCH (e:Entity {entity_type: 'PERSON', normalized_value: 'juan garcia'})
      -[:APPEARS_IN]->(d:Document)
WHERE d.tenant_id = 'tenant-123'
RETURN d.id, d.title

-- Find document dependencies/references
MATCH (d1:Document)-[r:REFERENCES]->(d2:Document)
WHERE d1.tenant_id = 'tenant-123'
RETURN d1.title AS source, d2.title AS target, r.type

-- Find co-occurring entities (entities that appear together)
MATCH (e1:Entity)-[:APPEARS_IN]->(d:Document)<-[:APPEARS_IN]-(e2:Entity)
WHERE e1.entity_id <> e2.entity_id
  AND e1.tenant_id = 'tenant-123'
RETURN e1.value, e2.value, count(d) AS co_occurrences
ORDER BY co_occurrences DESC
LIMIT 10
```

### Graph Service API

The Knowledge Graph is accessible through the Weaviate Service API:

```bash
# Get graph statistics for a tenant
curl http://localhost:8007/api/v1/graph/stats \
  -H "X-Tenant-ID: $TENANT_ID" | jq

# Response:
{
  "enabled": true,
  "backend": "apache_age",
  "graph_name": "knowledge_graph",
  "tenant_id": "tenant-123",
  "node_count": 1542,
  "edge_count": 3891,
  "entity_types": {
    "PERSON": 234,
    "ORGANIZATION": 156,
    "DATE": 412,
    "AMOUNT": 289,
    "LOCATION": 98
  }
}

# Find entity neighbors (related entities)
curl "http://localhost:8007/api/v1/graph/neighbors?entity=Juan%20García&depth=2" \
  -H "X-Tenant-ID: $TENANT_ID" | jq

# Response:
[
  {
    "entity_value": "Acme Corp",
    "entity_type": "ORGANIZATION",
    "relationship_type": "RELATED_TO",
    "relationship_strength": 0.85,
    "depth": 1
  },
  {
    "entity_value": "María López",
    "entity_type": "PERSON",
    "relationship_type": "RELATED_TO",
    "relationship_strength": 0.72,
    "depth": 2
  }
]
```

### Configuration

```bash
# backend/docker/.env

# =============================================================================
# Knowledge Graph Configuration (Apache AGE)
# =============================================================================
# Enable/disable knowledge graph
RAG_KNOWLEDGE_GRAPH_ENABLED=true

# Graph traversal settings
RAG_GRAPH_TRAVERSAL_DEPTH=2          # Max hops for neighbor queries
RAG_GRAPH_MAX_NEIGHBORS=50           # Max neighbors to return
RAG_GRAPH_MIN_RELATIONSHIP_STRENGTH=0.3  # Filter weak relationships

# Entity extraction (during indexing)
ENTITY_EXTRACTION_ENABLED=true
ENTITY_EXTRACTION_MODEL=vllm         # Use local vLLM for extraction
ENTITY_TYPES=PERSON,ORGANIZATION,DATE,AMOUNT,LOCATION,CONTRACT_ID

# Index optimization
KG_ENTITY_DEDUP_ENABLED=true         # Deduplicate similar entities
KG_RELATIONSHIP_INFERENCE=true       # Infer relationships from context
```

### Database Setup

The Knowledge Graph is automatically initialized when PostgreSQL starts. The initialization script (`backend/docker/init-scripts/01-init-age.sql`) creates:

1. **Apache AGE Extension**: Graph database functionality
2. **Knowledge Graph**: Default graph for all tenants
3. **Index Tables**: Fast lookup tables for entities and documents
4. **Helper Functions**: Tenant graph management functions

```bash
# Verify AGE installation
docker compose exec db psql -U nexusdocs -d nexusdocs -c "
  SELECT extname, extversion FROM pg_extension WHERE extname = 'age';
"

# Check graph exists
docker compose exec db psql -U nexusdocs -d nexusdocs -c "
  LOAD 'age';
  SET search_path = ag_catalog, public;
  SELECT name FROM ag_catalog.ag_graph;
"

# View entity index
docker compose exec db psql -U nexusdocs -d nexusdocs -c "
  SELECT entity_type, count(*) FROM kg_entity_index GROUP BY entity_type;
"
```

### Use Cases

| Use Case | How Graph Helps |
|----------|-----------------|
| **"Find contracts with Juan García"** | Entity lookup → APPEARS_IN → Documents |
| **"Show related people"** | Entity → RELATED_TO traversal |
| **"Documents referencing this one"** | Document → REFERENCES → Documents |
| **"Find all invoices > €10,000"** | AMOUNT entities + APPEARS_IN |
| **Query expansion** | Automatically adds related terms from graph |

---

## ⚖️ BOE Legal Knowledge Base

NouxCubeIA includes a comprehensive **Spanish Legal Knowledge Base** sourced from the Boletín Oficial del Estado (BOE). This enables Emma AI to provide legally-grounded responses when analyzing contracts, compliance documents, and legal questions.

> **📖 Full Documentation**: [`docs/architecture/BOE_LEGAL_KNOWLEDGE.md`](docs/architecture/BOE_LEGAL_KNOWLEDGE.md)

### Key Features

| Feature | Description |
|---------|-------------|
| **13 Legal Domains** | Labor, Tax, Civil, Commercial, GDPR, Compliance, etc. |
| **47+ Laws Indexed** | ET, LOPDGDD, LGT, Código Civil, LSC, and more |
| **Change Detection** | Automatic sync with BOE for legislative updates |
| **Article-Level Diff** | Detailed change tracking with severity classification |
| **Graph Integration** | Laws linked in Apache AGE for relationship queries |

### Initialization

```bash
# Download all core Spanish legislation (first-time setup)
cd backend
python scripts/boe_legislation_downloader.py --preset all

# Or download specific domains
python scripts/boe_legislation_downloader.py --preset laboral
python scripts/boe_legislation_downloader.py --preset fiscal
python scripts/boe_legislation_downloader.py --preset proteccion_datos

# Sync to Legal Knowledge Graph
python scripts/sync_public_knowledge_to_legal_graph.py
```

### Legal Domains Available

| Preset | Laws | Description |
|--------|------|-------------|
| `laboral` | ET, LPRL, LISOS, LETA | Employment & Labor Law |
| `fiscal` | LGT, LIRPF, LIVA | Tax Law |
| `civil` | CC, LEC | Civil Code & Procedure |
| `mercantil` | LSC, CCom | Commercial Law |
| `proteccion_datos` | LOPDGDD | Data Protection (GDPR Spanish) |
| `compliance` | LPBC, CP | AML, Criminal Liability |
| `administrativo` | LPACAP, LRJSP | Administrative Procedure |

---

## 🧠 SLM Router - Small Language Model Query Planning

El **SLM Router** es un sistema de **planificación de queries** que utiliza un Small Language Model (SLM) para generar planes de ejecución estructurados llamados **TOON (Task-Oriented Orchestration Notation)**. Permite enrutar consultas al origen de datos óptimo, ahorrando hasta un **70-90% de tokens**.

> **📖 Documentación completa**: [`docs/architecture/SLM_ROUTER.md`](docs/architecture/SLM_ROUTER.md)

### Problema que Resuelve

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  RAG TRADICIONAL                    →    SLM ROUTER                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ❌ Siempre invoca RAG completo     →    ✅ Enruta al origen de datos óptimo │
│  ❌ Reglas de routing hardcodeadas  →    ✅ Planes generados por LLM         │
│  ❌ 10K+ tokens por consulta        →    ✅ 500-1000 tokens (70-90% ahorro)  │
│  ❌ Sin capacidad de aprendizaje    →    ✅ Aprendizaje continuo automático  │
│  ❌ Lento para consultas simples    →    ✅ <500ms para consultas de grafo   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SLM ROUTER ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Query: "¿Cuántos contratos tiene ACME?"                              │
│       │                                                                      │
│       ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  SLM Client (Qwen2-0.5B)                                             │   │
│   │  Genera plan TOON:                                                   │   │
│   │  {route: GRAPH_ONLY, operation: COUNT, entities: [{ACME, client}]}  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ▼                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  TOON Executor                                                       │   │
│   │  Ejecuta Cypher contra Apache AGE:                                   │   │
│   │  MATCH (d:structural_document {client:'ACME'}) RETURN count(d) → 5  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                      │
│       ▼                                                                      │
│   Emma recibe contexto estructurado → "ACME tiene 5 contratos..."           │
│                                                                              │
│   🎯 NO SE LEYÓ CONTENIDO - 70% ahorro de tokens                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tipos de Ruta (TOON Routes)

| Ruta | Usa RAG | Tiempo | Ejemplo |
|------|---------|--------|---------|
| `GRAPH_ONLY` | ❌ No | <500ms | "¿Cuántos documentos hay?" |
| `VECTOR_ONLY` | ✅ Sí | 1-3s | "Busca información sobre..." |
| `HYBRID` | ✅ Parcial | 2-4s | "Lista contratos ACME y resume riesgos" |
| `ASK_CLARIFY` | ❌ No | <100ms | "documentos" (muy ambiguo) |

### Endpoints SLM Router

```bash
# Planificar y ejecutar query
POST http://localhost:8007/slm/route
{
  "query": "¿Cuántos contratos tiene ACME?",
  "tenant_id": "tenant-uuid",
  "session_id": "session-uuid"
}

# Respuesta (SIN leer contenido de documentos)
{
  "success": true,
  "plan": {
    "route": "GRAPH_ONLY",
    "confidence": 0.92,
    "entities": [{"name": "ACME", "type": "client"}]
  },
  "graph_result": {"count": 5},
  "context_for_llm": "## Structural Information\n**Count:** 5",
  "execution_time_ms": 45
}

# Solo generar plan (sin ejecutar)
POST http://localhost:8007/slm/plan
{
  "query": "Lista todos los contratos de ACME",
  "tenant_id": "tenant-uuid"
}

# Health check
GET http://localhost:8007/slm/health

# Métricas del router
GET http://localhost:8007/slm/metrics
```

### Configuración SLM Router

```bash
# backend/docker/.env

# =============================================================================
# SLM Router - Small Language Model Query Planning
# =============================================================================
SLM_ROUTER_ENABLED=true
SLM_MODEL=Qwen/Qwen2-0.5B-Instruct    # Modelo pequeño y rápido (~1GB VRAM)
SLM_BASE_URL=http://vllm:8000/v1
SLM_TEMPERATURE=0.0                    # Determinístico para planes consistentes
SLM_MAX_TOKENS=512                     # Planes TOON son concisos
SLM_TIMEOUT_MS=3000
```

### Componentes del SLM Router

| Componente | Descripción |
|------------|-------------|
| `SLMClient` | Cliente del Small Language Model (Qwen2-0.5B) |
| `TOONExecutor` | Ejecuta planes contra Apache AGE y Weaviate |
| `TenantSchemaProvider` | Proporciona contexto del tenant |
| `HistoryManager` | Maneja historial de conversación |
| `ContinuousLearningService` | Fine-tuning automático basado en uso |

---

## ✅ Agent Self-Verifies - Generación Verificada (NUEVO)

El patrón **Agent Self-Verifies** implementa generación de documentos donde **cada claim se verifica contra Weaviate** antes de ser aceptado. Reduce alucinaciones en un **~70%** comparado con generación estándar.

### Problema que Resuelve

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  GENERACIÓN TRADICIONAL              →    AGENT SELF-VERIFIES               │
├─────────────────────────────────────────────────────────────────────────────┤
│  ❌ Genera todo de una vez           →    ✅ Genera UN claim a la vez        │
│  ❌ ~15% tasa de alucinación         →    ✅ <5% tasa de alucinación         │
│  ❌ Sin verificación                 →    ✅ Cada claim verificado           │
│  ❌ Confianza binaria                →    ✅ Puntuación de confianza 0-1     │
│  ❌ Sin corrección                   →    ✅ Auto-corrección si es posible   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Arquitectura Stop-and-Go

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    VERIFIED GENERATION FLOW                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐      ┌─────────────────┐      ┌─────────────────┐          │
│  │   WRITER    │      │     CELERY      │      │      REDIS      │          │
│  │   AGENT     │ ───▶ │    VERIFIER     │ ───▶ │      CACHE      │          │
│  │   (vLLM)    │      │  (Weaviate +    │      │   (Verified     │          │
│  │             │      │   vLLM)         │      │    Claims)      │          │
│  └─────────────┘      └─────────────────┘      └─────────────────┘          │
│        │                     │                        │                      │
│        │  1. Genera UN       │  2. Busca evidencia    │  3. Si OK,          │
│        │     claim           │     en Weaviate        │     almacena        │
│        │                     │  3. Evalúa con vLLM    │                      │
│        │                     │  4. Sugiere corrección │                      │
│        │                     │     si es necesario    │                      │
│        │                     │                        │                      │
│        │◀────────────────────┼────────────────────────┤                      │
│        │                     │                        │                      │
│        │  5. Si VERIFIED:    │                        │                      │
│        │     genera siguiente│                        │                      │
│        │  6. Si REJECTED:    │                        │                      │
│        │     intenta corregir│                        │                      │
│        │     o salta         │                        │                      │
│        │                     │                        │                      │
│        └─────────────────────┼────────────────────────┘                      │
│                              │                                               │
│                              ▼                                               │
│                    ┌─────────────────┐                                       │
│                    │ DOCUMENTO FINAL │                                       │
│                    │ (Solo claims    │                                       │
│                    │  verificados)   │                                       │
│                    └─────────────────┘                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Estados de Claims

| Estado | Descripción | Acción |
|--------|-------------|--------|
| `verified` | Evidencia encontrada, confianza >= umbral | ✅ Incluir en documento |
| `corrected` | Sin evidencia exacta, pero LLM sugirió corrección | ✅ Incluir versión corregida |
| `rejected` | Sin evidencia suficiente, sin corrección posible | ❌ Descartar |
| `error` | Error durante verificación (timeout, etc.) | 🔄 Reintentar o descartar |

### Endpoints Verified Generation

```bash
# Generar documento verificado (síncrono)
POST http://localhost:8007/verified/generate
{
  "query": "Genera un resumen del proyecto Alpha basado en los documentos",
  "tenant_id": "tenant-uuid",
  "max_claims": 10,
  "confidence_threshold": 0.7
}

# Respuesta
{
  "session_id": "uuid",
  "query": "Genera un resumen del proyecto Alpha...",
  "document_text": "El proyecto Alpha inició el 15 de marzo de 2024...",
  "claims": [
    {
      "id": "claim-uuid",
      "text": "El proyecto Alpha inició el 15 de marzo de 2024",
      "status": "verified",
      "confidence": 0.92,
      "evidence": [
        {
          "document_id": "doc-uuid",
          "document_title": "Acta de inicio Proyecto Alpha",
          "text_excerpt": "...fecha de inicio oficial: 15 de marzo de 2024...",
          "similarity_score": 0.89
        }
      ]
    },
    {
      "id": "claim-uuid-2",
      "text": "El presupuesto inicial fue de 150.000 euros",
      "status": "corrected",
      "confidence": 0.78,
      "original_text": "El presupuesto inicial fue de 200.000 euros",
      "correction_reason": "Evidencia muestra 150.000€, no 200.000€"
    }
  ],
  "total_claims_generated": 10,
  "claims_verified": 7,
  "claims_corrected": 2,
  "claims_rejected": 1,
  "average_confidence": 0.85,
  "execution_time_ms": 45000,
  "verification_time_ms": 38000
}

# Generar con streaming SSE (progreso en tiempo real)
POST http://localhost:8007/verified/generate/stream
Content-Type: application/json

# Eventos SSE:
# data: {"event": "claim_generated", "claim": {...}}
# data: {"event": "verification_started", "task_id": "..."}
# data: {"event": "claim_verified", "result": {...}}
# data: {"event": "claim_rejected", "reason": "..."}
# data: {"event": "document_complete", "document": {...}}

# Obtener claims verificados de una sesión
GET http://localhost:8007/verified/session/{session_id}/claims

# Estadísticas de sesión
GET http://localhost:8007/verified/session/{session_id}/stats

# Limpiar sesión
DELETE http://localhost:8007/verified/session/{session_id}
```

### Configuración Verified Generation

```bash
# backend/docker/.env

# =============================================================================
# VERIFIED GENERATION (Agent Self-Verifies Pattern)
# =============================================================================
# Reduce alucinaciones ~70% vs generación estándar

# Máximo número de claims por documento
VERIFIED_MAX_CLAIMS=20

# Temperatura para generación (bajo = más factual)
VERIFIED_CLAIM_TEMPERATURE=0.3

# Timeout por claim (segundos)
VERIFIED_TIMEOUT_SECONDS=45

# Umbral mínimo de confianza para aceptar claim
VERIFIED_CONFIDENCE_THRESHOLD=0.7

# Intentos de corrección por claim
VERIFIED_MAX_CORRECTION_ATTEMPTS=2

# Auto-aceptar correcciones sugeridas por LLM
VERIFIED_AUTO_ACCEPT_CORRECTIONS=true

# TTL del cache en Redis (segundos)
VERIFIED_CACHE_TTL_SECONDS=3600
```

### Cola Celery para Verificación

El sistema usa una cola Celery dedicada para tareas de verificación:

```bash
# El worker debe escuchar la cola "verification"
celery -A worker_app.celery_app worker -Q default,verification,...

# Tareas registradas:
# - verification.verify_claim
# - verification.batch_verify_claims
```

### Métricas de Rendimiento

| Métrica | Valor Típico | Notas |
|---------|--------------|-------|
| Tiempo por claim | 30-50s | Incluye búsqueda + evaluación |
| Tasa de verificación | 70-85% | Claims que pasan verificación |
| Tasa de corrección | 10-20% | Claims auto-corregidos |
| Tasa de rechazo | 5-15% | Claims descartados |
| Ahorro vs alucinación | ~70% | Reducción de información falsa |

---

## RAG Pipeline: Query Flow

When a user asks Emma a question, the query flows through a sophisticated 7-layer RAG pipeline:

### Query Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAG PIPELINE - QUERY FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Query: "What are the payment terms in the service agreement?"         │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 1: Query Analysis                                            │    │
│  │  • Intent detection (search, analysis, comparison, etc.)            │    │
│  │  • Entity extraction (dates, amounts, names)                        │    │
│  │  • Query expansion (synonyms, related terms)                        │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 2: Multi-Stage Retrieval                                     │    │
│  │                                                                      │    │
│  │  ┌──────────────┐    ┌──────────────┐                               │    │
│  │  │ Dense Search │    │ Sparse BM25  │    (50 candidates each)       │    │
│  │  │  (Vectors)   │    │  (Keywords)  │                               │    │
│  │  └──────┬───────┘    └──────┬───────┘                               │    │
│  │         │                   │                                        │    │
│  │         └─────────┬─────────┘                                        │    │
│  │                   ▼                                                  │    │
│  │  ┌──────────────────────────────────────────────────────────┐       │    │
│  │  │  RRF Fusion (Reciprocal Rank Fusion)                     │       │    │
│  │  │  score(d) = Σ 1/(k + rank_i(d))  where k=60             │       │    │
│  │  │  +15-20% recall improvement over weighted average        │       │    │
│  │  └──────────────────────────────────────────────────────────┘       │    │
│  │                                                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 3: Cross-Encoder Reranking                                   │    │
│  │  • Precise relevance scoring (query, document) pairs                │    │
│  │  • Reduces 100 → 20 candidates                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 4: Public Knowledge Augmentation (Optional)                  │    │
│  │  • BOE legislation lookup (if legal query detected)                 │    │
│  │  • Adds regulatory context from indexed laws                        │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 5: Context Assembly                                          │    │
│  │  • Token budget allocation (fit within context window)              │    │
│  │  • Document grouping (keep related chunks together)                 │    │
│  │  • Diversity optimization (avoid redundancy)                        │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 6: Agent Orchestration (Emma Coordinator)                    │    │
│  │  • Pattern selection (handoff/sequential/concurrent/rlm)            │    │
│  │  • Agent delegation based on query domain                           │    │
│  │  • Tool calling for specialized analysis                            │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  LAYER 7: Response Generation                                       │    │
│  │  • LLM inference (vLLM with Qwen3)                                  │    │
│  │  • Citation injection (document references)                         │    │
│  │  • Thinking tag cleanup (remove <think> blocks)                     │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  Response: "The payment terms in the service agreement state..."            │
│  [Sources: doc-123:chunk-5, doc-456:chunk-2]                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### RAG Configuration

```bash
# =============================================================================
# RAG Pipeline Configuration
# =============================================================================
# Retrieval settings
RAG_DENSE_CANDIDATES=50
RAG_SPARSE_CANDIDATES=50
RAG_RERANK_TOP_K=20
RAG_FINAL_TOP_K=10

# RRF Fusion
RAG_RRF_K=60
RAG_DENSE_WEIGHT=1.0
RAG_SPARSE_WEIGHT=1.0

# Context assembly
RAG_MAX_CONTEXT_TOKENS=24000
RAG_CHUNK_OVERLAP=100

# Public Knowledge (BOE)
RAG_PUBLIC_KNOWLEDGE_ENABLED=true
RAG_PUBLIC_KNOWLEDGE_WEIGHT=0.3
RAG_PUBLIC_KNOWLEDGE_LIMIT=5
RAG_PUBLIC_KNOWLEDGE_CATEGORIES=laboral,fiscal,proteccion_datos
```

### Multi-Tier RAG Caching

NouxCubeIA implements a sophisticated multi-tier caching system that combines RAG with CAG (Cache-Augmented Generation) patterns. This significantly reduces latency and compute costs for on-premise deployments.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CACHE HIT PERFORMANCE BENEFITS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Tier 1 Hit (Retrieval)    │  Skip vector search      │  200-500ms saved    │
│  Tier 2 Hit (Context)      │  Skip doc assembly       │  50-200ms saved     │
│  Tier 3 Hit (Semantic)     │  Skip entire RAG + LLM   │  3-10 seconds saved │
│                                                                              │
│  Combined effect for repetitive workloads:                                  │
│  • 40-60% of queries hit at least one cache tier                           │
│  • Average latency reduction: 50-70%                                        │
│  • vLLM GPU utilization reduction: 30-50%                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Cache Configuration

```bash
# backend/docker/.env

# =============================================================================
# MULTI-TIER RAG CACHING (Reduces latency and GPU load)
# =============================================================================

# TIER 1: Retrieval Cache
# Caches vector search results (doc_ids + scores)
# User-isolated for ACL security
RETRIEVAL_CACHE_ENABLED=true
RETRIEVAL_CACHE_TTL_SECONDS=300        # 5 minutes (short for freshness)
RETRIEVAL_CACHE_MAX_ENTRIES=500        # Max cached queries per tenant

# TIER 2: Context Assembly Cache
# Caches assembled context strings ready for LLM
# Key insight: Different queries retrieving same docs share context
CONTEXT_CACHE_ENABLED=true
CONTEXT_CACHE_TTL_SECONDS=1800         # 30 minutes
CONTEXT_CACHE_MAX_SIZE_MB=100          # Max cache size

# TIER 3: Semantic Cache (existing)
# Caches final LLM responses for semantically similar queries
RAG_CACHE_ENABLED=true
RAG_CACHE_TTL_SECONDS=3600             # 1 hour
RAG_SEMANTIC_CACHE_SIMILARITY=0.92     # Similarity threshold
```

#### Cache Invalidation

The system automatically invalidates caches when data changes:

| Event | What Happens | Latency Impact |
|-------|--------------|----------------|
| **Document updated** | Invalidates all caches referencing that document | ~10ms |
| **Document deleted** | Invalidates all caches referencing that document | ~10ms |
| **Index rebuilt** | Invalidates ALL caches for tenant | ~100ms |
| **Chunking changed** | Invalidates context + semantic caches | ~50ms |

```bash
# Manual cache invalidation (admin API)
# Invalidate caches for specific documents
curl -X POST http://localhost:8007/api/v1/cache/invalidate \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"document_ids": ["doc-123", "doc-456"]}'

# Get cache health statistics
curl http://localhost:8007/api/v1/cache/health \
  -H "X-Tenant-ID: $TENANT_ID" | jq
```

#### Monitoring Cache Performance

```bash
# Check Redis cache usage
docker compose exec redis redis-cli INFO memory | grep used_memory_human

# View cache keys for a tenant
docker compose exec redis redis-cli KEYS "retrieval:tenant-123:*" | wc -l
docker compose exec redis redis-cli KEYS "context:tenant-123:*" | wc -l

# Cache statistics endpoint
curl http://localhost:8007/api/v1/cache/stats \
  -H "X-Tenant-ID: $TENANT_ID" | jq

# Response:
# {
#   "retrieval_cache": {"hits": 1234, "misses": 567, "hit_rate": 0.68},
#   "context_cache": {"hits": 890, "misses": 234, "hit_rate": 0.79},
#   "semantic_cache": {"hits": 456, "misses": 123, "hit_rate": 0.78}
# }
```

#### Hardware Considerations for Caching

| Scenario | Redis Memory | Recommendation |
|----------|--------------|----------------|
| **Small (1-10 users)** | 256MB | Default config works |
| **Medium (10-50 users)** | 1GB | Increase TTL for better hit rates |
| **Large (50+ users)** | 2-4GB | Consider Redis Cluster |

```bash
# Increase Redis memory limit in docker-compose.yml
redis:
  deploy:
    resources:
      limits:
        memory: 2G
```

---

### Testing the Pipeline

```bash
# 1. Simple search query
curl -X POST http://localhost:8007/api/v1/emma/ask \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "question": "Find all contracts from 2024",
    "workflow_type": "auto"
  }' | jq

# 2. Legal analysis query (triggers Public Knowledge)
curl -X POST http://localhost:8007/api/v1/emma/ask \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "question": "Is this employment contract compliant with the Workers Statute?",
    "document_ids": ["doc-123"],
    "workflow_type": "sequential"
  }' | jq

# 3. Multi-document comparison (concurrent pattern)
curl -X POST http://localhost:8007/api/v1/emma/ask \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -d '{
    "question": "Compare the terms between contract A and contract B",
    "document_ids": ["doc-123", "doc-456"],
    "workflow_type": "concurrent"
  }' | jq
```

---

## Quick Start

### Prerequisites

```bash
# 1. NVIDIA Driver (535+)
nvidia-smi  # Should show your GPU

# 2. Docker with NVIDIA Runtime
docker run --rm --gpus all nvidia/cuda:12.2-base nvidia-smi

# 3. Docker Compose v2
docker compose version  # Should be 2.x+

# 4. HuggingFace Token (for Qwen3 models)
# Get from: https://huggingface.co/settings/tokens
```

### Installation

```bash
# 1. Clone repository
git clone https://github.com/your-org/nexus-documents-ia.git
cd nexus-documents-ia

# 2. Configure environment
cp backend/docker/.env.example backend/docker/.env

# 3. Edit .env with your configuration
nano backend/docker/.env
```

### Environment Configuration

```bash
# backend/docker/.env

# =============================================================================
# GPU / vLLM Configuration
# =============================================================================
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx  # Required for Qwen3 models
VLLM_ENABLED=true
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_MODEL=Qwen/Qwen3-4B-Thinking-2507
VLLM_MAX_MODEL_LEN=32768  # 32K for multimodal, 262144 for text-only

# GPU Memory Utilization (0.0-1.0)
# Lower = less VRAM but slower, Higher = more VRAM but faster
VLLM_GPU_MEMORY_UTILIZATION=0.45

# =============================================================================
# Embedding Configuration
# =============================================================================
# Option A: Multimodal (recommended)
EMBEDDING_PROVIDER=qwen3-vl
EMBEDDING_MODEL=Qwen/Qwen3-VL-Embedding-2B
EMBEDDING_URL=http://qwen3-vl-embedding:8001/v1
MULTIMODAL_EMBEDDING_ENABLED=true

# Option B: Text-only (maximum context)
# EMBEDDING_PROVIDER=qwen3
# EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
# MULTIMODAL_EMBEDDING_ENABLED=false

# =============================================================================
# Fallback LLM Providers (optional)
# =============================================================================
# Used when vLLM is unavailable or for specific tasks
OPENAI_API_KEY=sk-...       # Optional fallback
ANTHROPIC_API_KEY=sk-ant-...  # Optional fallback

# =============================================================================
# Database
# =============================================================================
POSTGRES_USER=nexusdocs
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=nexusdocs
DATABASE_URL=postgresql://nexusdocs:your-secure-password@db:5432/nexusdocs

# =============================================================================
# Storage
# =============================================================================
# Option A: Local storage
STORAGE_PROVIDER=local
LOCAL_STORAGE_PATH=/data/documents

# Option B: Google Cloud Storage
# STORAGE_PROVIDER=gcs
# GCS_BUCKET=your-bucket-name
# GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcs-key.json

# =============================================================================
# Security
# =============================================================================
SECRET_KEY=your-very-long-random-secret-key
JWT_SECRET=another-very-long-random-secret

# =============================================================================
# Redis
# =============================================================================
REDIS_URL=redis://redis:6379

# =============================================================================
# Weaviate
# =============================================================================
WEAVIATE_URL=http://weaviate:8080
```

### Start Services

```bash
# 1. Start all services
cd backend/docker
docker compose up -d

# 2. Watch startup logs (vLLM model download takes time on first run)
docker compose logs -f vllm

# 3. Check all services are healthy
docker compose ps

# 4. Verify API is responding
curl http://localhost:8000/health

# 5. Verify vLLM is loaded
curl http://localhost:8000/v1/models
```

### First Run Expectations

```
┌─────────────────────────────────────────────────────────────────┐
│                    FIRST RUN TIMELINE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  0-5 min    Infrastructure starts (db, redis, weaviate)         │
│                                                                  │
│  5-15 min   vLLM downloads Qwen3-4B model (~8GB)                │
│             (subsequent starts are instant)                      │
│                                                                  │
│  5-10 min   Embedding model downloads (~4GB)                    │
│             (parallel with vLLM)                                 │
│                                                                  │
│  15-20 min  All services healthy, ready to use                  │
│                                                                  │
│  Note: Model files are cached in Docker volumes                 │
│        Subsequent starts take ~2 minutes                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Testing the Installation

### 1. Check vLLM Health

```bash
# List available models
curl http://localhost:8000/v1/models | jq

# Test chat completion
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-4B-Thinking-2507",
    "messages": [{"role": "user", "content": "What is 25 * 4? Think step by step."}],
    "max_tokens": 500
  }' | jq
```

### 2. Check Embedding Service

```bash
# Test embedding generation
curl http://localhost:8001/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-VL-Embedding-2B",
    "input": ["This is a test document about contracts"]
  }' | jq '.data[0].embedding | length'
# Should return 1024 (embedding dimensions)
```

### 3. Check Main API

```bash
# Health check
curl http://localhost:8000/health | jq

# API docs
open http://localhost:8000/docs
```

### 4. Check Emma AI

```bash
# Test Emma endpoint (requires authentication)
curl -X POST http://localhost:8007/api/v1/emma/ask \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: test-tenant" \
  -d '{
    "question": "What documents do I have?",
    "workflow_type": "auto"
  }' | jq
```

---

## Monitoring

### GPU Monitoring

```bash
# Real-time GPU usage
watch -n 1 nvidia-smi

# vLLM metrics (Prometheus format)
curl http://localhost:8000/metrics | grep vllm
```

### Service Health

```bash
# All service status
docker compose ps

# Service logs
docker compose logs -f api
docker compose logs -f weaviate-service
docker compose logs -f vllm
```

### Prometheus Metrics

All services expose Prometheus metrics:

| Service | Metrics Endpoint |
|---------|------------------|
| api | http://localhost:8000/metrics |
| vllm | http://localhost:8000/metrics |
| weaviate | http://localhost:8080/v1/.well-known/ready |

---

## Troubleshooting

### CUDA Out of Memory

```bash
# Symptom: vLLM fails to load model
# Solution 1: Reduce GPU memory utilization
VLLM_GPU_MEMORY_UTILIZATION=0.35  # Lower from 0.45

# Solution 2: Use smaller context
VLLM_MAX_MODEL_LEN=16384  # Reduce from 32768

# Solution 3: Disable multimodal embedding
MULTIMODAL_EMBEDDING_ENABLED=false
# This frees ~5GB VRAM
```

### Model Download Fails

```bash
# Symptom: "401 Unauthorized" or "Model not found"
# Solution: Verify HuggingFace token

# 1. Check token is set
echo $HF_TOKEN

# 2. Test token works
curl -H "Authorization: Bearer $HF_TOKEN" \
  https://huggingface.co/api/whoami

# 3. Ensure you've accepted Qwen3 license
# Visit: https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507
```

### Services Not Starting

```bash
# Check which services are unhealthy
docker compose ps

# View logs for failed service
docker compose logs vllm
docker compose logs qwen3-vl-embedding

# Common issues:
# - Port already in use: stop conflicting services
# - Insufficient disk: docker system prune
# - NVIDIA driver issues: restart docker daemon
```

### Embedding Service Unavailable

```bash
# Symptom: Embedding requests timeout
# Check service status
docker compose logs qwen3-vl-embedding

# If model loading fails, try text-only embedding:
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
MULTIMODAL_EMBEDDING_ENABLED=false
```

---

## Scaling

### Vertical Scaling (Single Node)

```bash
# Add more GPU memory utilization (if available)
VLLM_GPU_MEMORY_UTILIZATION=0.85

# Increase worker processes
API_WORKERS=4
CELERY_WORKERS=8
```

### Horizontal Scaling (Multiple Nodes)

```yaml
# docker-compose.prod.yml example
services:
  api:
    deploy:
      replicas: 3

  vllm:
    deploy:
      placement:
        constraints:
          - node.labels.gpu == true
```

### High Availability

For production deployments:

1. **Database**: Use PostgreSQL with streaming replication
2. **Redis**: Use Redis Sentinel or Cluster
3. **Weaviate**: Configure multi-node cluster
4. **Load Balancer**: nginx or Traefik in front of API

---

## Backup & Recovery

### Database Backup

```bash
# Automated daily backup
docker compose exec db pg_dump -U nexusdocs nexusdocs > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T db psql -U nexusdocs nexusdocs < backup_20240115.sql
```

### Document Storage Backup

```bash
# If using local storage
rsync -av /data/documents/ /backup/documents/

# If using GCS
gsutil -m rsync -r gs://your-bucket /backup/gcs/
```

### Weaviate Backup

```bash
# Create backup
curl -X POST http://localhost:8080/v1/backups/filesystem \
  -H "Content-Type: application/json" \
  -d '{"id": "backup-2024-01-15"}'

# Restore
curl -X POST http://localhost:8080/v1/backups/filesystem/backup-2024-01-15/restore
```

---

## Security Hardening

### Network Security

```yaml
# docker-compose.prod.yml
networks:
  backend:
    internal: true  # No external access
  frontend:
    # Only API exposed
```

### Secrets Management

```bash
# Use Docker secrets instead of environment variables
docker secret create db_password db_password.txt
docker secret create hf_token hf_token.txt
```

### SSL/TLS

```bash
# Use reverse proxy with SSL
# Example: nginx with Let's Encrypt
apt install certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

---

## Updates

### Updating NouxCubeIA

```bash
# 1. Pull latest code
git pull origin main

# 2. Rebuild containers
cd backend/docker
docker compose build --no-cache

# 3. Apply database migrations
docker compose exec api alembic upgrade head

# 4. Restart services
docker compose up -d
```

### Updating Models

```bash
# Update vLLM model
# Edit .env with new model name
VLLM_MODEL=Qwen/Qwen3-8B-Thinking  # Example upgrade

# Restart vLLM service
docker compose restart vllm
```

---

## Support

### Community Support

- GitHub Issues: https://github.com/your-org/nexusdocs360/issues
- Discord: https://discord.gg/nexusdocs360

### Enterprise Support

- Email: enterprise@nexusdocs360.com
- On-site installation available
- Custom model training
- SLA options

---

<div align="center">
  <p><strong>Ready for complete data sovereignty?</strong></p>
  <p>
    <a href="#quick-start">Quick Start</a> |
    <a href="#troubleshooting">Troubleshooting</a> |
    <a href="mailto:enterprise@nexusdocs360.com">Enterprise Support</a>
  </p>
</div>
