# NouxCubeIA - Intelligent Document Management Platform

<div align="center">
  <h3>Where AI Transforms Documents into Decisions</h3>
  <p><strong>360° AI-Powered Document Intelligence</strong></p>

  ![License](https://img.shields.io/badge/license-MIT-blue.svg)
  ![Python](https://img.shields.io/badge/python-3.9+-green.svg)
  ![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)
  ![vLLM](https://img.shields.io/badge/vLLM-Qwen3-purple.svg)
</div>

---

## Overview

**NouxCubeIA** is the next generation of enterprise document management, where Artificial Intelligence is not just a feature, but the core that radically transforms how organizations interact with their information. Our platform uses advanced AI to automate 80% of document tasks, allowing teams to focus on strategic decisions while AI handles operational complexity.

### Key Features

| Feature | Description |
|---------|-------------|
| **Emma AI Assistant** | Intelligent assistant with multi-agent orchestration (Microsoft Agent Framework) |
| **Multimodal RAG Pipeline** | 7-layer retrieval with hybrid search, reranking, and validated generation |
| **Cross-Modal Search** | Text queries find images, diagrams, and tables in documents |
| **Legal Knowledge Base** | Spanish BOE legislation indexed for automatic legal context |
| **Entity Extraction** | Automatic identification of people, organizations, dates, amounts |
| **Digital Signatures** | Integration with DocuSign, YouSign, Signaturit |

### Supported LLM Providers

| Provider | Models | Usage |
|----------|--------|-------|
| **vLLM** (Primary) | Qwen3-4B-Thinking, Qwen3-14B | GPU inference (On-Premise) |
| **OpenAI** | GPT-4o, GPT-4o-mini | API (SaaS/Fallback) |
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Opus | API (SaaS/Fallback) |
| **Google** | Gemini 2.0 Flash, Gemini 1.5 Pro | API (SaaS/Fallback) |
| **OpenRouter** | Multi-provider routing | API (SaaS) |

---

## Deployment Options

NouxCubeIA offers two deployment models to fit your organization's needs:

### SaaS vs On-Premise Comparison

| Aspect | SaaS (Cloud) | On-Premise |
|--------|--------------|------------|
| **Infrastructure** | Managed by us | Self-hosted |
| **GPU Required** | No | Yes (RTX 3090/4090+) |
| **LLM Provider** | API-based (OpenAI, Anthropic, Google) | Local vLLM (Qwen3) |
| **Data Residency** | Cloud (GCP) | Your servers |
| **Scaling** | Automatic | Manual |
| **Maintenance** | Zero | Your team |
| **Cost Model** | Subscription (€29-299/mo) | Infrastructure + License |
| **Setup Time** | Minutes | Hours |
| **Best For** | SMBs, Quick start | Enterprise, Data sovereignty |

### Choose Your Deployment

| Deployment | Documentation | Description |
|------------|---------------|-------------|
| **SaaS (Cloud)** | [README-SAAS.md](README-SAAS.md) | Multi-tenant cloud with Clerk auth, Stripe payments |
| **On-Premise** | [README-ONPREMISE.md](README-ONPREMISE.md) | Self-hosted with local GPU inference |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NouxCubeIA Architecture                          │
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
│  │  │PostgreSQL│ │ Weaviate │ │Redis │ │ │  │  LLM Provider       │   │    │
│  │  │   +AGE   │ │ (Vector) │ │      │ │ │  │  vLLM / OpenAI /    │   │    │
│  │  └──────────┘ └──────────┘ └──────┘ │ │  │  Anthropic / Google │   │    │
│  └─────────────────────────────────────┘ │  └─────────────────────┘   │    │
│                                          └────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Emma AI: Multi-Agent Orchestration

Emma AI is built on **Microsoft Agent Framework** with **PlanningFlow** (OpenManus-style) orchestration:

```
┌─────────────────────────────────────────────────────────────────┐
│                    EMMA AI ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Query ──▶ PlanningFlow ──▶ Dynamic Plan Generation        │
│                      │                                           │
│         ┌───────────┴───────────┐                               │
│         ▼                       ▼                               │
│  ┌─────────────┐         ┌─────────────┐                        │
│  │   Search    │         │   Analyst   │                        │
│  │   Agent     │         │   Agent     │                        │
│  └─────────────┘         └─────────────┘                        │
│         │                       │                               │
│  ┌──────┴───────────────────────┴──────┐                        │
│  │         Specialized Agents          │                        │
│  │  ┌─────────┐ ┌─────────┐ ┌────────┐ │                        │
│  │  │Contract │ │ Labor   │ │ Fiscal │ │                        │
│  │  │ Agent   │ │ Agent   │ │ Agent  │ │                        │
│  │  └─────────┘ └─────────┘ └────────┘ │                        │
│  │  ┌─────────┐ ┌─────────┐ ┌────────┐ │                        │
│  │  │Privacy  │ │Education│ │ Legal  │ │                        │
│  │  │ Agent   │ │ Agent   │ │ Agent  │ │                        │
│  │  └─────────┘ └─────────┘ └────────┘ │                        │
│  └─────────────────────────────────────┘                        │
│                      │                                           │
│                      ▼                                           │
│           ┌─────────────────────┐                               │
│           │  RAG Pipeline       │                               │
│           │  (7-Layer Hybrid)   │                               │
│           │  + BOE Knowledge    │                               │
│           └─────────────────────┘                               │
│                      │                                           │
│                      ▼                                           │
│              Response with Legal Citations                       │
└─────────────────────────────────────────────────────────────────┘
```

### 12 Specialized Agents

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
| **RealEstateAgent** | Property Law | Lease analysis, property documentation |
| **EducationAgent** | Education Law | LOMLOE, LOE, LOU compliance |
| **LegalAgent** | General Legal | Cross-domain legal analysis |
| **TaxDeclarationAgent** | Tax Forms | Form analysis, deduction identification |

---

## Quick Start

### Option 1: SaaS (Recommended for Quick Start)

```bash
# Sign up at https://app.nouxcubeia.com
# No installation required - start in minutes
```

See [README-SAAS.md](README-SAAS.md) for details.

### Option 2: On-Premise (For Data Sovereignty)

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

See [README-ONPREMISE.md](README-ONPREMISE.md) for complete setup.

---

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.9+) with async/await
- **Database**: PostgreSQL 15 + Apache AGE (Graph)
- **Vector DB**: Weaviate
- **Cache**: Redis
- **Task Queue**: Celery
- **AI Framework**: Microsoft Agent Framework

### Frontend
- **Framework**: Next.js 15 (App Router)
- **UI**: Shadcn/UI + Tailwind CSS
- **Auth**: Clerk
- **Language**: TypeScript

### AI/ML
- **Inference**: vLLM (GPU) / Cloud APIs
- **Models**: Qwen3-4B-Thinking, GPT-4o, Claude 3.5
- **Embeddings**: Qwen3-VL-Embedding-2B (Multimodal)
- **RAG**: 7-layer pipeline with hybrid search

---

## Documentation

| Document | Description |
|----------|-------------|
| [README-SAAS.md](README-SAAS.md) | SaaS deployment guide |
| [README-ONPREMISE.md](README-ONPREMISE.md) | On-premise deployment guide |
| [CLAUDE.md](CLAUDE.md) | Development guidelines for Claude Code |
| [LANGEXTRACT_INTEGRATION.md](LANGEXTRACT_INTEGRATION.md) | Entity extraction guide |
| [EMMA_ARCHITECTURE.md](EMMA_ARCHITECTURE.md) | Emma AI technical architecture |

---

## Security

- **Authentication**: Multi-factor with Clerk / KeyCloak SSO
- **Multi-Tenant**: Complete data isolation per tenant
- **Encryption**: At rest and in transit
- **Audit**: Comprehensive logging of all operations
- **RBAC**: Fine-grained role-based access control
- **Compliance**: GDPR/HIPAA ready

---

## License

This project is licensed under the [MIT License](LICENSE).

## Support

- Documentation: [docs.nouxcubeia.com](https://docs.nouxcubeia.com)
- Issues: [GitHub Issues](https://github.com/your-org/nouxcubeia/issues)
- Email: support@nouxcubeia.com

---

<div align="center">
  <h3>NouxCubeIA - Where AI Transforms Every Document into Competitive Advantage</h3>
  <p>Powered by vLLM + Microsoft Agent Framework | Made with AI by the NouxCubeIA Team</p>
</div>
