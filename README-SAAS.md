# NouxCubeIA SaaS - Cloud-Hosted Document Intelligence

<div align="center">
  <h3>Enterprise AI Without Infrastructure Complexity</h3>
  <p><strong>Start in minutes, scale without limits</strong></p>
</div>

---

## Overview

NouxCubeIA SaaS is the cloud-hosted version of our intelligent document management platform. Get all the power of enterprise AI document processing without managing infrastructure, GPUs, or complex deployments.

### Why SaaS?

| Benefit | Description |
|---------|-------------|
| **Instant Start** | No hardware setup, no GPU configuration |
| **Auto-Scaling** | Handle any workload automatically |
| **Always Updated** | Latest features and security patches |
| **Managed Infrastructure** | We handle uptime, backups, and maintenance |
| **Predictable Pricing** | Pay for what you use, no capital expenditure |

### SaaS vs On-Premise Comparison

| Feature | SaaS | On-Premise |
|---------|------|------------|
| **Setup Time** | 5 minutes | 2-4 hours |
| **Hardware Required** | None | GPU server |
| **Authentication** | Clerk (SSO ready) | OIDC/SAML (KeyCloak, Azure AD) |
| **Billing** | Stripe integration | None |
| **Data Location** | Google Cloud (EU/US) | Your servers |
| **Maintenance** | Managed | Self-managed |
| **Features** | Signatures, Site Portal | Enterprise Connectors |
| **Best For** | SMBs, Fast deployment | Regulated industries, Air-gapped |

> **Need complete data sovereignty?** See [README-ONPREMISE.md](README-ONPREMISE.md) for self-hosted deployment.

---

## Quick Start

### 1. Sign Up

```
https://app.nouxcubeia.com/signup
```

1. Enter your email and create a password
2. Verify your email
3. Complete organization setup
4. You're ready to upload documents!

### 2. Upload Your First Document

```bash
# Using the API
curl -X POST https://api.nouxcubeia.com/api/v1/documents/upload \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@contract.pdf" \
  -F "folder_id=root"

# Response
{
  "id": "doc-uuid",
  "title": "contract.pdf",
  "status": "processing",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 3. Ask Emma AI

```bash
curl -X POST https://api.nouxcubeia.com/api/v1/emma/ask \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the payment terms in my contracts?",
    "workflow_type": "auto"
  }'

# Response
{
  "answer": "Based on your contracts, the payment terms are...",
  "sources": [
    {"document_id": "doc-123", "title": "Service Agreement 2024"}
  ],
  "confidence": 0.92
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      NouxCubeIA SaaS Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Client Layer                                 │    │
│  │                                                                      │    │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │    │
│  │  │  Web App     │   │  Mobile App  │   │  REST API    │            │    │
│  │  │  (Next.js)   │   │  (Future)    │   │  Integration │            │    │
│  │  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘            │    │
│  │         │                  │                  │                     │    │
│  └─────────┼──────────────────┼──────────────────┼─────────────────────┘    │
│            │                  │                  │                          │
│            └──────────────────┼──────────────────┘                          │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Authentication (Clerk)                            │    │
│  │                                                                      │    │
│  │  • Social Login (Google, Microsoft, GitHub)                         │    │
│  │  • Email/Password                                                   │    │
│  │  • SSO (SAML, OIDC) - Enterprise plans                              │    │
│  │  • MFA Support                                                       │    │
│  │                                                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                   API Gateway (Cloud Run)                            │    │
│  │                                                                      │    │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │    │
│  │  │  Main API    │   │ Weaviate Svc │   │ Storage Svc  │            │    │
│  │  │  (FastAPI)   │   │ (RAG+Emma)   │   │ (GCS)        │            │    │
│  │  │  :8000       │   │ :8007        │   │ :8003        │            │    │
│  │  └──────────────┘   └──────────────┘   └──────────────┘            │    │
│  │                                                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Data Layer                                   │    │
│  │                                                                      │    │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐            │    │
│  │  │ Cloud SQL    │   │ Weaviate     │   │ Cloud Storage│            │    │
│  │  │ (PostgreSQL) │   │ (Vectors)    │   │ (Documents)  │            │    │
│  │  └──────────────┘   └──────────────┘   └──────────────┘            │    │
│  │                                                                      │    │
│  │  ┌──────────────┐   ┌──────────────┐                               │    │
│  │  │ Redis        │   │ Pub/Sub      │                               │    │
│  │  │ (Cache)      │   │ (Events)     │                               │    │
│  │  └──────────────┘   └──────────────┘                               │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      AI Layer (GPU Cluster)                          │    │
│  │                                                                      │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │  vLLM Cluster (L4 GPUs)                                      │   │    │
│  │  │                                                               │   │    │
│  │  │  • Auto-scaling based on demand                              │   │    │
│  │  │  • Qwen3-4B-Thinking (default)                               │   │    │
│  │  │  • Multiple model options per plan                           │   │    │
│  │  │  • Regional deployment (EU/US)                               │   │    │
│  │  │                                                               │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Features

### Core Features (All Plans)

| Feature | Description |
|---------|-------------|
| **Document Upload** | PDF, Word, Excel, PowerPoint, images |
| **Emma AI Assistant** | Intelligent Q&A over your documents |
| **Semantic Search** | Find documents by meaning, not just keywords |
| **Folder Organization** | Hierarchical document organization |
| **Document Sharing** | Share with team members |
| **Version History** | Track document changes |
| **Audit Trail** | Complete activity logging |

### Advanced Features (Professional+)

| Feature | Description |
|---------|-------------|
| **Site Portal** | Branded portal for external document sharing |
| **Digital Signatures** | Request and track document signatures |
| **Workflows** | Automated document approval workflows |
| **Custom Metadata** | Define custom fields for documents |
| **API Access** | Full REST API for integrations |
| **Webhooks** | Real-time event notifications |

### Enterprise Features

| Feature | Description |
|---------|-------------|
| **SSO Integration** | SAML/OIDC with your identity provider |
| **Advanced Analytics** | Usage dashboards and insights |
| **SLA Guarantee** | 99.9% uptime commitment |
| **Priority Support** | Dedicated support channel |
| **Custom Models** | Fine-tuned AI for your domain |
| **Data Residency** | Choose EU or US data center |

---

## Site Portal: Secure External Sharing

The Site Portal allows you to create branded, secure portals for sharing documents with external parties (clients, vendors, partners).

### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SITE PORTAL FLOW                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. CREATE PORTAL                                                            │
│     ───────────────                                                          │
│     Admin creates portal with:                                               │
│     • Custom branding (logo, colors)                                        │
│     • Access permissions                                                     │
│     • Expiration settings                                                    │
│                                                                              │
│  2. INVITE GUESTS                                                            │
│     ─────────────                                                            │
│     ┌─────────────┐      ┌─────────────┐      ┌─────────────┐              │
│     │   Admin     │ ───▶ │   Email     │ ───▶ │   Guest     │              │
│     │  Dashboard  │      │  Invitation │      │  Receives   │              │
│     └─────────────┘      └─────────────┘      │    Link     │              │
│                                               └─────────────┘              │
│                                                                              │
│  3. GUEST ACCESS                                                             │
│     ────────────                                                             │
│     ┌─────────────┐      ┌─────────────┐      ┌─────────────┐              │
│     │   Guest     │ ───▶ │   OTP       │ ───▶ │   Portal    │              │
│     │   Clicks    │      │   Code      │      │   Access    │              │
│     │   Link      │      │   Verify    │      │   Granted   │              │
│     └─────────────┘      └─────────────┘      └─────────────┘              │
│                                                                              │
│  4. AUDIT EVERYTHING                                                         │
│     ───────────────                                                          │
│     • Document views tracked                                                 │
│     • Download history                                                       │
│     • Access timestamps                                                      │
│     • Revoke access anytime                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Portal API

```bash
# Create a Site Portal
curl -X POST https://api.nouxcubeia.com/api/v1/portals \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Client Documents - Acme Corp",
    "branding": {
      "logo_url": "https://example.com/logo.png",
      "primary_color": "#0066CC"
    },
    "settings": {
      "require_otp": true,
      "allow_download": true,
      "expires_at": "2024-12-31T23:59:59Z"
    }
  }'

# Add documents to portal
curl -X POST https://api.nouxcubeia.com/api/v1/portals/{portal_id}/documents \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": ["doc-123", "doc-456"]
  }'

# Invite guest
curl -X POST https://api.nouxcubeia.com/api/v1/portals/{portal_id}/guests \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "client@acme.com",
    "name": "John Smith",
    "permissions": ["view", "download"]
  }'
```

---

## Digital Signatures

Request and track legally-binding digital signatures on your documents.

### Signature Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SIGNATURE REQUEST FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐                                                             │
│  │  REQUESTER  │                                                             │
│  │  Uploads    │                                                             │
│  │  Document   │                                                             │
│  └──────┬──────┘                                                             │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SIGNATURE REQUEST                                                   │    │
│  │                                                                      │    │
│  │  • Select document                                                   │    │
│  │  • Define signature fields (position, size)                         │    │
│  │  • Add signers (name, email, order)                                 │    │
│  │  • Set deadline                                                      │    │
│  │  • Optional: Add message                                             │    │
│  │                                                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SIGNER NOTIFICATION                                                 │    │
│  │                                                                      │    │
│  │  📧 Email sent with:                                                 │    │
│  │     • Document preview                                               │    │
│  │     • Secure signing link                                            │    │
│  │     • Instructions                                                   │    │
│  │                                                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  SIGNING PROCESS                                                     │    │
│  │                                                                      │    │
│  │  1. Signer opens link                                                │    │
│  │  2. OTP verification                                                 │    │
│  │  3. Review document                                                  │    │
│  │  4. Draw/type signature                                              │    │
│  │  5. Confirm & submit                                                 │    │
│  │                                                                      │    │
│  └────────────────────────────────┬────────────────────────────────────┘    │
│                                   │                                          │
│                                   ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  COMPLETION                                                          │    │
│  │                                                                      │    │
│  │  ✅ All parties signed                                               │    │
│  │  📄 Signed PDF generated                                             │    │
│  │  🔐 Audit certificate attached                                       │    │
│  │  📧 Notification to all parties                                      │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Signature API

```bash
# Create signature request
curl -X POST https://api.nouxcubeia.com/api/v1/signatures \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc-123",
    "title": "Service Agreement Signature",
    "message": "Please review and sign the attached agreement.",
    "signers": [
      {
        "name": "John Smith",
        "email": "john@acme.com",
        "order": 1,
        "fields": [
          {"type": "signature", "page": 5, "x": 100, "y": 650, "required": true},
          {"type": "date", "page": 5, "x": 350, "y": 650}
        ]
      },
      {
        "name": "Jane Doe",
        "email": "jane@client.com",
        "order": 2,
        "fields": [
          {"type": "signature", "page": 5, "x": 100, "y": 700, "required": true}
        ]
      }
    ],
    "deadline": "2024-02-01T23:59:59Z",
    "reminders": true
  }'

# Check signature status
curl https://api.nouxcubeia.com/api/v1/signatures/{signature_id} \
  -H "Authorization: Bearer $API_KEY"

# Response
{
  "id": "sig-uuid",
  "status": "in_progress",
  "document_id": "doc-123",
  "signers": [
    {"email": "john@acme.com", "status": "signed", "signed_at": "2024-01-20T14:30:00Z"},
    {"email": "jane@client.com", "status": "pending", "viewed_at": "2024-01-20T15:00:00Z"}
  ],
  "created_at": "2024-01-19T10:00:00Z",
  "deadline": "2024-02-01T23:59:59Z"
}
```

---

## Authentication (Clerk)

NouxCubeIA SaaS uses [Clerk](https://clerk.com) for authentication, providing a seamless sign-up and login experience.

### Supported Methods

| Method | Description | Plans |
|--------|-------------|-------|
| **Email/Password** | Traditional login | All |
| **Google** | OAuth with Google | All |
| **Microsoft** | OAuth with Microsoft 365 | All |
| **GitHub** | OAuth with GitHub | All |
| **SAML SSO** | Enterprise identity providers | Enterprise |
| **OIDC SSO** | OpenID Connect providers | Enterprise |

### User Management

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    USER & ORGANIZATION MODEL                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ORGANIZATION (Tenant)                                               │    │
│  │                                                                      │    │
│  │  • Billing entity                                                    │    │
│  │  • Data isolation boundary                                           │    │
│  │  • Subscription plan                                                 │    │
│  │  • Storage quota                                                     │    │
│  │                                                                      │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │  MEMBERS                                                     │    │    │
│  │  │                                                              │    │    │
│  │  │  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐    │    │    │
│  │  │  │  Owner  │   │  Admin  │   │  Member │   │ Viewer  │    │    │    │
│  │  │  │         │   │         │   │         │   │         │    │    │    │
│  │  │  │ • Full  │   │ • User  │   │ • Upload│   │ • View  │    │    │    │
│  │  │  │   access│   │   mgmt  │   │ • Edit  │   │   only  │    │    │    │
│  │  │  │ • Billing│  │ • Share │   │ • Share │   │         │    │    │    │
│  │  │  │ • Delete│   │         │   │         │   │         │    │    │    │
│  │  │  └─────────┘   └─────────┘   └─────────┘   └─────────┘    │    │    │
│  │  │                                                              │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Inviting Team Members

```bash
# Invite a team member
curl -X POST https://api.nouxcubeia.com/api/v1/organization/invites \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "colleague@company.com",
    "role": "member"
  }'
```

---

## Billing & Pricing

NouxCubeIA SaaS uses Stripe for secure payment processing.

### Plans

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PRICING PLANS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │     STARTER     │  │  PROFESSIONAL   │  │   ENTERPRISE    │             │
│  │                 │  │                 │  │                 │             │
│  │    €29/month    │  │    €99/month    │  │    Custom       │             │
│  │                 │  │                 │  │                 │             │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤             │
│  │                 │  │                 │  │                 │             │
│  │ ✓ 3 users       │  │ ✓ 10 users      │  │ ✓ Unlimited     │             │
│  │ ✓ 5GB storage   │  │ ✓ 50GB storage  │  │ ✓ Custom storage│             │
│  │ ✓ 100 AI/month  │  │ ✓ 1000 AI/month │  │ ✓ Unlimited AI  │             │
│  │ ✓ Email support │  │ ✓ Site Portal   │  │ ✓ SSO           │             │
│  │                 │  │ ✓ Signatures    │  │ ✓ Custom models │             │
│  │                 │  │ ✓ API access    │  │ ✓ SLA 99.9%     │             │
│  │                 │  │ ✓ Webhooks      │  │ ✓ Dedicated     │             │
│  │                 │  │                 │  │   support       │             │
│  │                 │  │                 │  │                 │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                              │
│  All plans include:                                                          │
│  • Unlimited document uploads (within storage)                              │
│  • Emma AI Assistant                                                         │
│  • Semantic search                                                           │
│  • Version history                                                           │
│  • Audit trail                                                               │
│  • SSL encryption                                                            │
│  • Daily backups                                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Usage Metering

AI queries are metered and counted against your plan limits:

| Operation | AI Credits |
|-----------|------------|
| Simple search | 1 |
| Emma Q&A (short answer) | 5 |
| Emma analysis (detailed) | 10 |
| Document summarization | 15 |
| Multi-document comparison | 20 |

### Billing API

```bash
# Get current usage
curl https://api.nouxcubeia.com/api/v1/billing/usage \
  -H "Authorization: Bearer $API_KEY"

# Response
{
  "period": "2024-01",
  "plan": "professional",
  "usage": {
    "storage_gb": 23.5,
    "storage_limit_gb": 50,
    "ai_queries": 342,
    "ai_limit": 1000,
    "users": 7,
    "user_limit": 10
  },
  "billing_cycle_ends": "2024-01-31T23:59:59Z"
}

# Get invoices
curl https://api.nouxcubeia.com/api/v1/billing/invoices \
  -H "Authorization: Bearer $API_KEY"

# Upgrade plan
curl -X POST https://api.nouxcubeia.com/api/v1/billing/upgrade \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan": "enterprise"}'
```

---

## API Reference

### Base URL

```
Production: https://api.nouxcubeia.com
Staging:    https://api-staging.nouxcubeia.com
```

### Authentication

All API requests require a Bearer token:

```bash
curl -H "Authorization: Bearer $API_KEY" \
  https://api.nouxcubeia.com/api/v1/documents
```

Get your API key from: **Settings → API Keys → Create Key**

### Rate Limits

| Plan | Requests/minute | Requests/day |
|------|-----------------|--------------|
| Starter | 60 | 5,000 |
| Professional | 300 | 50,000 |
| Enterprise | Custom | Custom |

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/documents` | GET | List documents |
| `/api/v1/documents` | POST | Upload document |
| `/api/v1/documents/{id}` | GET | Get document details |
| `/api/v1/documents/{id}` | DELETE | Delete document |
| `/api/v1/documents/search` | POST | Search documents |
| `/api/v1/emma/ask` | POST | Ask Emma AI |
| `/api/v1/emma/conversations` | GET | List conversations |
| `/api/v1/folders` | GET/POST | Manage folders |
| `/api/v1/portals` | GET/POST | Manage site portals |
| `/api/v1/signatures` | GET/POST | Manage signatures |

### Webhooks

Configure webhooks to receive real-time notifications:

```bash
# Create webhook
curl -X POST https://api.nouxcubeia.com/api/v1/webhooks \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-server.com/webhook",
    "events": ["document.uploaded", "document.processed", "signature.completed"],
    "secret": "your-webhook-secret"
  }'
```

### Webhook Events

| Event | Description |
|-------|-------------|
| `document.uploaded` | Document upload started |
| `document.processed` | Document fully indexed |
| `document.deleted` | Document deleted |
| `signature.requested` | Signature request created |
| `signature.signed` | A signer completed |
| `signature.completed` | All signers completed |
| `signature.declined` | Signer declined |
| `portal.accessed` | Guest accessed portal |

---

## Data Security

### Encryption

| Layer | Method |
|-------|--------|
| **In Transit** | TLS 1.3 |
| **At Rest** | AES-256 |
| **Backups** | AES-256 + separate key |

### Data Isolation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MULTI-TENANT ISOLATION                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐       │
│  │    Tenant A       │  │    Tenant B       │  │    Tenant C       │       │
│  │                   │  │                   │  │                   │       │
│  │  ┌─────────────┐  │  │  ┌─────────────┐  │  │  ┌─────────────┐  │       │
│  │  │  Database   │  │  │  │  Database   │  │  │  │  Database   │  │       │
│  │  │  (Isolated) │  │  │  │  (Isolated) │  │  │  │  (Isolated) │  │       │
│  │  └─────────────┘  │  │  └─────────────┘  │  │  └─────────────┘  │       │
│  │                   │  │                   │  │                   │       │
│  │  ┌─────────────┐  │  │  ┌─────────────┐  │  │  ┌─────────────┐  │       │
│  │  │  Storage    │  │  │  │  Storage    │  │  │  │  Storage    │  │       │
│  │  │  Bucket     │  │  │  │  Bucket     │  │  │  │  Bucket     │  │       │
│  │  └─────────────┘  │  │  └─────────────┘  │  │  └─────────────┘  │       │
│  │                   │  │                   │  │                   │       │
│  │  ┌─────────────┐  │  │  ┌─────────────┐  │  │  ┌─────────────┐  │       │
│  │  │  Vector     │  │  │  │  Vector     │  │  │  │  Vector     │  │       │
│  │  │  Namespace  │  │  │  │  Namespace  │  │  │  │  Namespace  │  │       │
│  │  └─────────────┘  │  │  └─────────────┘  │  │  └─────────────┘  │       │
│  │                   │  │                   │  │                   │       │
│  └───────────────────┘  └───────────────────┘  └───────────────────┘       │
│                                                                              │
│  ✓ Row-level security in database                                           │
│  ✓ Separate storage buckets per tenant                                      │
│  ✓ Tenant-scoped vector search                                              │
│  ✓ Complete audit isolation                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Compliance

| Standard | Status |
|----------|--------|
| **GDPR** | Compliant |
| **SOC 2 Type II** | In progress |
| **ISO 27001** | Planned |

### Data Residency

Choose your data region during signup:

| Region | Location | Availability |
|--------|----------|--------------|
| **EU** | Belgium (europe-west1) | Available |
| **US** | Iowa (us-central1) | Available |
| **UK** | London (europe-west2) | Coming soon |

---

## Integrations

### Zapier

Connect NouxCubeIA with 5,000+ apps via Zapier:

- **Triggers**: Document uploaded, Signature completed, Portal accessed
- **Actions**: Upload document, Create folder, Ask Emma

### Make (Integromat)

Full integration with Make for complex workflows.

### Native Integrations

| Integration | Status | Description |
|-------------|--------|-------------|
| Google Drive | Available | Import documents from Drive |
| Dropbox | Available | Sync with Dropbox folders |
| OneDrive | Coming soon | Microsoft 365 integration |
| Slack | Available | Notifications and commands |
| Microsoft Teams | Coming soon | Teams integration |

---

## SDK & Libraries

### Official SDKs

```bash
# Python
pip install nouxcubeia

# JavaScript/TypeScript
npm install @nouxcubeia/sdk

# Go
go get github.com/nouxcubeia/nouxcubeia-go
```

### Python Example

```python
from nouxcubeia import NouxCubeIA

client = NouxCubeIA(api_key="your-api-key")

# Upload document
doc = client.documents.upload(
    file_path="contract.pdf",
    folder_id="folder-123"
)

# Ask Emma
response = client.emma.ask(
    question="What are the key terms in this contract?",
    document_ids=[doc.id]
)

print(response.answer)
print(response.sources)
```

### TypeScript Example

```typescript
import { NouxCubeIA } from '@nouxcubeia/sdk';

const client = new NouxCubeIA({ apiKey: 'your-api-key' });

// Upload document
const doc = await client.documents.upload({
  file: fileBuffer,
  filename: 'contract.pdf',
  folderId: 'folder-123'
});

// Ask Emma
const response = await client.emma.ask({
  question: 'What are the key terms in this contract?',
  documentIds: [doc.id]
});

console.log(response.answer);
```

---

## Support

### Self-Service

| Resource | URL |
|----------|-----|
| **Documentation** | https://docs.nouxcubeia.com |
| **API Reference** | https://api.nouxcubeia.com/docs |
| **Status Page** | https://status.nouxcubeia.com |
| **Community Forum** | https://community.nouxcubeia.com |

### Contact Support

| Plan | Channel | Response Time |
|------|---------|---------------|
| Starter | Email | 48 hours |
| Professional | Email + Chat | 24 hours |
| Enterprise | Dedicated + Phone | 4 hours |

### Enterprise Support

- **Email**: enterprise@nouxcubeia.com
- **Phone**: Available for Enterprise plans
- **Dedicated CSM**: Assigned account manager

---

## Migrating from On-Premise

If you're currently using NouxCubeIA On-Premise and want to migrate to SaaS:

### Migration Steps

1. **Export Documents**: Use the export API to download all documents
2. **Export Metadata**: Export folder structure and document metadata
3. **Create SaaS Account**: Sign up for appropriate plan
4. **Import Documents**: Use bulk import API
5. **Verify Data**: Confirm all documents are properly indexed
6. **Update Integrations**: Point API integrations to new endpoint
7. **Decommission On-Premise**: After verification period

### Migration Support

Enterprise customers receive dedicated migration support:
- Migration planning session
- Data transfer assistance
- Parallel running period
- Verification checklist

Contact: migrations@nouxcubeia.com

---

## Frequently Asked Questions

### General

**Q: Can I export my data?**
A: Yes, you can export all documents and metadata at any time via API or UI.

**Q: What happens if I cancel?**
A: You have 30 days to export your data. After that, data is permanently deleted.

**Q: Is there a free trial?**
A: Yes, 14-day free trial with full Professional features.

### Security

**Q: Where is my data stored?**
A: In your chosen region (EU or US) on Google Cloud Platform.

**Q: Do you have access to my documents?**
A: Support staff cannot access document contents without explicit permission.

**Q: Is data encrypted?**
A: Yes, AES-256 at rest and TLS 1.3 in transit.

### AI

**Q: How does Emma AI work?**
A: Emma uses a RAG pipeline to search your documents and generate answers with citations.

**Q: Is my data used to train AI models?**
A: No, your data is never used for model training.

**Q: What models are available?**
A: Qwen3-4B (default), GPT-4 (Enterprise), Claude (Enterprise).

---

<div align="center">
  <h3>Ready to transform your document management?</h3>
  <p>
    <a href="https://app.nouxcubeia.com/signup">Start Free Trial</a> |
    <a href="https://nouxcubeia.com/demo">Book a Demo</a> |
    <a href="mailto:sales@nouxcubeia.com">Contact Sales</a>
  </p>
  <p><em>NouxCubeIA SaaS - Enterprise AI, Zero Infrastructure</em></p>
</div>
