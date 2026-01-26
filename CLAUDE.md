# CLAUDE.md - NouxCubeIA Project Guidelines

This file provides guidance to Claude Code (claude.ai/code) when working with code in the NouxCubeIA repository.

## Development Commands

### Backend Development
- **Start development environment (RECOMMENDED)**: `cd backend/docker && ./start-dev.sh`
- **Start production environment**: `cd backend/docker && ./start-prod.sh`
- **Start development environment (manual)**: `cd backend/docker && docker compose up -d`
- **Start production environment (manual)**: `cd backend/docker && docker compose -f docker-compose.prod.yml up -d`
- **API server (local without Docker)**: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Initialize database**: `cd backend && python -m scripts.init_db`
- **Database migrations**: `cd backend && alembic upgrade head`
- **Run tests**: `cd backend/tests && ./run_tests.sh`
- **Run tests (with real GCS)**: `cd backend/docker && docker compose -f docker-compose.test.yml up`
- **Clean rebuild**: `./clean_and_rebuild.sh` (from project root)

### Frontend Development
- **Node version**: Use Node.js 18+ (required for Next.js 15)
  - `nvm use 18` or `nvm use 20` (if using nvm)
- **Start development**: `cd frontend && npm run dev` (uses Turbopack)
- **Build**: `cd frontend && npm run build`
- **Lint**: `cd frontend && npm run lint`
- **Install dependencies**: `cd frontend && npm install`

### Full Stack Development
- **Backend services**: `cd backend/docker && ./start-dev.sh` (PostgreSQL, Redis, Weaviate, Elasticsearch, microservices with live reload)
- **Frontend**: `cd frontend && npm run dev` (runs on port 3000)
- **API Documentation**: Available at `http://localhost:8000/docs` when backend is running

### Docker Development Modes

#### Development Mode (Default - Recommended for development)
```bash
cd backend/docker && ./start-dev.sh
# OR manually:
cd backend/docker && docker compose up -d
```
**Features:**
- **Live code reloading**: Python files are mounted as volumes, changes reflect immediately
- **No rebuilds needed**: Only rebuilds when `requirements.txt` or `Dockerfile` changes
- **Auto-reload enabled**: uvicorn starts with `--reload` flag
- **Faster iteration**: Ideal for active development

**What's mounted:**
- `backend/` → Container's `/app` (main API)
- `microservices/storage-service/app` → Container's `/app/app`
- `microservices/weaviate-service/app` → Container's `/app/app`
- `microservices/elasticsearch-service/app` → Container's `/app/app`

#### Production Mode
```bash
cd backend/docker && ./start-prod.sh
# OR manually:
cd backend/docker && docker compose -f docker-compose.prod.yml up -d
```
**Features:**
- **Optimized images**: Multi-stage builds for smaller image sizes
- **No volume mounting**: Code is copied into containers during build
- **Production settings**: Optimized for performance and security
- **Full rebuilds**: Rebuilds entire images when code changes

#### Test Mode
```bash
cd backend/docker && docker compose -f docker-compose.test.yml up
```
**Features:**
- **Isolated testing**: Separate database and services for tests
- **Real GCS integration**: Uses actual Google Cloud Storage for realistic testing
- **Coverage reports**: Generates test coverage in `backend/tests/coverage_report/`
- **Automatic cleanup**: Services stop after tests complete

## Architecture Overview

### System Design
**NouxCubeIA** is a **multi-tenant intelligent document management system** with a microservices architecture that provides a 360-degree view of organizational documents:

**Backend**: FastAPI with Python 3.9+, using async/await patterns throughout
**Frontend**: Next.js 15 with App Router, TypeScript, and OIDC/SAML authentication
**Database**: PostgreSQL for relational data, Weaviate for vector embeddings, Elasticsearch for full-text search
**Storage**: Google Cloud Storage for files
**AI/ML**: vLLM (GPU inference) + Anthropic Skill Custom for multi-agent orchestration (Emma AI)

### Key Architectural Patterns

#### Multi-Tenant Architecture
- Complete tenant isolation at database and storage levels
- Tenant-specific settings and quotas in models
- Tenant context passed through dependency injection in FastAPI endpoints
- Authentication via OIDC/SAML providers (KeyCloak, Azure AD, Okta)

#### Authentication Architecture (On-Premise OIDC/SAML)

**Authentication Flow (JIT Provisioning Supported):**
```
┌─────────────────────────────────────────────────────────────┐
│  LOGIN FLOW (OIDC/SAML)                                     │
├─────────────────────────────────────────────────────────────┤
│  1. User → Login page → Redirect to IdP                      │
│  2. IdP authenticates → JWT/SAML assertion                   │
│  3. Frontend → POST /api/v1/auth/callback (token)            │
│  4. Backend:                                                 │
│     ├── Validates token against IdP JWKS/metadata            │
│     ├── Extracts user info (email, groups, attributes)       │
│     ├── JIT: Creates user if not exists (from IdP groups)    │
│     ├── Maps IdP groups → Application roles                  │
│     └── Returns session with permissions                     │
│  5. Backend → { user, permissions, tenant_id }               │
│  6. Frontend stores state, redirects to dashboard            │
└─────────────────────────────────────────────────────────────┘
```

**Key Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/login` | POST | Initiates OIDC/SAML flow |
| `/api/v1/auth/callback` | POST | Handles IdP callback, creates session |
| `/api/v1/auth/logout` | POST | Logs event, clears session |
| `/api/v1/auth/me` | GET | Returns current user data |

**Configuration:**
```bash
# OIDC Configuration (.env)
AUTH_PROVIDER=oidc
OIDC_ISSUER_URL=https://keycloak.company.com/realms/nexusdocs
OIDC_CLIENT_ID=nexusdocs-client
OIDC_CLIENT_SECRET=your-client-secret
OIDC_SCOPES=openid,profile,email,groups

# Group to Role Mapping
OIDC_ADMIN_GROUP=NouxCubeIA-Admins
OIDC_USER_GROUP=NouxCubeIA-Users
```

**Important:**
- **JIT Provisioning**: Users created automatically on first login from IdP groups.
- **Group Mapping**: IdP groups map to application roles (Admin, User, Viewer).
- **No External Dependencies**: Authentication handled by your organization's IdP.
- **SSO Ready**: Integrates with existing enterprise identity infrastructure.

#### Microservices Design
- **Main API** (port 8000): Core business logic, authentication, document management
- **Storage Service** (port 8003): Google Cloud Storage operations with signed URLs
- **Weaviate Service** (port 8007): Vector search, RAG pipeline (7-layer), Emma AI (Agent Framework orchestration)
- **vLLM Server** (internal): High-throughput GPU inference with OpenAI-compatible API
- **Elasticsearch Service** (port 8008): Full-text search, document indexing, hybrid search
- **Gotenberg Service** (port 3000): Document conversion, PDF generation, thumbnail creation
- **Background Worker** (port 8100): Async task processing with Celery
- **Camunda Service** (port 8080): BPMN workflow orchestration for document pipelines
- **LangExtract Service** (port 8009): Structured document extraction with LLM providers

#### Modular Architecture (SaaS vs On-Premise)

> **📖 Full Documentation**: [`docs/architecture/MODULAR_ARCHITECTURE.md`](docs/architecture/MODULAR_ARCHITECTURE.md)

The codebase supports different deployment modes through a modular architecture:

```
backend/
├── core/                    # Shared core (always loaded)
│   └── acl/                 # ACL abstraction (ACLProvider, ACLProviderFactory)
│
├── modules/
│   ├── on_premise/          # On-Premise module (DEPLOYMENT_MODE=on_premise)
│   │   ├── acl/provider.py  # JSONBACLProvider (uses IndexedDocument JSONB)
│   │   └── module.py        # Module registration
│   │
│   └── saas/                # SaaS module (DEPLOYMENT_MODE=saas)
│       ├── acl/provider.py  # TableACLProvider (uses DocumentACL table)
│       └── module.py        # Module registration
│
└── app/main.py              # Loads module based on DEPLOYMENT_MODE
```

**Key Differences:**

| Feature | SaaS | On-Premise |
|---------|------|------------|
| Auth | Clerk | OIDC/SAML |
| ACL | DocumentACL table | JSONB in IndexedDocument |
| Documents | `documents` table | `indexed_documents` table |
| Billing | Stripe | None |
| Features | Signatures, Site Portal | Connectors (Alfresco, SharePoint) |

**Configuration:**
```bash
# Set deployment mode in .env
DEPLOYMENT_MODE=on_premise  # or: saas, custom
```

#### Database Schema Highlights
- **Multi-tenant models**: All core entities have tenant_id foreign keys
- **Audit trails**: Comprehensive tracking for compliance (document views, role assignments)
- **RBAC system**: Role-based access control with fine-grained permissions
- **Agent system**: AI agents with conversation history and execution tracking
- **ACL JSONB**: Fine-grained access control stored in IndexedDocument

#### SLM Router - Small Language Model Query Planning

> **📖 Full Documentation**: [`docs/architecture/SLM_ROUTER.md`](docs/architecture/SLM_ROUTER.md)

The SLM Router is a unified query routing system that uses a Small Language Model to generate **TOON (Task-Oriented Orchestration Notation)** plans:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TRADITIONAL RAG                    →    SLM ROUTER APPROACH                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  ❌ Always invoke full RAG          →    ✅ Route to optimal data source     │
│  ❌ Hardcoded routing rules         →    ✅ LLM-generated execution plans    │
│  ❌ 10K+ tokens per query           →    ✅ 500-1000 tokens (70-90% savings) │
│  ❌ No learning capability          →    ✅ Continuous learning from usage   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Route Types:**
| Route | Description | Data Source |
|-------|-------------|-------------|
| `GRAPH_ONLY` | Structural/counting queries | Apache AGE |
| `VECTOR_ONLY` | Semantic search queries | Weaviate |
| `HYBRID` | Structure + content | Both |
| `ASK_CLARIFY` | Ambiguous query | User input |

**Query Flow:**
```
User: "¿Cuántos contratos tiene ACME?"
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SLM Router                                                                   │
│ 1. SLM generates TOON plan: route=GRAPH_ONLY, operation=COUNT               │
│ 2. Executor runs Cypher: MATCH (d:structural_document) WHERE...             │
│ 3. Returns: count=5, context="ACME has 5 contracts"                         │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
Emma receives structured context → "ACME tiene 5 contratos..."
         │
         ▼
🎯 NO DOCUMENT CONTENT READ - 70% token savings
```

**Key Components:**
- `weaviate-service/app/services/slm_router/` - SLM Router package
  - `router.py` - Main orchestrator
  - `toon_schema.py` - TOON models and guardrails
  - `slm_client.py` - SLM client (Qwen2-0.5B)
  - `toon_executor.py` - Plan execution
  - `tenant_schema.py` - Tenant context
  - `history_manager.py` - Conversation history
  - `continuous_learning.py` - Automated fine-tuning
- `weaviate-service/app/api/slm_router.py` - REST endpoints (`/slm/*`)

**API Endpoints:**
| Endpoint | Description |
|----------|-------------|
| `POST /slm/route` | Plan and execute a query |
| `POST /slm/plan` | Generate TOON plan only |
| `GET /slm/health` | Health check |
| `GET /slm/metrics` | Router metrics |

**Configuration:**
```bash
SLM_ROUTER_ENABLED=true
SLM_MODEL=Qwen/Qwen2-0.5B-Instruct
SLM_BASE_URL=http://vllm:8000/v1
```

### File Structure Conventions

#### Backend (`/backend/app/`)
- `api/v1/`: Versioned REST endpoints, each file handles one domain
- `core/`: Configuration, security, logging - shared infrastructure
- `db/`: SQLAlchemy models and database configuration
- `schemas/`: Pydantic models for request/response validation
- `services/`: Business logic layer, one service per domain

#### Frontend (`/frontend/src/`)
- `app/`: Next.js App Router structure with nested layouts
- `components/`: Reusable UI components, organized by domain
- `lib/`: Utilities, API client, types, and service layers
- `contexts/`: React Context for global state management

### Technology Stack Details

#### Backend Technologies
- **FastAPI**: High-performance async web framework
- **SQLAlchemy 2.0**: Modern ORM with async support
- **Alembic**: Database migration management
- **OIDC/SAML**: Authentication via KeyCloak, Azure AD, Okta
- **Weaviate**: Vector database for semantic search
- **Apache AGE**: PostgreSQL graph extension for SLM Router (structural queries via Cypher)
- **Anthropic Skill Custom**: Multi-agent orchestration with ChatAgent, @ai_function decorators
- **vLLM**: High-throughput GPU inference server (Qwen3-14B, OpenAI-compatible API)
- **Elasticsearch**: Full-text search and document indexing
- **Redis**: Caching and session storage
- **Celery**: Distributed task queue for async processing
- **Camunda**: BPMN workflow orchestration engine (replacing Temporal.io)

#### Frontend Technologies
- **Next.js 15**: React framework with App Router
- **OIDC/SAML Integration**: Supports KeyCloak, Azure AD, Okta
- **shadcn/ui**: UI component library based on Radix UI
- **Tailwind CSS**: Utility-first styling
- **Zod**: Schema validation
- **React Hook Form**: Form management

## Environment Setup

### Node Version Management (NVM)
This project uses NVM (Node Version Manager) for managing Node.js versions:
- **Frontend requires**: Node.js 18.18.0+ or 20.0.0+ (for Next.js 15)
- **Switch Node version**: `nvm use 18` or `nvm use 20`
- **Install if needed**: `nvm install 18` or `nvm install 20`
- **Set default**: `nvm alias default 18`

Common NVM commands:
- `nvm list` - Show installed versions
- `nvm current` - Show current version
- `nvm use <version>` - Switch to specific version

## Development Guidelines

### Database Operations
- Always use tenant isolation in queries: `filter(Model.tenant_id == current_tenant.id)`
- Use async database sessions: `async with get_async_db() as db:`
- Create migrations for schema changes: `alembic revision --autogenerate -m "description"`

### API Development
- Follow REST conventions in `/api/v1/` endpoints
- Use dependency injection for database sessions and authentication
- Implement proper error handling with custom exception classes
- Include comprehensive request/response schema validation

### Security Requirements
- All API endpoints require authentication except public ones
- Implement tenant-based authorization for data access
- Never log sensitive information (API keys, tokens, passwords)
- Use environment variables for all secrets and configuration

### Testing Approach
- Tests use isolated PostgreSQL database via Docker Compose
- Run full test suite with `./tests/run_tests.sh` from backend/tests directory
- Tests include API integration tests and service unit tests
- Coverage reports generated in `backend/tests/coverage_report/`
- **Test environment uses real GCS** (not mocks) for realistic testing
- GCS credentials must be mounted at `./credentials:/app/credentials:ro` for tests

### Storage Configuration
- **All environments use real GCS** (no mocks for realistic testing)
- **Multi-tenant architecture**: One bucket per tenant (team/organization)
- **Multiple users per tenant**: Users share the same bucket within their organization
- **Development mode**: Uses real GCS with credentials mounted from `./credentials` directory
- **Test mode**: Uses real GCS with credentials mounted from `./credentials` directory  
- **Production mode**: Uses real GCS with service account credentials
- Place GCS service account JSON file in `/credentials/nexus-document-ia-04252dae0146.json`

#### Bucket Naming Convention
- **Per-tenant buckets**: `{org-name}-{hash}` (e.g., `org-john-doe-abc12345`)
- **Test buckets**: Same name + `-test` suffix for testing isolation
- **Automatic creation**: Buckets created when new user registers (creates new org)
- **File organization**: Within bucket, files are organized by user paths for access control

#### User Registration Flow
- **New user signup**: Creates new tenant (organization) + bucket automatically
- **Invited user**: TODO - Should join existing tenant when invited by admin
- **Multi-user tenants**: Multiple users can belong to same tenant/bucket

### Code Quality Standards
- Use async/await patterns consistently in backend
- Follow TypeScript strict mode in frontend
- Implement comprehensive error handling
- Use structured logging with request correlation IDs

## Troubleshooting

### Next.js Build/Module Errors
If you encounter module resolution errors like "Export default doesn't exist":
1. **Clear Next.js cache**: `rm -rf frontend/.next`
2. **Check Node version**: `cd frontend && nvm current` (should be 18+)
3. **Switch if needed**: `nvm use 18` or `nvm use 20`
4. **Reinstall dependencies**: `rm -rf node_modules && npm install`
5. **Restart dev server**: `npm run dev`

### Docker Issues
- **Permission denied**: Add user to docker group: `sudo usermod -aG docker $USER`
- **Port already in use**: Check with `docker ps` and stop conflicting containers
- **Out of space**: Clean up with `docker system prune -a`

### Common Frontend Errors
- **Module not found**: Usually a cache issue, follow Next.js troubleshooting steps above
- **Type errors**: Run `npm run lint` to check for TypeScript issues
- **Tailwind not working**: Ensure `npm run dev` is running (it compiles Tailwind)

## Common Development Workflows

### Adding New API Endpoint
1. Create Pydantic schemas in `schemas/`
2. Add route in appropriate `api/v1/` file
3. Implement business logic in `services/`
4. Add database models if needed with migration
5. Write tests in `tests/test_api/`

### Adding New Microservice Feature
1. Identify appropriate microservice (Weaviate Service, Storage Service, Elasticsearch Service)
2. Implement endpoint in microservice's `api/` directory
3. Update main API to call microservice
4. Add necessary environment variables
5. Update docker-compose configuration

### Working with Anthropic Skill Custom
The Weaviate Service includes a complete Anthropic Skill Custom + vLLM integration for high-throughput GPU inference:

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                     Emma Service                            │
│          (PlanningFlow + RAG Pipeline Orchestration)        │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
   ┌─────▼─────┐   ┌────▼──────┐  ┌────▼────────┐
   │ Sequential│   │PlanningFlow│  │ RAG Pipeline │
   │ Workflow  │   │(Graph-based)│  │  (Fallback)  │
   └─────┬─────┘   └────┬──────┘  └──────────────┘
         └───────┬──────┘
                 │
    ┌────────────▼────────────────────────────────┐
    │        Agent Framework Layer                 │
    │  • ChatAgent (stateless per invocation)      │
    │  • AgentThread (state management)            │
    │  • @ai_function decorators (tools)           │
    │  • Middleware (logging, auth)                │
    └────────────┬────────────────────────────────┘
                 │
    ┌────────────▼────────────────────────────────┐
    │        LLM Provider Factory                  │
    │  • vLLM (primary) → Qwen3-4B-Thinking        │
    │  • OpenAI (fallback) → GPT-4o-mini           │
    │  • Anthropic (fallback) → Claude 3.5        │
    └────────────┬────────────────────────────────┘
                 │
    ┌────────────▼────────────────────────────────┐
    │           vLLM Server (Docker)               │
    │  • GPU: NVIDIA CUDA 12.2 (RTX 4090)          │
    │  • API: OpenAI-compatible (:8000)            │
    │  • Model: Qwen/Qwen3-4B-Thinking-2507        │
    │  • Context: 256K native (32K recommended)    │
    │  • Thinking: Automatic <think> blocks        │
    └─────────────────────────────────────────────┘
```

**Structure:**
```
weaviate-service/app/agents/
├── config.py          # Agent configuration (providers, timeouts)
├── model_client.py    # Multi-provider LLM client factory (vLLM primary)
├── orchestrator.py    # Main entry point
├── agents/            # Specialized agents (Search, Analyst, Contract, Compliance, Summarizer)
├── tools/             # RAG pipeline wrappers as @ai_function tools
└── workflows/         # Orchestration patterns (Sequential, PlanningFlow)
```

**Usage:**
```python
from app.agents import get_orchestrator, WorkflowType

orchestrator = get_orchestrator()
result = await orchestrator.execute(
    query="Analyze the contract for compliance issues",
    tenant_id="tenant-123",
    workflow_type=WorkflowType.AUTO  # or SEQUENTIAL, PLANNING_FLOW
)
```

**Supported LLM Providers:**
- `LLM_PROVIDER=vllm` - **Primary** - High-throughput GPU inference (Qwen3-4B)
- `LLM_PROVIDER=ollama` - Legacy local models (llama3.2, qwen2.5, mistral)
- `LLM_PROVIDER=openai` - Fallback to GPT-4o, GPT-4o-mini
- `LLM_PROVIDER=anthropic` - Fallback to Claude 3.5 Sonnet, Claude 3 Opus
- `LLM_PROVIDER=google` - Fallback to Gemini 1.5 Flash, Gemini 1.5 Pro

#### Recommended Model Configuration (RTX 4090 24GB)

**Text-Only RAG Configuration (RECOMMENDED):**
```
┌─────────────────────────────────────────────────────────────┐
│  RECOMMENDED: Text-Only RAG with BGE-M3 Embeddings          │
├─────────────────────────────────────────────────────────────┤
│  LLM: Qwen/Qwen3-4B                                         │
│    • VRAM: ~8GB (35% allocation)                            │
│    • Context: 16K tokens (configurable up to 32K)           │
│    • Features: Stable text generation for RAG               │
│    • Docs: https://huggingface.co/Qwen/Qwen3-4B             │
├─────────────────────────────────────────────────────────────┤
│  Embedding: BAAI/bge-m3                                     │
│    • VRAM: ~2GB (10% allocation)                            │
│    • Dimensions: 1024                                       │
│    • Features: Multilingual (100+ languages)                │
│    • Excellent for Spanish/English document retrieval       │
│    • Docs: https://huggingface.co/BAAI/bge-m3               │
├─────────────────────────────────────────────────────────────┤
│  Total VRAM: ~10GB (45% of 24GB)                            │
│  Buffer: ~14GB for batching and concurrent requests         │
└─────────────────────────────────────────────────────────────┘

PDF Processing Pipeline:
  ✅ Text extraction → Chunking → Text embedding
  ✅ Multilingual support (Spanish/English)
  ✅ High-quality semantic search
```

**Alternative: Extended Context Configuration:**
```
┌─────────────────────────────────────────────────────────────┐
│  ALTERNATIVE: Maximum Context (larger LLM)                  │
├─────────────────────────────────────────────────────────────┤
│  LLM: Qwen/Qwen3-8B                                         │
│    • VRAM: ~16GB (65% allocation)                           │
│    • Context: 32K tokens                                    │
├─────────────────────────────────────────────────────────────┤
│  Embedding: BAAI/bge-m3                                     │
│    • VRAM: ~2GB                                             │
│    • Dimensions: 1024                                       │
├─────────────────────────────────────────────────────────────┤
│  Set: VLLM_MODEL=Qwen/Qwen3-8B                              │
│  Set: VLLM_MAX_MODEL_LEN=32768                              │
└─────────────────────────────────────────────────────────────┘
```

**vLLM Configuration:**
```bash
# Environment variables for vLLM (docker-compose.yml)
VLLM_ENABLED=true
VLLM_BASE_URL=http://vllm:8000/v1
VLLM_MODEL=Qwen/Qwen3-4B
VLLM_MAX_MODEL_LEN=16384  # 16K default, up to 32K available
HF_TOKEN=your_huggingface_token  # Required for Qwen3

# Text Embedding (BGE-M3 - Local Sentence Transformers)
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
EMBEDDING_DEVICE=cuda  # or cpu for non-GPU

# NOTE: Embeddings are loaded directly in weaviate-service
# No external embedding service needed - simpler and more reliable
# Hardware: RTX 4090 (24GB VRAM)
# Total VRAM: LLM(50%) + Local Embedding(~2GB) = ~14GB
```

**vLLM Server API Endpoints:**
The vLLM server exposes multiple APIs beyond the OpenAI-compatible interface:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI-compatible chat completions |
| `/v1/completions` | POST | OpenAI-compatible text completions |
| `/v1/models` | GET | List available models |
| `/v1/embeddings` | POST | Generate text embeddings |
| `/v1/score` | POST | Score/classify text |
| `/v1/rerank` | POST | Rerank documents |
| `/v2/rerank` | POST | Rerank v2 API |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |
| `/ping` | GET/POST | Liveness probe |
| `/pooling` | POST | Pooling operations |
| `/classify` | POST | Text classification |
| `/inference/v1/generate` | POST | Direct inference generation |

**Testing vLLM:**
```bash
# Check available models
curl http://localhost:8000/v1/models | jq

# Test chat completion
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-4B",
    "messages": [{"role": "user", "content": "Explain step by step: What is 25 * 4?"}],
    "max_tokens": 1000,
    "temperature": 0.7
  }'

# Test BGE-M3 embedding (embedding-service runs on internal port)
# From inside Docker network:
curl http://embedding-service:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "BAAI/bge-m3",
    "input": ["This is a test document about contracts"]
  }'

# Check metrics
curl http://localhost:8000/metrics
```

### Database Schema Changes
1. Modify models in `db/models.py`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review and edit migration file if needed
4. Apply migration: `alembic upgrade head`
5. Update corresponding Pydantic schemas

#### Migration Management (IMPORTANT)
To prevent multiple heads in Alembic migrations, use the provided tools:

**Check for problems:**
```bash
cd backend
python scripts/alembic_utils.py check
# or
python scripts/create_migration.py --check
```

**Create new migration safely:**
```bash
cd backend
# Manual migration
python scripts/create_migration.py -m "your migration message"

# Auto-generate from model changes
python scripts/create_migration.py -m "your migration message" --autogenerate
```

**Fix multiple heads if they exist:**
```bash
cd backend
python scripts/create_migration.py --fix-heads
# or manually
python scripts/alembic_utils.py fix
```

**Visualize migration chain:**
```bash
cd backend
python scripts/alembic_utils.py visualize
```

**Common issues and solutions:**
- **Multiple heads error**: Run `python scripts/create_migration.py --fix-heads`
- **Missing dependencies**: Check with `python scripts/alembic_utils.py check`
- **Circular dependencies**: Use `visualize` command to identify and manually fix
- **Duplicate table/column errors**: Use safe migration tools (see below)

**Best practices:**
- Always use `create_migration.py` instead of `alembic revision` directly
- Check for problems before creating new migrations
- Never manually set `down_revision = None` unless creating the initial migration
- Use descriptive migration messages for better tracking

#### Safe Migration Management (Prevents Duplicate Errors)
To prevent errors when migrations try to create tables/columns that already exist:

**Check for conflicts before migrating:**
```bash
cd backend
python scripts/alembic_safe_migrate.py --check
```

**Run migrations safely with conflict detection:**
```bash
cd backend
# Default: upgrade to head with safety checks
python scripts/alembic_safe_migrate.py

# Upgrade to specific revision
python scripts/alembic_safe_migrate.py --target abc123

# Dry run to see what would happen
python scripts/alembic_safe_migrate.py --dry-run
```

**Fix duplicate table/column issues:**
```bash
cd backend
# Generate SQL script to fix conflicts
python scripts/alembic_safe_migrate.py --fix-script

# Mark a migration as already applied (when database already has the changes)
python scripts/alembic_safe_migrate.py --mark-applied revision_id

# Sync alembic version with actual database state
python scripts/alembic_safe_migrate.py --sync
```

**Recovery from failed migrations:**
1. If migration fails with "table already exists" or "column already exists":
   ```bash
   # Check what conflicts exist
   python scripts/alembic_safe_migrate.py --check
   
   # Option 1: Generate fix SQL to remove duplicates
   python scripts/alembic_safe_migrate.py --fix-script > fix.sql
   # Review and run the SQL manually if needed
   
   # Option 2: Mark the migration as already applied
   python scripts/alembic_safe_migrate.py --mark-applied failed_revision_id
   
   # Option 3: Sync to match current database state
   python scripts/alembic_safe_migrate.py --sync
   ```

2. Always backup your database before running fix scripts

3. Use `--dry-run` flag to preview changes before applying them

### Frontend Component Development
1. Use existing patterns from `components/` directory
2. Follow shadcn/ui component structure
3. Implement proper TypeScript typing
4. Use React Context for state that crosses component boundaries
5. Integrate with API using the configured client in `lib/api-client.ts`

## Simple UI Pattern (MANDATORY)

**ALWAYS follow this simple pattern for any data loading in React components:**

### The Simple Pattern
```typescript
// 1. SHOW LOADER
setIsLoading(true)
setError(null)

try {
  // 2. CALL BACKEND
  const response = await service.getData(params)
  
  // 3. AWAIT RESPONSE
  if (response.error) {
    setError(response.error)
  } else {
    setData(response.data)
  }
} catch (err) {
  setError(err.message)
} finally {
  // 4. HIDE LOADER (always)
  setIsLoading(false)
}
```

### What NOT to do
❌ **NEVER use these patterns:**
- `useCallback` for data loading functions
- `useMemo` for simple data transformations
- Complex dependency arrays in `useEffect`
- Debounce for automatic search
- Multiple simultaneous API calls
- Intervals or timers for progress simulation
- Complex state management for simple operations

### What TO do
✅ **ALWAYS use these patterns:**
- Simple async functions
- `useEffect(() => { loadData() }, [])` for mount
- `useEffect(() => { loadData() }, [filter])` for filter changes
- Manual search with button click or Enter key
- One operation at a time
- Clear error handling with try/catch/finally
- Explicit user actions (no automatic behaviors)

### Example Implementation
```typescript
export function MyComponent() {
  const [data, setData] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const service = useService()

  // Simple data loading function
  const loadData = async () => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await service.getData()
      if (response.error) {
        setError(response.error)
      } else {
        setData(response.data)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  // Load on mount
  useEffect(() => {
    loadData()
  }, [])

  // Load when filter changes
  useEffect(() => {
    loadData()
  }, [filter])

  return (
    <div>
      {isLoading && <Loader />}
      {error && <ErrorMessage error={error} retry={loadData} />}
      {!isLoading && !error && <DataDisplay data={data} />}
    </div>
  )
}
```

### Key Principles
1. **One source of truth**: Single loading state per component
2. **Explicit actions**: User controls when data loads
3. **Simple dependencies**: Minimal useEffect dependencies
4. **Clear error handling**: Always handle errors explicitly
5. **Predictable behavior**: No background processes or automatic updates

