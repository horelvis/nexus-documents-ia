# NexusDocs360 On-Premise - Self-Hosted Deployment

<div align="center">
  <h3>Full Control, Local GPU Inference, Data Sovereignty</h3>
  <p><strong>Run NexusDocs360 on your own infrastructure</strong></p>
</div>

---

## Overview

NexusDocs360 On-Premise is designed for organizations that require complete control over their data and infrastructure. With local GPU inference via vLLM and Qwen3 models, you get enterprise-grade AI capabilities without sending data to external providers.

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

### Minimum Configuration (Text-Only)

| Component | Specification |
|-----------|---------------|
| **GPU** | NVIDIA RTX 3090 (24GB VRAM) |
| **CPU** | 8+ cores (Intel i7/AMD Ryzen 7) |
| **RAM** | 32GB DDR4 |
| **Storage** | 500GB NVMe SSD |
| **Network** | 1 Gbps |

### Recommended Configuration (Multimodal RAG)

| Component | Specification |
|-----------|---------------|
| **GPU** | NVIDIA RTX 4090 (24GB VRAM) |
| **CPU** | 16+ cores (Intel i9/AMD Ryzen 9) |
| **RAM** | 64GB DDR5 |
| **Storage** | 1TB NVMe SSD + 4TB HDD |
| **Network** | 10 Gbps |

### Enterprise Configuration (High Throughput)

| Component | Specification |
|-----------|---------------|
| **GPU** | 2x NVIDIA A100 (80GB) or H100 |
| **CPU** | 32+ cores (AMD EPYC/Intel Xeon) |
| **RAM** | 256GB ECC |
| **Storage** | 2TB NVMe RAID + NAS |
| **Network** | 25 Gbps |

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
│                     NexusDocs360 On-Premise Architecture                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        Docker Compose Stack                          │    │
│  │                                                                      │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                     Application Services                     │    │    │
│  │  │                                                              │    │    │
│  │  │  ┌──────────┐  ┌─────────────────┐  ┌──────────────────┐   │    │    │
│  │  │  │   api    │  │ weaviate-service│  │ background-worker│   │    │    │
│  │  │  │ FastAPI  │  │  RAG + Emma AI  │  │     Celery       │   │    │    │
│  │  │  │  :8000   │  │     :8007       │  │     :8100        │   │    │    │
│  │  │  └──────────┘  └─────────────────┘  └──────────────────┘   │    │    │
│  │  │                                                              │    │    │
│  │  │  ┌──────────┐  ┌─────────────────┐  ┌──────────────────┐   │    │    │
│  │  │  │langextract│ │  mcp-storage    │  │   tts-service    │   │    │    │
│  │  │  │  :8009   │  │     :8003       │  │  (VibeVoice)     │   │    │    │
│  │  │  └──────────┘  └─────────────────┘  └──────────────────┘   │    │    │
│  │  │                                                              │    │    │
│  │  └──────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                GPU Services (NVIDIA CUDA)                    │    │    │
│  │  │                                                              │    │    │
│  │  │  ┌────────────────────────┐  ┌─────────────────────────┐   │    │    │
│  │  │  │         vllm          │  │   qwen3-vl-embedding    │   │    │    │
│  │  │  │  Qwen3-4B-Thinking    │  │  Multimodal Embedding   │   │    │    │
│  │  │  │       :8000           │  │        :8001            │   │    │    │
│  │  │  └────────────────────────┘  └─────────────────────────┘   │    │    │
│  │  │                                                              │    │    │
│  │  └──────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                     Infrastructure                           │    │    │
│  │  │                                                              │    │    │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │    │    │
│  │  │  │    db    │  │  redis   │  │ weaviate │  │  keycloak │   │    │    │
│  │  │  │PostgreSQL│  │  Cache   │  │ VectorDB │  │ SSO (opt) │   │    │    │
│  │  │  │  + AGE   │  │  :6379   │  │  :8080   │  │   :8080   │   │    │    │
│  │  │  │  :5432   │  │          │  │          │  │           │   │    │    │
│  │  │  └──────────┘  └──────────┘  └──────────┘  └───────────┘   │    │    │
│  │  │                                                              │    │    │
│  │  └──────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
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

Emma is the intelligent assistant built on **Qwen-Agent** framework with multi-pattern orchestration. The system automatically selects the best execution pattern based on query analysis.

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

NexusDocs360 can sync documents from external systems via the **Connector Adapter** system. This enables unified search across your organization's document repositories.

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

### Updating NexusDocs360

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
