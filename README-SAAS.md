# NexusDocs360 SaaS - Cloud Deployment

<div align="center">
  <h3>Managed Multi-Tenant Cloud Platform</h3>
  <p><strong>Zero infrastructure, instant start, automatic scaling</strong></p>
</div>

---

## Overview

NexusDocs360 SaaS is our fully managed cloud offering, designed for organizations that want to focus on their documents, not infrastructure. With multi-tenant architecture, integrated authentication via Clerk, and payments via Stripe, you can start using Emma AI in minutes.

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Zero Infrastructure** | No servers to manage, no GPUs to configure |
| **Instant Start** | Sign up and start uploading documents immediately |
| **Automatic Scaling** | Scales with your usage, no capacity planning |
| **Always Updated** | Latest features and security patches automatically |
| **99.9% SLA** | Enterprise-grade availability (Pro/Enterprise plans) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NexusDocs360 SaaS Architecture                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        Cloud Run / GKE                               │    │
│  │  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────────┐    │    │
│  │  │ API Gateway │  │ Weaviate Service│  │  Background Workers  │    │    │
│  │  │  (FastAPI)  │  │  (RAG + Emma)   │  │     (Celery)         │    │    │
│  │  │   :8000     │  │     :8007       │  │                      │    │    │
│  │  └──────┬──────┘  └────────┬────────┘  └──────────────────────┘    │    │
│  │         │                  │                                        │    │
│  └─────────┼──────────────────┼────────────────────────────────────────┘    │
│            │                  │                                              │
│  ┌─────────┼──────────────────┼────────────────────────────────────────┐    │
│  │         │    Managed Services                                        │    │
│  │         ▼                  ▼                                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │    │
│  │  │ Cloud SQL   │  │ Weaviate    │  │ Memorystore │  │    GCS     │  │    │
│  │  │ PostgreSQL  │  │   Cloud     │  │   (Redis)   │  │  Storage   │  │    │
│  │  │   + AGE     │  │             │  │             │  │            │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      LLM Providers (API-based)                       │    │
│  │                                                                      │    │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌─────────────┐        │    │
│  │  │  OpenAI  │  │ Anthropic │  │  Google  │  │ OpenRouter  │        │    │
│  │  │ GPT-4o   │  │ Claude 3.5│  │ Gemini   │  │ Multi-model │        │    │
│  │  └──────────┘  └───────────┘  └──────────┘  └─────────────┘        │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      External Integrations                           │    │
│  │                                                                      │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐        │    │
│  │  │  Clerk   │  │  Stripe  │  │ KeyCloak │  │  Signature   │        │    │
│  │  │  Auth    │  │ Payments │  │   SSO    │  │  Providers   │        │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘        │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Pricing Plans

| Feature | Trial | Basic | Pro | Enterprise |
|---------|-------|-------|-----|------------|
| **Price** | Free | €29/mo | €99/mo | Custom |
| **Documents** | 50 | 500 | 5,000 | Unlimited |
| **Storage** | 1 GB | 10 GB | 100 GB | Unlimited |
| **Emma AI Queries** | 100/mo | 1,000/mo | 10,000/mo | Unlimited |
| **Users** | 1 | 5 | 25 | Unlimited |
| **LLM Provider** | GPT-4o-mini | GPT-4o-mini | GPT-4o | Custom |
| **Entity Extraction** | Basic | Full | Full | Full |
| **Legal KB (BOE)** | - | - | Yes | Yes |
| **SSO (KeyCloak)** | - | - | - | Yes |
| **API Access** | - | Limited | Full | Full |
| **SLA** | - | - | 99.9% | 99.99% |
| **Support** | Community | Email | Priority | Dedicated |
| **Data Retention** | 30 days | 1 year | 3 years | Custom |

### Trial Plan Details

- **Duration**: 14 days
- **No credit card required**
- **Full Emma AI access** (limited queries)
- **Automatic downgrade** to free tier after trial

---

## Authentication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTHENTICATION FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SIGN UP (New Users)                                      │   │
│  │                                                           │   │
│  │  1. User clicks "Sign Up"                                 │   │
│  │  2. Clerk creates user account                            │   │
│  │  3. Webhook fires → Backend creates:                      │   │
│  │     • Tenant (organization)                               │   │
│  │     • GCS bucket                                          │   │
│  │     • Trial subscription                                  │   │
│  │  4. User redirected to onboarding                         │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  LOGIN (Existing Users)                                   │   │
│  │                                                           │   │
│  │  1. User enters credentials                               │   │
│  │  2. Clerk authenticates → JWT token                       │   │
│  │  3. Frontend calls POST /api/v1/auth/login                │   │
│  │  4. Backend validates JWT + queries Stripe                │   │
│  │  5. Returns: user + subscription + permissions            │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SSO (Enterprise Only - KeyCloak)                         │   │
│  │                                                           │   │
│  │  1. User selects "SSO Login"                              │   │
│  │  2. Redirect to organization's KeyCloak                   │   │
│  │  3. SAML/OIDC authentication                              │   │
│  │  4. Token exchange with backend                           │   │
│  │  5. User provisioned/updated automatically                │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## LLM Provider Configuration

SaaS uses API-based LLM providers. You can configure your preferred provider per tenant:

### Default Configuration by Plan

| Plan | Default Provider | Model | Fallback |
|------|------------------|-------|----------|
| Trial | OpenAI | gpt-4o-mini | - |
| Basic | OpenAI | gpt-4o-mini | - |
| Pro | OpenAI | gpt-4o | gpt-4o-mini |
| Enterprise | Custom | Any | Multi-provider |

### Supported Providers

```
┌─────────────────────────────────────────────────────────────────┐
│                     LLM PROVIDER OPTIONS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐                                                 │
│  │   OpenAI    │  gpt-4o, gpt-4o-mini, gpt-4-turbo              │
│  │  (Default)  │  Best for: General purpose, fast responses     │
│  └─────────────┘                                                 │
│                                                                  │
│  ┌─────────────┐                                                 │
│  │  Anthropic  │  claude-3-5-sonnet, claude-3-opus              │
│  │             │  Best for: Complex analysis, long documents    │
│  └─────────────┘                                                 │
│                                                                  │
│  ┌─────────────┐                                                 │
│  │   Google    │  gemini-2.0-flash, gemini-1.5-pro              │
│  │             │  Best for: Multimodal, cost-effective          │
│  └─────────────┘                                                 │
│                                                                  │
│  ┌─────────────┐                                                 │
│  │ OpenRouter  │  Any model via unified API                     │
│  │             │  Best for: Model flexibility, A/B testing      │
│  └─────────────┘                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Bring Your Own API Key (Enterprise)

Enterprise customers can use their own API keys:

```bash
# In tenant settings
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o

# Or use multiple providers
LLM_PROVIDERS=openai,anthropic
ANTHROPIC_API_KEY=sk-ant-your-key
```

---

## Quick Start

### 1. Sign Up

```
1. Go to https://app.nexusdocs360.com
2. Click "Start Free Trial"
3. Create account with email or Google/Microsoft SSO
4. Complete onboarding wizard
```

### 2. Upload Your First Document

```
1. Click "Upload" in the dashboard
2. Drag & drop your document (PDF, DOCX, etc.)
3. Wait for AI processing (entity extraction, embeddings)
4. Document is now searchable and analyzable
```

### 3. Ask Emma AI

```
1. Click on Emma AI chat
2. Ask questions about your documents:
   - "What are the key terms in contract #123?"
   - "Find all invoices from Q4 2024"
   - "Summarize the compliance report"
3. Emma responds with citations and legal references
```

---

## API Access

### Authentication

```bash
# Get your API key from Settings > API Keys
export NEXUSDOCS_API_KEY="your-api-key"

# All requests require Bearer token
curl -H "Authorization: Bearer $NEXUSDOCS_API_KEY" \
  https://api.nexusdocs360.com/api/v1/documents
```

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/documents` | GET | List documents |
| `/api/v1/documents` | POST | Upload document |
| `/api/v1/documents/{id}` | GET | Get document details |
| `/api/v1/search` | POST | Semantic search |
| `/api/v1/search/ask` | POST | Ask Emma AI |
| `/api/v1/entities/{doc_id}` | GET | Get extracted entities |

### Example: Search Documents

```bash
curl -X POST https://api.nexusdocs360.com/api/v1/search \
  -H "Authorization: Bearer $NEXUSDOCS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "contract renewal terms",
    "limit": 10,
    "include_entities": true
  }'
```

### Example: Ask Emma AI

```bash
curl -X POST https://api.nexusdocs360.com/api/v1/search/ask \
  -H "Authorization: Bearer $NEXUSDOCS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the payment terms in the service agreement?",
    "document_ids": ["doc-123", "doc-456"]
  }'
```

---

## Integrations

### Clerk (Authentication)

Clerk handles all authentication:
- Email/password
- Social login (Google, Microsoft, GitHub)
- Multi-factor authentication
- Session management

### Stripe (Payments)

Stripe manages subscriptions:
- Automatic billing
- Plan upgrades/downgrades
- Usage-based billing (Enterprise)
- Invoice generation

### KeyCloak (SSO - Enterprise)

For enterprise SSO:
- SAML 2.0
- OIDC
- Active Directory integration
- Custom identity providers

### Signature Providers

Digital signature integrations:
- DocuSign
- YouSign
- Signaturit

---

## Deployment for Self-Managed SaaS

If you want to run NexusDocs360 SaaS on your own GCP infrastructure:

### Prerequisites

- GCP Project with billing enabled
- gcloud CLI configured
- Docker installed
- Clerk account (for auth)
- Stripe account (for payments)
- LLM API keys (OpenAI, Anthropic, etc.)

### Environment Variables

```bash
# Authentication
CLERK_SECRET_KEY=sk_live_xxx
CLERK_WEBHOOK_SECRET=whsec_xxx
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_xxx

# Payments
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_BASIC=price_xxx
STRIPE_PRICE_PRO=price_xxx

# LLM Providers
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
GOOGLE_API_KEY=xxx

# Database
DATABASE_URL=postgresql://user:pass@host:5432/nexusdocs

# Storage
GCS_BUCKET_PREFIX=nexusdocs-
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

# Services
WEAVIATE_URL=http://weaviate:8080
REDIS_URL=redis://redis:6379
```

### GCP Deployment

```bash
# 1. Set up GCP project
gcloud config set project your-project-id

# 2. Enable required APIs
gcloud services enable \
  cloudsql.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  redis.googleapis.com

# 3. Create Cloud SQL instance
gcloud sql instances create nexusdocs-db \
  --database-version=POSTGRES_15 \
  --tier=db-standard-2 \
  --region=europe-west1

# 4. Create Redis (Memorystore)
gcloud redis instances create nexusdocs-cache \
  --size=1 \
  --region=europe-west1

# 5. Create GCS bucket
gsutil mb -l europe-west1 gs://nexusdocs-storage

# 6. Deploy with Cloud Build
gcloud builds submit --config=cloudbuild.yaml

# 7. Set up Cloud Run services
gcloud run deploy nexusdocs-api \
  --image=gcr.io/your-project/nexusdocs-api \
  --platform=managed \
  --region=europe-west1 \
  --allow-unauthenticated
```

---

## Security & Compliance

### Data Security

- **Encryption at rest**: AES-256
- **Encryption in transit**: TLS 1.3
- **Data isolation**: Complete tenant separation
- **Backup**: Daily automated backups

### Compliance

- **GDPR**: Data processing agreements available
- **HIPAA**: BAA available (Enterprise)
- **SOC 2**: Type II certified
- **ISO 27001**: Certified

### Data Residency

| Region | Data Center | Availability |
|--------|-------------|--------------|
| Europe | GCP europe-west1 | Default |
| US | GCP us-central1 | On request |
| APAC | GCP asia-southeast1 | Enterprise only |

---

## Support

| Plan | Support Channel | Response Time |
|------|-----------------|---------------|
| Trial | Community forums | Best effort |
| Basic | Email | 48 hours |
| Pro | Email + Chat | 24 hours |
| Enterprise | Dedicated manager | 4 hours |

### Contact

- **Sales**: sales@nexusdocs360.com
- **Support**: support@nexusdocs360.com
- **Status**: status.nexusdocs360.com

---

## FAQ

### Can I migrate from SaaS to On-Premise?

Yes, Enterprise customers can export all data and migrate to on-premise deployment. Contact support for migration assistance.

### What happens when my trial ends?

Your account downgrades to a limited free tier. Documents are retained for 30 days. Upgrade anytime to restore full access.

### Can I use my own LLM API keys?

Enterprise customers can bring their own API keys for OpenAI, Anthropic, or Google. This also allows usage-based billing on your own accounts.

### Is my data used for training?

No. Your documents are never used to train AI models. All data is processed in real-time and not retained by LLM providers.

---

<div align="center">
  <p><strong>Ready to start?</strong></p>
  <a href="https://app.nexusdocs360.com">Start Free Trial</a> |
  <a href="https://docs.nexusdocs360.com">Documentation</a> |
  <a href="mailto:sales@nexusdocs360.com">Contact Sales</a>
</div>
