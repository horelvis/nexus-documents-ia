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
| **SaaS** | Fast start, no infrastructure | [README-SAAS.md](README-SAAS.md) |
| **On-Premise** | Data sovereignty, air-gapped | [README-ONPREMISE.md](README-ONPREMISE.md) |

### Key Features

| Feature | Description |
|---------|-------------|
| **Emma AI Assistant** | Intelligent assistant with LangGraph ReAct agent + Swarm parallel execution |
| **Emma Reactive** | Event-driven proactive AI — triggers, notifications, multi-channel (Telegram, WhatsApp, Slack, Email) |
| **SmartSearch** | Unified multi-store search (Weaviate + BOE legislation + knowledge graph) |
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

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NouxCubeIA Architecture                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────┐    │
│  │   Frontend  │     │  API Gateway│     │     AI Services             │    │
│  │  Next.js 15 │────▶│   FastAPI   │────▶│  ┌─────────────────────┐   │    │
│  │  Shadcn/UI  │     │   :8000     │     │  │    Emma AI          │   │    │
│  └─────────────┘     └─────────────┘     │  │  (LangGraph ReAct)   │   │    │
│                             │            │  │                     │   │    │
│                             │            │  │  9 Tools + Swarm    │   │    │
│                             ▼            │  │  + PostgresSaver    │   │    │
│  ┌─────────────────────────────────────┐ │  └─────────────────────┘   │    │
│  │         Data Layer                   │ │                           │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────┐ │ │  ┌─────────────────────┐   │    │
│  │  │PostgreSQL│ │ Weaviate │ │Redis │ │ │  │  vLLM Server        │   │    │
│  │  │   +AGE   │ │ (Vector) │ │      │ │ │  │  Qwen3-4B (GPU)     │   │    │
│  │  └──────────┘ └──────────┘ └──────┘ │ │  └─────────────────────┘   │    │
│  └─────────────────────────────────────┘ │                            │    │
│                                          └────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Emma AI: LangGraph ReAct Agent

Emma AI is built on **LangGraph** with a ReAct agent (8 nodes) + optional Swarm parallel execution:

| Tool | Purpose |
|------|---------|
| `smart_search` | Unified search across tenant documents, BOE legislation, and knowledge graph |
| `structural_query` | Count, list, filter via Apache AGE graph |
| `analyze_domain` | Specialist domain analysis (legal, fiscal, labor, medical) |
| `get_document_content` | Read full document content by ID |
| `web_search` | Internet search (DuckDuckGo) |
| `search_jurisprudence` | CENDOJ jurisprudence search |
| `query_connector` | Query external connectors (SharePoint, OneDrive, etc.) |

**Persistence**: PostgresSaver checkpointer (conversation continuity) + AsyncPostgresStore (cross-session user memory)

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
- **Database**: PostgreSQL 15 + Apache AGE (Graph)
- **Vector DB**: Weaviate
- **Cache**: Redis
- **AI Framework**: LangGraph (ReAct agent + PostgresSaver + AsyncPostgresStore)

### Frontend
- **Framework**: Next.js 15 (App Router)
- **UI**: Shadcn/UI + Tailwind CSS
- **Auth**: OIDC/SAML (KeyCloak, Azure AD)
- **Language**: TypeScript

### AI/ML
- **Inference**: SGLang (GPU)
- **Model**: Qwen3.5-9B BF16 (default, single-model dual-phase)
- **Embeddings**: BGE-M3 (multilingual, 1024d)
- **RAG**: SmartSearch unified pipeline with cross-encoder reranking

---

## Documentation

| Document | Description |
|----------|-------------|
| [README-SAAS.md](README-SAAS.md) | **Cloud-hosted SaaS deployment guide** |
| [README-ONPREMISE.md](README-ONPREMISE.md) | **Complete on-premise deployment guide** |
| [CLAUDE.md](CLAUDE.md) | Development guidelines for Claude Code |
| [docs/architecture/](docs/architecture/) | System architecture documentation |
| [docs/on-premise/](docs/on-premise/) | On-premise specific guides |

### Architecture Documentation

| Document | Description |
|----------|-------------|
| [MODULAR_ARCHITECTURE.md](docs/architecture/MODULAR_ARCHITECTURE.md) | SaaS vs On-Premise modular design |
| [USER_MEMORY.md](docs/architecture/USER_MEMORY.md) | Cross-session user memory (AsyncPostgresStore) |
| [EMMA_AI.md](docs/architecture/EMMA_AI.md) | Emma AI agent system |
| [EMMA_REACTIVE.md](docs/architecture/EMMA_REACTIVE.md) | Emma Reactive event-driven system |
| [BOE_LEGAL_KNOWLEDGE.md](docs/architecture/BOE_LEGAL_KNOWLEDGE.md) | Spanish Legal Knowledge Base (BOE) |
| [ACL_SYSTEM.md](docs/architecture/ACL_SYSTEM.md) | Access Control architecture |
| [RAG_PIPELINE.md](docs/architecture/RAG_PIPELINE.md) | RAG implementation blueprint |

---

## Security

- **Authentication**: OIDC/SAML with KeyCloak, Azure AD, Okta
- **Multi-Tenant**: Complete data isolation per tenant
- **Encryption**: At rest and in transit
- **Audit**: Comprehensive logging of all operations
- **RBAC**: Fine-grained role-based access control with JSONB ACL
- **Air-Gapped**: Works without internet connectivity

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">
  <h3>NouxCubeIA - Enterprise Document Intelligence with Local AI</h3>
  <p>Powered by SGLang (Qwen3.5) + LangGraph</p>
</div>
