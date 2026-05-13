# NouxCubeIA - Intelligent Document Management Platform

<div align="center">
  <h3>Enterprise Document Intelligence with Local AI</h3>
  <p><strong>360° AI-Powered Document Management - 100% On-Premise</strong></p>

  ![License](https://img.shields.io/badge/license-MIT-blue.svg)
  ![Python](https://img.shields.io/badge/python-3.9+-green.svg)
  ![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)
  ![SGLang](https://img.shields.io/badge/SGLang-Qwen3.5-purple.svg)
</div>

---

## Overview

**NouxCubeIA** is an enterprise-grade document management platform where Artificial Intelligence transforms how organizations interact with their information. Running **100% locally** with GPU inference, it ensures complete data sovereignty while automating document workflows with advanced AI capabilities.

### Deployment Options

| Option | Best For | Guide |
|--------|----------|-------|
| **On-Premise** | Data sovereignty, air-gapped | [README-ONPREMISE.md](README-ONPREMISE.md) |

### Key Features

| Feature | Description |
|---------|-------------|
| **Emma AI Assistant** | Intelligent assistant with LangGraph ReAct agent (16 tools) + Swarm parallel execution |
| **TrustGraph Knowledge Expert** | RDF-style knowledge graph (FalkorDB) with 76-predicate dual-layer ontology (structural in FalkorDB + semantic in Weaviate `OntologyTerms` for fuzzy predicate resolution), authority scoring, and report generation with verified citations |
| **Emma Reactive** | Event-driven proactive AI — triggers, notifications, multi-channel (Telegram, WhatsApp, Slack, Email) |
| **SmartSearch** | Unified multi-store search (Weaviate + TrustGraph knowledge graph + semantic index) |
| **Multimodal RAG Pipeline** | 7-layer retrieval with hybrid search, cross-encoder reranking, and verified generation |
| **Cross-Modal Search** | Text queries find images, diagrams, and tables in documents |
| **Legal Knowledge Base** | Spanish BOE legislation indexed for automatic legal context |
| **Enterprise Connectors** | Alfresco, SharePoint, Database (PostgreSQL/MySQL) |

### Why On-Premise?

| Benefit | Description |
|---------|-------------|
| **Data Sovereignty** | All data stays on your infrastructure |
| **No API Costs** | Local GPU inference with SGLang (Qwen3.5-9B) |
| **Air-Gapped Ready** | Works without internet connectivity |
| **Compliance** | Full control for GDPR, HIPAA, internal policies |
| **Customization** | Complete access to code and models |

---

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/your-org/nexus-documents-ia.git
cd nexus-documents-ia

# 2. Configure environment
cp backend/docker/.env.example backend/docker/.env
# Edit .env with HF_TOKEN and configurations

# 3. Start services
cd backend/docker
docker compose up -d

# 4. Verify
curl http://localhost:8000/health
```

**Complete setup guide with all options: [README-ONPREMISE.md](README-ONPREMISE.md)**

---

## Architecture Overview

NouxCubeIA is a **single-tenant, on-premise** document IA built as a constellation of focused microservices around a **TrustGraph-style knowledge graph** (`:Node`/`:Literal`/`:Rel` triples on FalkorDB) and a **hybrid RAG layer** (Weaviate + intelligence-docs-service). The Emma agent (LangGraph ReAct + Swarm) orchestrates 16 tools that read both stores.

> The KG layer is not an add-on — it is the load-bearing design choice. See [`docs/architecture/README.md`](docs/architecture/README.md) for the *why* (TrustGraph foundation, vector-RAG failure modes the KG addresses, what we kept/changed/replaced from upstream TrustGraph). Per-piece reference docs live next to it.

```
                                                ┌──────────────────────┐
EDGE        ┌──────────────┐    HTTPS / OIDC    │  KeyCloak            │
            │  Frontend    │◄──────────────────►│  Auth + SSO          │
            │  Next.js 16  │                    └──────────────────────┘
            └──────┬───────┘
                   │   (HTTPS via tls-proxy)
                   ▼
API         ┌────────────────────────┐
            │  Main API (FastAPI)    │  internal :8000  →  external :8002
            │  REST + auth + ACL     │
            └──┬───────────┬─────────┘
               │           │
               │           └────────────────────────────────────────┐
               │                                                    │
ORCHESTRATION  │                                                    │
& AI SERVICES  ▼                                                    ▼
       ┌──────────────────────┐         ┌──────────────────────────────┐
       │ emma-agent-service   │         │ weaviate-service             │
       │ :8019 (LangGraph)    │         │ :8007 — RAG indexer +        │
       │  ReAct + Swarm       │◄───────►│  hybrid search + 5-signal    │
       │  16 tools  ─────────────────►   │  re-rank                     │
       │  PostgresSaver+Store │         └──┬──────────────────────────┘
       └──┬──────────────┬─────┘            │
          │              │                  │ /extract/triples
          │              │                  ▼
          │              │       ┌──────────────────────┐    ┌────────────────────┐
          │              ├──────►│ knowledge-tree-svc   │    │ intelligence-docs  │
          │              │       │ :8011 (TrustGraph)   │    │ :8012 — Tika +     │
          │              │       │  4 LLM extractors    │    │ Docling + BGE-M3   │
          │              │       │  + EntityResolver    │    │ + LangExtract NER  │
          │              │       └──────────────────────┘    └────┬───────────────┘
          │              │                                        │
          │              │       ┌──────────────────────┐         │
          │              ├──────►│ document-forge       │         │
          │              │       │ :8013 — PDF/DOCX gen │         │
          │              │       └──────────────────────┘         │
          │              │                                        │
          │              │       ┌──────────────────────┐         │
          │              └──────►│ storage-service      │◄────────┘
          │                      │ :8010 — MinIO API    │
          │                      └──────────────────────┘
          │
          │   ┌────────────────────────┐    ┌─────────────────────────┐
          └──►│ background-worker      │    │ emma-reactive-worker    │
              │ Celery (async tasks)   │    │ Redis Streams consumer  │
              └────────────────────────┘    └─────────────────────────┘

INFERENCE        ┌────────────────────────────────────────────────────────┐
                 │  SGLang  (Qwen3.5-9B, single GPU, dual PLANNER/CHAT)   │
                 │  ↑ called by emma-agent, knowledge-tree, intel-docs    │
                 └────────────────────────────────────────────────────────┘
                 ┌─────────────────┐    ┌─────────────────┐
                 │ Docling (CPU)   │    │ Tika            │
                 │ OCR + chunking  │    │ text extraction │
                 └─────────────────┘    └─────────────────┘

DATA LAYER  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
            │PostgreSQL│  │ Weaviate │  │ FalkorDB │  │  MinIO   │  │  Redis   │
            │  main DB │  │ (vector) │  │ (graph,  │  │  blob    │  │ cache +  │
            │ users/   │  │ HNSW+BM25│  │ TrustGraph│ │ nexus-   │  │ Streams +│
            │ docs/etc │  │ 6 collec │  │ triples) │  │ storage  │  │ Celery   │
            └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

**Service legend** — every service has a port, an owner, and a single responsibility. Full table + inter-service contracts in [`docs/architecture/MODULAR_ARCHITECTURE.md`](docs/architecture/MODULAR_ARCHITECTURE.md).

| Service | Port | Responsibility |
|---------|------|----------------|
| `frontend` | 3001 (HTTPS) | Next.js 16 UI, OIDC + SSO via KeyCloak |
| `keycloak` | 8081 | OIDC/SAML auth provider |
| `api` (main) | 8000 internal / 8002 external | REST API, document CRUD, admin (`is_superuser` gate) |
| `emma-agent-service` | 8019 / 8009 internal | LangGraph ReAct + Swarm + 16 tools + sub-graphs |
| `weaviate-service` | 8007 | RAG indexing pipeline + hybrid search + 5-signal re-rank |
| `knowledge-tree-service` | 8011 | TrustGraph triple store, 4 LLM extractors, EntityResolver |
| `intelligence-docs-service` | 8012 | Text extraction (Tika/Docling), embeddings (BGE-M3), NER (LangExtract) |
| `storage-service` | 8010 (internal) | MinIO abstraction, file fetch + cache |
| `document-forge` | 8013 | PDF/DOCX generation (`forge_document` tool) |
| `background-worker` | — | Celery async tasks (heartbeat, reactive, embeddings refresh) |
| `emma-reactive-worker` | — | Redis Streams consumer + trigger engine |
| `sglang` | internal | Qwen3.5-9B inference, dual-phase PLANNER/CHAT |
| `docling` | 5001 (profile) | CPU OCR + page-aware chunking (gated behind `--profile docling`) |
| `tika` | 9998 | Text extraction fallback |
| `weaviate` | 8080 internal | Native vector DB, 6 collections |
| `falkordb` | 6380 | Graph DB (Redis-based), `knowledge_graph` graph |
| `postgres` | 5432 | Main DB (vanilla `postgres:15`) |
| `minio` | 9000/9001 | S3-compatible blob storage, bucket `nexus-storage` |
| `redis` | 6379 | Cache + event bus (Streams) + Celery broker |

### Emma AI: LangGraph ReAct Agent

Emma is a LangGraph ReAct agent (8 nodes) plus a Swarm path for parallel decomposition. **All 16 tools** the agent can invoke:

| # | Tool | Purpose |
|---|------|---------|
| 1 | `smart_search` | Unified hybrid search (Weaviate + graph expansion via TrustGraph) |
| 2 | `graph_rag` | 8-stage TrustGraph retrieval (entity → BFS → guided expansion → 5-signal scoring → provenance) |
| 3 | `get_document_content` | Read full document by ID |
| 4 | `structural_query` | Count, list, filter via FalkorDB TrustGraph |
| 5 | `invoke_agent` | Delegate to a specialist from the admin-curated agents catalog (replaces legacy `analyze_domain`) |
| 6 | `web_search` | Internet search (Tavily primary, DuckDuckGo fallback) |
| 7 | `search_jurisprudence` | CENDOJ jurisprudence search |
| 8 | `list_sources` | Discover available data sources |
| 9 | `query_connector` | Query external connectors (SharePoint, etc.) |
| 10 | `generate_document` | Generate document from template |
| 11 | `forge_document` | Create PDF/DOCX documents (`document-forge` service) |
| 12 | `send_email` | Send email notifications |
| 13 | `verified_generation` | Claim-by-claim verification sub-graph (SSE streamed) |
| 14 | `predictive_analysis` | Predictive analysis sub-graph |
| 15 | `generate_knowledge_report` | Structured report with KPIs + verified citations from KG |
| 16 | `terminate` | Signal completion with response |

**Persistence (LangGraph Level 3)**: `AsyncPostgresSaver` checkpointer (per-thread conversation continuity) + `AsyncPostgresStore` (cross-thread user memory: identity, work, preferences). Both share a single `psycopg3` async connection pool.

### Emma Reactive: Event-Driven Proactive AI

Emma Reactive transforms Emma from a request-response chatbot into a **proactive, event-driven, multi-channel assistant**:

```
┌──────────────────────────────────────────────────────────┐
│              EVENT BUS (Redis Streams)                     │
│  document.indexed | connector.synced | knowledge.updated  │
└────────┬──────────────┬──────────────┬───────────────────┘
         │              │              │
   ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼──────┐
   │ Event     │ │ Celery    │ │ Channel    │
   │ Listener  │ │ Beat      │ │ Router     │
   └─────┬─────┘ └─────┬─────┘ └─────┬──────┘
         │              │              │
   ┌─────▼──────────────▼──────────────▼──────┐
   │           Trigger Engine                  │
   │  (evaluate rules → dispatch actions)      │
   └─────┬────────────────────────────────────┘
         │
   ┌─────▼──────────────────────────────────┐
   │  Emma Background Service               │
   │  (LangGraph proactive execution)       │
   └─────┬──────────────────────────────────┘
         │
   ┌─────▼───┬────────┬────────┬──────────┐
   │WhatsApp │Telegram│ Slack  │ WebSocket│
   └─────────┴────────┴────────┴──────────┘
```

| Component | Description |
|-----------|-------------|
| **Event Bus** | Redis Streams for inter-service events (document.indexed, connector.synced, etc.) |
| **Trigger Engine** | Configurable rules per tenant — match events to actions (analyze, notify, workflow) |
| **Notifications** | In-app (WebSocket push), email, webhook |
| **Multi-Channel** | Telegram Bot, WhatsApp (Twilio), Slack, Email — with user pairing |
| **Background Service** | Proactive LangGraph execution (daily summaries, document analysis) |

> **Full docs**: [docs/architecture/EMMA_REACTIVE.md](docs/architecture/EMMA_REACTIVE.md)

### Multi-Channel Webhooks with ngrok

For external messaging channels (Slack, Telegram, WhatsApp) to send messages to Emma, you need a public URL. The stack includes an optional **ngrok** service for development/testing:

```bash
# 1. Get your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
# 2. Add to backend/docker/.env:
NGROK_AUTHTOKEN=your_token_here

# 3. Start ngrok alongside your services:
cd backend/docker
docker compose --profile webhooks up ngrok -d

# 4. Get your public URL:
docker compose logs ngrok | grep "url="
# → https://abc123.ngrok-free.app

# 5. Configure in your channel provider:
# - Slack: Event Subscriptions → Request URL: https://abc123.ngrok-free.app/channels/webhooks/slack
# - Telegram: setWebhook API → https://abc123.ngrok-free.app/channels/webhooks/telegram
# - WhatsApp (Twilio): Webhook URL → https://abc123.ngrok-free.app/channels/webhooks/whatsapp
```

**ngrok Web UI**: Visit `http://localhost:4040` to inspect incoming webhook requests in real-time.

> **Note**: ngrok is under the `webhooks` profile — it won't start with regular `docker compose up`. This avoids consuming tunnel bandwidth during normal development.

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | RTX 3090 (24GB) | RTX 4090 (24GB) |
| **CPU** | 8 cores | 16+ cores |
| **RAM** | 32GB | 64GB |
| **Storage** | 100GB SSD | 500GB NVMe |

---

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.9+) with async/await
- **Database**: PostgreSQL 15
- **Graph DB**: FalkorDB (TrustGraph knowledge graph on Redis)
- **Vector DB**: Weaviate
- **Cache**: Redis
- **AI Framework**: LangGraph (ReAct agent + PostgresSaver + AsyncPostgresStore)

### Frontend
- **Framework**: Next.js 16 (App Router)
- **UI**: Shadcn/UI + Tailwind CSS
- **Auth**: OIDC/SAML (KeyCloak, Azure AD)
- **Language**: TypeScript

### AI/ML
- **Inference**: SGLang (GPU) serving Qwen3.5-9B
- **Model role split**: Dual-phase PLANNER (temp=0.3, tool calls) / CHAT (temp=0.6, generation)
- **Embeddings**: BGE-M3 (multilingual, 1024d, via intelligence-docs-service)
- **OCR**: Docling CPU + Tika fallback
- **RAG**: Hybrid Weaviate (BM25 + dense) + TrustGraph graph expansion + 5-signal re-rank (heuristic; optional cross-encoder)
- **KG**: TrustGraph model on FalkorDB, 4 LLM extractors per chunk, PROV-O provenance, contradiction detection, EntityResolver (heuristic + LLM clustering)

---

## Documentation

| Document | Description |
|----------|-------------|
| [README-ONPREMISE.md](README-ONPREMISE.md) | **Complete on-premise deployment guide** |
| [CLAUDE.md](CLAUDE.md) | Development guidelines for Claude Code |
| [docs/architecture/](docs/architecture/) | System architecture documentation |
| [docs/on-premise/](docs/on-premise/) | On-premise specific guides |

### Architecture Documentation

Start here if you are new: [`docs/architecture/README.md`](docs/architecture/README.md) — conceptual primer covering why a KG, what TrustGraph defines, what we kept/changed/replaced, and what the KG brings to RAG. All the reference docs below sit underneath it.

| Document | Description |
|----------|-------------|
| [README.md](docs/architecture/README.md) | **Start here.** KG primer + folder index + TrustGraph foundation + 3 concrete RAG scenarios |
| [MODULAR_ARCHITECTURE.md](docs/architecture/MODULAR_ARCHITECTURE.md) | Service topology, ports, inter-service contracts, persistence layout |
| [TRUSTGRAPH.md](docs/architecture/TRUSTGRAPH.md) | KG schema, FalkorDB indexes, 4 extractors, ontology, reindex script |
| [RAG_PIPELINE.md](docs/architecture/RAG_PIPELINE.md) | Indexing pipeline + 8-stage `graph_rag` + `smart_search` re-ranking + caching |
| [EMMA_AI.md](docs/architecture/EMMA_AI.md) | LangGraph agent topology, ReAct loop, Swarm, sub-graphs |
| [EMMA_REACTIVE.md](docs/architecture/EMMA_REACTIVE.md) | Event bus, triggers, channels (Slack/Telegram/WhatsApp), heartbeat |
| [USER_MEMORY.md](docs/architecture/USER_MEMORY.md) | Cross-thread persistent user facts (LangGraph Store) |
| [PROMPT_MANAGEMENT.md](docs/architecture/PROMPT_MANAGEMENT.md) | Langfuse as single source of truth for prompts, rules, guardrails |
| [AGENTS.md](docs/architecture/AGENTS.md) | Admin-curated specialist agents (`@slug` mention flow) |
| [ACL_SYSTEM.md](docs/architecture/ACL_SYSTEM.md) | Single-tenant authorisation (`is_superuser` only, role-based ACL removed 2026-05) |

---

## Security

- **Authentication**: OIDC/SAML with KeyCloak, Azure AD, Okta
- **Encryption**: At rest and in transit
- **Audit**: Comprehensive logging of all operations
- **Authorization**: All authenticated users read every document. Admin endpoints gate on `User.is_superuser` via `Depends(require_superuser)`. Per-document role-based ACL was removed 2026-05-08 (see [ACL_SYSTEM.md](docs/architecture/ACL_SYSTEM.md))
- **Air-Gapped**: Works without internet connectivity

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">
  <h3>NouxCubeIA - Enterprise Document Intelligence with Local AI</h3>
  <p>Powered by SGLang (Qwen3.5) + LangGraph</p>
</div>
