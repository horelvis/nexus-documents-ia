# NouxCubeIA - Intelligent Document Management Platform

<div align="center">
  <h3>Enterprise Document Intelligence with Local AI</h3>
  <p><strong>360° AI-Powered Document Management - 100% On-Premise</strong></p>

  ![License](https://img.shields.io/badge/license-MIT-blue.svg)
  ![Python](https://img.shields.io/badge/python-3.9+-green.svg)
  ![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)
  ![vLLM](https://img.shields.io/badge/vLLM-Qwen3-purple.svg)
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
| **Emma AI Assistant** | Intelligent assistant with multi-agent orchestration (Microsoft Agent Framework) |
| **Structural Intelligence Layer (SIL)** | Pre-LLM reasoning with Apache AGE knowledge graphs |
| **Multimodal RAG Pipeline** | 7-layer retrieval with hybrid search, reranking, and validated generation |
| **Cross-Modal Search** | Text queries find images, diagrams, and tables in documents |
| **Legal Knowledge Base** | Spanish BOE legislation indexed for automatic legal context |
| **Enterprise Connectors** | Alfresco, SharePoint, Database (PostgreSQL/MySQL) |

### Why On-Premise?

| Benefit | Description |
|---------|-------------|
| **Data Sovereignty** | All data stays on your infrastructure |
| **No API Costs** | Local GPU inference with vLLM (Qwen3) |
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
│  └─────────────┘     └─────────────┘     │  │  (Agent Framework)  │   │    │
│                             │            │  │                     │   │    │
│                             │            │  │  12 Specialized     │   │    │
│                             ▼            │  │  Agents + RAG       │   │    │
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

### Emma AI: Multi-Agent Orchestration

Emma AI is built on **Microsoft Agent Framework** with **PlanningFlow** orchestration:

| Agent | Domain | Capabilities |
|-------|--------|--------------|
| **SearchAgent** | Document Retrieval | Semantic + hybrid search across all documents |
| **AnalystAgent** | Data Analysis | Financial analysis, metrics extraction |
| **ContractAgent** | Contract Law | Clause analysis, risk detection, Civil Code |
| **ComplianceAgent** | Regulatory | GDPR, LOPDGDD, compliance verification |
| **SummarizerAgent** | Content Synthesis | Executive summaries, key points extraction |
| **LaborAgent** | Employment Law | Workers' Statute, PRL, LISOS analysis |
| **FiscalAgent** | Tax Law | IRPF, VAT, Corporate Tax analysis |
| **PrivacyAgent** | Data Protection | LOPDGDD, GDPR compliance |
| **LegalAgent** | General Legal | Cross-domain legal analysis |

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
- **AI Framework**: Microsoft Agent Framework

### Frontend
- **Framework**: Next.js 15 (App Router)
- **UI**: Shadcn/UI + Tailwind CSS
- **Auth**: OIDC/SAML (KeyCloak, Azure AD)
- **Language**: TypeScript

### AI/ML
- **Inference**: vLLM (GPU)
- **Model**: Qwen3-4B-Thinking (default)
- **Embeddings**: BGE-M3 (multilingual)
- **RAG**: 7-layer pipeline with SIL

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
| [SIL.md](docs/architecture/SIL.md) | Structural Intelligence Layer |
| [EMMA_AI.md](docs/architecture/EMMA_AI.md) | Emma AI agent system |
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
  <p>Powered by vLLM + Microsoft Agent Framework</p>
</div>
