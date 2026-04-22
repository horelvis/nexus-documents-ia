# NouxCubeIA Onboarding Guide

Complete guide for initial deployment and content ingestion on a new NouxCubeIA installation. Covers initial setup, bulk indexing optimization, legislation download, and go-live checklist.

---

## Architecture Overview

```
                           ONBOARDING MODE                    NORMAL MODE
                      ┌─────────────────────┐          ┌─────────────────────┐
                      │                     │          │                     │
   GPU (24GB VRAM)    │  Docling GPU        │    →     │  SGLang (Qwen3.5-9B)│
                      │  5-10x faster PDF   │          │  Emma AI agent      │
                      │                     │          │                     │
                      ├─────────────────────┤          ├─────────────────────┤
                      │                     │          │                     │
   CPU + RAM          │  textextract        │          │  textextract        │
                      │  weaviate-service   │          │  weaviate-service   │
                      │  MCP connectors     │          │  emma-agent-service │
                      │  knowledge-tree     │          │  MCP connectors     │
                      │                     │          │                     │
                      └─────────────────────┘          └─────────────────────┘
                                │                                │
                      Emma NOT available              Emma fully operational
                      Indexing at max speed            Incremental syncs
```

The key insight: **SGLang and Docling compete for the same GPU**. During onboarding, bulk indexing is the priority, so we dedicate the GPU to Docling. Once indexing is complete, we swap the GPU to SGLang and Emma becomes operational.

---

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| GPU | NVIDIA RTX 3090 (24GB) | NVIDIA RTX 4090 (24GB) |
| RAM | 32GB | 64GB |
| CPU | 8 cores | 16 cores |
| Disk | 100GB SSD | 500GB NVMe |
| Docker | 24.0+ with Compose v2 | Latest |
| NVIDIA Driver | 535+ | 550+ |
| nvidia-container-toolkit | Installed | Installed |

Verify GPU access:
```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

---

## Quick Start (5 commands)

```bash
cd backend/docker

# 1. Enter onboarding mode (GPU → Docling)
./onboarding.sh start

# 2. Download Spanish legislation (13 presets, ~47 laws)
./onboarding.sh boe

# 3. Index all connected data sources
./onboarding.sh sync-all

# 4. Monitor progress
./onboarding.sh status

# 5. Go live (GPU → vLLM, Emma operational)
./onboarding.sh finish
```

---

## Detailed Process

### Phase 0: Initial Setup

Before onboarding, start the platform and complete initial configuration:

**Step 1: Start all services**

```bash
cd backend/docker
docker compose up -d
```

Wait for all services to report healthy:

```bash
docker compose ps
```

**Step 2: Apply database migrations**

```bash
docker exec docker-api-1 alembic upgrade head
```

**Step 3: Seed initial database**

```bash
docker exec docker-api-1 python -m scripts.init_db
```

**Step 4: Configure KeyCloak authentication**

Configure groups and role mappings per your deployment:

- See [`AUTHENTICATION.md`](AUTHENTICATION.md) for OIDC/SAML setup and `role_mapping.yaml` group configuration.

**Step 5: Seed Langfuse prompts**

Before Emma can answer queries, Langfuse must have the initial prompt set:

```bash
# Seed all prompt migrations in order:
docker compose exec emma-agent-service python scripts/migrate_9b_prompt_optimization.py
docker compose exec emma-agent-service python scripts/migrate_explain_prompts.py
docker compose exec emma-agent-service python scripts/migrate_ner_prompts.py
docker compose exec emma-agent-service python scripts/migrate_retrieval_intelligence_prompts.py
docker compose exec emma-agent-service python scripts/migrate_trustgraph_phase2_prompts.py
docker compose exec emma-agent-service python scripts/migrate_knowledge_report_prompt.py
docker compose exec emma-agent-service python scripts/seed_guardrails.py
```

Promote prompts to the `production` label in the Langfuse UI (http://localhost:3002) — see [`LANGFUSE_SETUP.md`](../guides/LANGFUSE_SETUP.md) for production-label pinning details.

**Step 6: Add data source connectors**

- See [`CONNECTORS.md`](CONNECTORS.md) for Google Drive, OneDrive, Alfresco connector setup.

### Phase 1: Enter Onboarding Mode

```bash
./onboarding.sh start
```

This command:
1. Ensures all base services are running
2. **Stops SGLang** (`sglang` service — frees ~22GB VRAM)
3. Stops Docling CPU (if running)
4. **Starts Docling GPU** (uses freed VRAM)
5. Restarts weaviate-service with `RAG_HIERARCHICAL_ENABLED=false`

**What's disabled:**
| Feature | Why | Impact |
|---------|-----|--------|
| SGLang (LLM inference) | Free GPU for Docling | Emma chat unavailable |
| RAG hierarchical summaries | Require LLM | No document-level summaries (minor retrieval impact on very long docs) |

**What's NOT disabled:**
- Text extraction (Docling GPU - faster)
- Semantic chunking (CPU, regex-based)
- Embedding generation (BGE-M3, separate from vLLM)
- Document intelligence (CPU heuristics)
- Contextual retrieval (rule-based mode, no LLM)
- Knowledge graph population

### Phase 2: Download Legislation (optional)

For tenants that need Spanish legal knowledge:

```bash
# All 13 presets (~47 laws) — recommended for legal/compliance sectors
./onboarding.sh boe

# Or specific presets
./onboarding.sh boe laboral      # Labor laws (ET, LPRL, etc.)
./onboarding.sh boe fiscal       # Tax laws (LGT, LIRPF, etc.)
./onboarding.sh boe compliance   # Compliance (LPBC, CP, etc.)
```

Available presets:

| Preset | Laws | Description |
|--------|------|-------------|
| `laboral` | 7 | Estatuto Trabajadores, PRL, LISOS, LOI, LETA, LGSS, LTD |
| `fiscal` | 5 | LGT, LIRPF, LIS, LIVA, Reglamento Facturación |
| `mercantil` | 3 | LSC, CCom, LSP |
| `civil` | 2 | CC, LEC |
| `administrativo` | 3 | LPACAP, LRJSP, LCSP |
| `compliance` | 5 | LPBC, CP, LC, LSE, Auditoría |
| `propiedad_intelectual` | 3 | LPI, LM, LP |
| `comercio_consumidores` | 5 | LGDCU, LCD, LOCM, LGUM, LSSI |
| `emprendimiento` | 3 | LE, LCC, LS |
| `inmobiliario` | 5 | LAU, LPH, LH, Crédito Inmobiliario |
| `contabilidad` | 2 | PGC, PGC Pymes |
| `educacion` | 3 | LOMLOE, LOE, LOU |
| `proteccion_datos` | 1 | LOPDGDD |

> BOE legislation is indexed into the unified TrustGraph — see [`TRUSTGRAPH.md`](../architecture/TRUSTGRAPH.md) for details on the knowledge graph pipeline.

### Phase 3: Index Data Sources

```bash
# Index ALL active connectors
./onboarding.sh sync-all

# Or index a specific connector
./onboarding.sh sync <connector-id>
```

Monitor progress:
```bash
./onboarding.sh status
```

Output example:
```
[ONBOARD] Indexing status across all connectors:

  Google Drive - Javi Venzia (google_drive):
    indexed=563  pending=0  processing=0  failed=204  skipped=173  total=940
    progress: 59%

  Alfresco DMS (alfresco):
    indexed=124  pending=3  processing=0  failed=2  skipped=0  total=129
    progress: 96%
```

**Document statuses:**

| Status | Meaning | Action |
|--------|---------|--------|
| `indexed` | Successfully processed and searchable | None |
| `pending` | Waiting to be processed | Will be picked up on next sync |
| `processing` | Currently being indexed | Wait |
| `failed` | Error during processing | Check `indexing_error` column for details |
| `skipped` | Unsupported file type | Permanent — file type not processable |

#### Supported File Types

The indexing pipeline processes these extensions:

| Category | Extensions |
|----------|-----------|
| Documents | `.pdf`, `.doc`, `.docx`, `.odt`, `.rtf`, `.epub` |
| Spreadsheets | `.xlsx`, `.xls`, `.csv` |
| Presentations | `.ppt`, `.pptx` |
| Text | `.txt`, `.md`, `.html`, `.xml`, `.json` |
| Images (OCR) | `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, `.bmp`, `.gif` |

Files with unsupported extensions (`.zip`, `.mp4`, `.webm`, `.gz`, `.rar`, `.bmpr`, etc.) are automatically **skipped** before download to save bandwidth and processing time.

#### Handling Failed Documents

Common failure reasons:

| Error | Cause | Fix |
|-------|-------|-----|
| `403 Forbidden` | No permission to read file | Check connector OAuth scopes |
| `Extraction timeout` | PDF too complex for Docling | Increase `DOCLING_SERVE_MAX_SYNC_WAIT` |
| `No text content extracted` | OCR failed on image | File may be blank or corrupted |
| `Connection failed` | Service was down during indexing | Re-sync to retry pending docs |

To retry failed documents:
```bash
# Reset retryable failures to pending
docker exec docker-db-1 psql -U nexus_user -d nouxcube -c "
  UPDATE indexed_documents
  SET indexing_status = 'pending', indexing_error = NULL
  WHERE indexing_status = 'failed'
    AND connector_id = '<connector-id>'
    AND indexing_error NOT LIKE '%403 Forbidden%'
    AND indexing_error NOT LIKE '%Unsupported%'
"

# Then re-sync
./onboarding.sh sync <connector-id>
```

### Phase 4: Go Live

Once all connectors show acceptable indexed percentages:

```bash
./onboarding.sh finish
```

This command:
1. Stops Docling GPU
2. Starts the full normal stack (SGLang + Docling CPU)
3. Waits for SGLang to load the model (~2-3 min)
4. Shows final indexing stats

After this, Emma is fully operational.

---

## Performance Tuning

### Indexing Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  Connector   │────▶│ textextract │────▶│   Weaviate   │────▶│ Knowledge│
│  (download)  │     │  (Docling)  │     │   Service    │     │   Graph  │
│              │     │             │     │  (chunk +    │     │(FalkorDB)│
│  20 parallel │     │ 4 workers   │     │   embed)     │     │          │
└─────────────┘     └─────────────┘     └──────────────┘     └──────────┘
    ~50ms/doc          ~3-30s/doc          ~2-5s/doc           ~1s/doc
   (network)        (CPU or GPU)       (BGE-M3 embed)      (graph insert)
```

| Parameter | Default | Onboarding | Location |
|-----------|---------|------------|----------|
| Connector concurrency | 20 | 20 | `sync_service.py` (`_INDEXABLE_EXTENSIONS` + semaphore) |
| Docling workers | 2 (CPU) / 4 (GPU) | 4 | `docker-compose.onboarding.yml` |
| Docling OMP threads | 4 (CPU) / 8 (GPU) | 8 | `docker-compose.onboarding.yml` |
| Docling memory limit | 8GB (CPU) / 12GB (GPU) | 12GB | `docker-compose.onboarding.yml` |
| Max sync wait | 300s | 300s | `DOCLING_SERVE_MAX_SYNC_WAIT` |
| Hierarchical summaries | enabled | **disabled** | `RAG_HIERARCHICAL_ENABLED` |

### Expected Throughput

| Document Type | CPU Docling | GPU Docling | Speedup |
|--------------|-------------|-------------|---------|
| Text-heavy PDF (10 pages) | ~15s | ~3s | 5x |
| Scanned PDF with OCR (5 pages) | ~45s | ~5s | 9x |
| DOCX/ODT | ~2s | ~1s | 2x |
| Plain text/CSV/JSON | ~0.5s | ~0.5s | 1x (no change) |
| Image (OCR) | ~10s | ~2s | 5x |

**Estimated onboarding times** (1000 mixed documents, RTX 4090):

| Mode | Time | Notes |
|------|------|-------|
| CPU Docling, concurrency 8 | ~4-6 hours | Old defaults |
| CPU Docling, concurrency 20 | ~2-3 hours | Concurrency improvement only |
| **GPU Docling, concurrency 20** | **~30-60 min** | **Full onboarding mode** |

### Bottleneck Analysis

```
                    CPU Mode                          GPU Mode
              ┌─────────────────┐              ┌─────────────────┐
   Download   │████             │ ~5%          │████             │ ~15%
   Docling    │████████████████ │ ~70%  →      │██████           │ ~25%
   Embedding  │████████         │ ~20%         │████████████     │ ~45%
   Graph      │██               │ ~5%          │████             │ ~15%
              └─────────────────┘              └─────────────────┘
```

In CPU mode, Docling is the clear bottleneck. In GPU mode, the pipeline becomes more balanced with embedding as the new bottleneck.

---

## Files Reference

### Docker Compose

| File | Purpose |
|------|---------|
| `docker-compose.onpremise.yml` | Base on-premise configuration |
| `docker-compose.onboarding.yml` | Onboarding override (Docling GPU + env tweaks) |

### Scripts

| File | Purpose |
|------|---------|
| `onboarding.sh` | CLI for onboarding lifecycle management |
| `start-dev.sh` | Normal development stack startup |

### Indexing Pipeline (MCP Connectors)

| File | Key Features |
|------|-------------|
| `mcp-google-drive-server/app/services/sync_service.py` | OAuth token refresh per-doc, skip unsupported extensions |
| `mcp-onedrive-server/app/services/sync_service.py` | Same pattern as Google Drive |
| `mcp-alfresco-server/app/services/sync_service.py` | Username/password auth (no token expiry) |

### RAG Pipeline (Weaviate Service)

| File | Stages |
|------|--------|
| `weaviate-service/app/services/rag/indexing_pipeline.py` | 8-stage pipeline orchestrator |
| `weaviate-service/app/services/rag/document_intelligence.py` | Quality assessment (no LLM) |
| `weaviate-service/app/services/rag/semantic_chunker.py` | Chunking by semantic boundaries (no LLM) |
| `weaviate-service/app/services/rag/contextual_retrieval.py` | Domain detection + applicable laws (optional LLM) |
| `weaviate-service/app/services/rag/hierarchical_indexer.py` | Document summaries (**requires LLM**) |

### Enrichment Properties

Documents indexed during onboarding include these first-class Weaviate properties for multi-signal retrieval:

| Property | Source | Example |
|----------|--------|---------|
| `semantic_type` | MIME mapping / pipeline inference | `"contract"`, `"invoice"`, `"report"` |
| `quality_score` | Document intelligence (0.0-1.0) | `0.85` |
| `associated_person` | Folder hierarchy heuristic | `"Javier Martinez"` |

These properties enable Emma's SmartSearch to filter results by type, person, and quality without relying on full-text matching.

---

## Troubleshooting

### Docling GPU fails to start

```
Error: could not select device driver "nvidia"
```

Fix: Install nvidia-container-toolkit
```bash
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Services won't start without SGLang

If services fail with "depends on undefined service sglang":
```bash
# Start normally first (SGLang included), then stop it
docker compose -f docker-compose.onpremise.yml up -d
docker compose -f docker-compose.onpremise.yml stop sglang
```

The `onboarding.sh start` command handles this automatically.

### Token expires during long sync

Google Drive OAuth tokens expire after ~1 hour. The MCP connectors now refresh the token **per document** (not per batch), so this should not occur. If you see 401 errors:

```bash
# Reset 401 failures to retry
docker exec docker-db-1 psql -U nexus_user -d nouxcube -c "
  UPDATE indexed_documents
  SET indexing_status = 'pending', indexing_error = NULL
  WHERE indexing_status = 'failed'
    AND indexing_error LIKE '%401%'
"
```

### Docling saturates with heavy PDFs

If many large PDFs cause timeouts:
1. Increase timeout: `DOCLING_SERVE_MAX_SYNC_WAIT=600`
2. Reduce connector concurrency temporarily in sync_service.py
3. Consider splitting the sync into batches by file type

---

## Post-Onboarding Checklist

- [ ] All connectors show acceptable indexed percentage (`./onboarding.sh status`)
- [ ] `./onboarding.sh finish` completed successfully
- [ ] SGLang is healthy (`docker exec docker-sglang-1 curl -sf http://localhost:8000/health`)
- [ ] Emma responds to test queries in the chat UI
- [ ] BOE legislation is searchable (test: "articulo 37 estatuto de trabajadores")
- [ ] Incremental sync scheduler is configured (Celery Beat or cron)
- [ ] Heartbeat system is enabled for proactive insights
- [ ] Backup strategy for PostgreSQL + Weaviate is in place
