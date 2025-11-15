# Nexus Document Management System

A comprehensive multi-tenant intelligent document management system with advanced AI capabilities, built on a microservices architecture for scalability and reliability.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Development](#development)
- [API Documentation](#api-documentation)
- [Microservices](#microservices)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Overview

Nexus Document Management System is an enterprise-grade solution for intelligent document processing, storage, and retrieval. It combines traditional document management capabilities with cutting-edge AI features including semantic search, intelligent agents, and automated document processing pipelines.

### Core Capabilities

- **Multi-tenant Architecture**: Complete data isolation for organizations with shared infrastructure
- **AI-Powered Processing**: Automatic document analysis, summarization, and intelligent tagging
- **Semantic Search**: Vector-based search for finding contextually relevant documents
- **Intelligent Agents**: AI agents for document analysis, contract review, and digital signatures
- **Scalable Storage**: Cloud-based storage with automatic organization and versioning
- **Real-time Collaboration**: Document sharing, commenting, and workflow management

## Key Features

### 1. **Multi-Tenant Architecture**
- Complete tenant isolation at database and storage levels
- Per-tenant configuration and quotas
- Automatic bucket creation for new organizations
- User invitation system for collaborative workspaces

### 2. **Document Processing Pipeline**
- Support for multiple formats: PDF, DOCX, TXT, CSV, Excel, Markdown, Images
- Automatic text extraction and OCR for scanned documents
- Intelligent chunking for large documents
- Metadata extraction and enrichment
- Thumbnail generation for visual preview

### 3. **AI and Machine Learning**
- **Semantic Search**: Find documents by meaning, not just keywords
- **Document Summarization**: AI-generated summaries for quick insights
- **Smart Tagging**: Automatic tag suggestions based on content
- **Question Answering**: Ask questions about your documents
- **Content Classification**: Automatic categorization of documents

### 4. **Agent System**
- **Digital Signature Agent**: Automated signature workflow management
- **Document Analyzer**: Deep analysis of document content and structure
- **RAG Assistant**: Retrieval-Augmented Generation for accurate answers
- **Contract Analysis**: Legal document review and risk assessment
- **Financial Analysis**: Extract and analyze financial data
- **Custom Agents**: Extensible framework for domain-specific agents

### 5. **Subscription and Billing (v2)**
- **Stripe Integration**: Secure payment processing
- **Flexible Plans**: Starter, Professional, Enterprise tiers
- **Usage Tracking**: Monitor storage, API calls, and AI usage
- **Automatic Billing**: Subscription management and invoicing
- **Feature Gates**: Plan-based feature access control

### 6. **Security and Compliance**
- **JWT-based Authentication**: Secure token-based auth
- **Role-Based Access Control**: Fine-grained permissions
- **Audit Trails**: Complete activity logging
- **Data Encryption**: At-rest and in-transit encryption
- **GDPR Compliance**: Data privacy and right to deletion

### 7. **Developer Experience**
- **RESTful API**: Clean, consistent API design
- **OpenAPI Documentation**: Interactive API documentation
- **Docker Development**: One-command development setup
- **Hot Reload**: Live code updates in development
- **Comprehensive Testing**: Unit, integration, and E2E tests

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NEXUS DOCUMENT BACKEND ARCHITECTURE              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT APPLICATIONS                         │
├─────────────────┬─────────────────┬─────────────────┬──────────────┤
│   Next.js Web   │  Mobile Apps    │  Admin Portal   │  API Clients │
└─────────────────┴─────────────────┴─────────────────┴──────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FASTAPI REST API GATEWAY                         │
├─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬────────┤
│  Auth   │Documents│ Search  │ Agents  │  Chat   │Signature│ Admin  │
│ Tenants │Subscrip │Storage  │Analytics│Workflows│  Audit  │Reports │
└─────────┴─────────┴─────────┴─────────┴─────────┴─────────┴────────┘
              │                           │
              ▼                           ▼
┌──────────────────────────┐    ┌─────────────────────────────────────┐
│    CORE SERVICES         │    │      BUSINESS LOGIC SERVICES       │
├─────────┬────────┬───────┤    ├────────────┬────────────┬──────────┤
│Security │Config  │Logging│    │Auth Service│Doc Service │Agent Srv │
│RBAC     │Cache   │Metrics│    ├────────────┼────────────┼──────────┤
└─────────┴────────┴───────┘    │Search Serv │Signature S │Storage S │
                                ├────────────┼────────────┼──────────┤
                                │Subscription│Vector Serv │Embedding │
                                └────────────┴────────────┴──────────┘
                                              │           │
                      ┌───────────────────────┼───────────┼────────────┐
                      ▼                       ▼           ▼            ▼
┌─────────────────────────┐  ┌──────────────────────────────┐  ┌──────────────────┐
│     DATA LAYER          │  │      MICROSERVICES          │  │ EXTERNAL SERVICES│
├──────────┬──────────────┤  ├───────────┬────────────────┤  ├─────────┬────────┤
│PostgreSQL│Redis Cache    │  │CAG Svc    │LangExtract Svc │  │Google   │Stripe  │
│Weaviate  │Session Store  │  │TextExtract│Temporalio Svc  │  │Cloud    │Payment │
├──────────┼──────────────┤  ├───────────┼────────────────┤  │Storage  │API     │
│Qdrant    │Alembic       │  │WeaviateSvc│Template Editor │  ├─────────┼────────┤
│Vector DB │Migrations    │  │Storage Svc│Elasticsearch   │  │Clerk    │Email   │
│          │              │  ├───────────┼────────────────┤  │Auth     │Alerts  │
│          │              │  │Gotenberg  │Ollama Host     │  └─────────┴────────┘
└──────────┴──────────────┘  └───────────┴────────────────┘

MICROSERVICES ARCHITECTURE:
╔══════════════════════════════════════════════════════════════════════╗
║ • CAG Service (8008): Contenido + agentes para análisis avanzado     ║
║ • LangExtract Service (8009): Extracción automática de entidades     ║
║ • TextExtract Service (8012): Extracción determinística/OCR          ║
║ • Weaviate Service (8007): Proxy vectorial multi-tenant             ║
║ • Temporalio Service (8010): Workflows durables + Process Library    ║
║ • Template Editor Service (8011): Gestión de plantillas colaborativa ║
║ • Storage Service (8003): Operaciones GCS y signed URLs              ║
║ • Elasticsearch Service (8005): Búsqueda híbrida y analytics         ║
║ • Main API (8000): Lógica de negocio, auth y orquestación            ║
╚══════════════════════════════════════════════════════════════════════╝

KEY ARCHITECTURAL PATTERNS:
╔══════════════════════════════════════════════════════════════════════╗
║ • Event-driven processing with async/await throughout               ║
║ • Microservices communicate via REST with unified API key auth     ║
║ • Database-per-service pattern for microservice independence        ║
║ • CQRS for read/write optimization in document operations          ║
║ • Circuit breakers for external service resilience                 ║
║ • Distributed caching with Redis for performance                   ║
╚══════════════════════════════════════════════════════════════════════╝
```

### Multi-Tenant Data Flow

```
User Request → Clerk Auth → Tenant Resolution → Data Isolation → Response

1. User authenticated via Clerk
2. Tenant ID extracted from user profile
3. All queries filtered by tenant_id
4. Storage buckets isolated per tenant
5. Vector collections namespaced by tenant
```

## Technology Stack

### Backend Technologies
- **FastAPI** (Python 3.9+): High-performance async web framework
- **SQLAlchemy 2.0**: Modern ORM with async support
- **Alembic**: Database migration management
- **Pydantic**: Data validation and serialization
- **asyncio**: Async/await patterns throughout

### Data Storage
- **PostgreSQL**: Primary relational database
- **Redis**: Caching and session management
- **Qdrant**: Vector database for embeddings
- **Google Cloud Storage**: Document storage

### AI/ML Stack
- **Emma AI + CAG Service**: Orquestación multi-agente y análisis avanzado
- **LangExtract & TextExtract**: Extracción de entidades (LLM) + parsing determinístico
- **Weaviate (+ Service Proxy)**: Búsqueda vectorial multi-tenant y guarda de similitud
- **Ollama / OpenAI / Anthropic**: Modelos LLM locales y cloud
- **Sentence Transformers**: Embeddings especializados por dominio

### Infrastructure
- **Docker**: Container orchestration
- **Docker Compose**: Multi-service development
- **Nginx**: Reverse proxy and load balancing
- **Prometheus**: Metrics collection
- **Grafana**: Monitoring dashboards

### External Services
- **Clerk**: Authentication and user management
- **Stripe**: Payment processing
- **Google Workspace**: Email services
- **Sentry**: Error tracking

## Project Structure

```
nexus-document-backend/
│
├── backend/
│   ├── app/                       # Main application code
│   │   ├── api/v1/               # REST API endpoints
│   │   │   ├── agents.py         # AI agent endpoints
│   │   │   ├── auth.py           # Authentication
│   │   │   ├── documents.py      # Document operations
│   │   │   ├── search.py         # Search functionality
│   │   │   ├── signatures.py     # Digital signatures
│   │   │   ├── subscriptions_v2.py # Stripe subscriptions
│   │   │   └── tenants.py        # Multi-tenancy
│   │   │
│   │   ├── core/                 # Core utilities
│   │   │   ├── config.py         # Configuration management
│   │   │   ├── security.py       # Security utilities
│   │   │   └── logging.py        # Structured logging
│   │   │
│   │   ├── db/                   # Database layer
│   │   │   ├── database.py       # Database configuration
│   │   │   ├── models.py         # SQLAlchemy models
│   │   │   └── session.py        # Session management
│   │   │
│   │   ├── schemas/              # Pydantic models
│   │   │   ├── agent.py          # Agent schemas
│   │   │   ├── document.py       # Document schemas
│   │   │   ├── subscription.py   # Subscription schemas
│   │   │   └── tenant.py         # Tenant schemas
│   │   │
│   │   ├── services/             # Business logic
│   │   │   ├── agent_service.py  # Agent operations
│   │   │   ├── async_storage_service.py # Async GCS
│   │   │   ├── document_service.py # Document processing
│   │   │   ├── subscription_service_v2.py # Stripe billing
│   │   │   └── vector_service.py # Vector operations
│   │   │
│   │   └── main.py              # FastAPI application
│   │
│   ├── microservices/           # Microservice applications
│   │   ├── cag-service/                 # Content Analysis & Generative agents
│   │   ├── langextract-service/         # Entity extraction pipeline
│   │   ├── textextract-service/         # Deterministic text/OCR extraction
│   │   ├── weaviate-service/            # Vector proxy + multi-tenant guards
│   │   ├── elasticsearch-service/       # Hybrid keyword/vector bridge
│   │   ├── storage-service/             # Async storage + signed URLs
│   │   ├── template-editor-service/     # Workflow template editor APIs
│   │   ├── temporalio-service/          # Durable workflow orchestrator
│   │   └── shared/                      # Shared utilities
│   │
│   ├── docker/                  # Docker configuration
│   │   ├── docker-compose.yml   # Development setup
│   │   ├── docker-compose.prod.yml # Production setup
│   │   ├── docker-compose.test.yml # Test environment
│   │   ├── start-dev.sh         # Dev startup script
│   │   └── start-prod.sh        # Prod startup script
│   │
│   ├── alembic/                 # Database migrations
│   │   └── versions/            # Migration files
│   │
│   ├── scripts/                 # Utility scripts
│   │   ├── init_db.py          # Database initialization
│   │   ├── create_migration.py  # Safe migration creation
│   │   └── alembic_utils.py    # Migration utilities
│   │
│   └── tests/                   # Test suite
│       ├── test_api/            # API tests
│       ├── test_services/       # Service tests
│       └── run_tests.sh         # Test runner
│
├── frontend/                    # Next.js frontend
│   ├── src/
│   │   ├── app/                # App router pages
│   │   ├── components/         # React components
│   │   └── lib/               # Utilities and services
│   │
│   └── package.json           # Dependencies
│
└── docs/                      # Documentation
    ├── api/                   # API documentation
    ├── architecture/          # Architecture diagrams
    └── deployment/            # Deployment guides
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.9+ (for local development)
- Node.js 18+ (for frontend development)
- Google Cloud account (for storage)
- Stripe account (for payments)
- Clerk account (for authentication)

### Quick Start with Docker

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/nexus-document-backend.git
   cd nexus-document-backend
   ```

2. **Set up environment variables**
   ```bash
   cd backend
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Configure Google Cloud Storage**
   ```bash
   # Place your GCS service account JSON in:
   mkdir -p backend/credentials
   cp path/to/your-service-account.json backend/credentials/
   ```

4. **Start the development environment**
   ```bash
   cd backend/docker
   ./start-dev.sh
   ```

   This will start:
   - PostgreSQL database
   - Redis cache
   - Qdrant vector database
   - All microservices with hot reload
   - Main API on http://localhost:8000

5. **Initialize the database**
   ```bash
   cd backend
   docker compose exec api python -m scripts.init_db
   ```

6. **Access the application**
   - API Documentation: http://localhost:8000/docs
   - Main API: http://localhost:8000
   - CAG Service: http://localhost:8008
   - LangExtract Service: http://localhost:8009
   - Temporalio Service: http://localhost:8010

### Manual Setup (Without Docker)

1. **Create Python virtual environment**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up services locally**
   - Install and run PostgreSQL
   - Install and run Redis
   - Install and run Qdrant

4. **Run database migrations safely**
   ```bash
   # Check for potential conflicts
   python scripts/alembic_safe_migrate.py --check

   # Apply migrations with safety checks
   python scripts/alembic_safe_migrate.py
   ```

5. **Start the API server**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Development

### Development Workflow

#### 1. **Backend Development**

**Start development environment:**
```bash
cd backend/docker
./start-dev.sh  # Includes all services with hot reload
```

**Key features of dev mode:**
- Live code reloading (no rebuilds needed)
- Volume mounting for instant updates
- Debug logging enabled
- Development database with sample data

**Common development tasks:**
```bash
# Create a new API endpoint
# 1. Add schema in app/schemas/
# 2. Add endpoint in app/api/v1/
# 3. Add service logic in app/services/
# 4. Add tests in tests/

# Run specific microservice
docker compose up cag-service

# View logs
docker compose logs -f api
docker compose logs -f cag-service

# Access database
docker compose exec db psql -U postgres -d nexus_docs
```

#### 2. **Database Development**

**Create a new migration:**
```bash
cd backend
# Safe migration creation (prevents conflicts)
python scripts/create_migration.py -m "add new feature"

# With model changes auto-detection
python scripts/create_migration.py -m "add new feature" --autogenerate
```

**Check migration health:**
```bash
python scripts/alembic_utils.py check
python scripts/alembic_utils.py visualize
```

**Apply migrations safely:**
```bash
# Check for conflicts first
python scripts/alembic_safe_migrate.py --check

# Apply migrations with safety checks
python scripts/alembic_safe_migrate.py
```

#### 3. **Frontend Development**

```bash
cd frontend
nvm use 18  # Ensure correct Node version
npm install
npm run dev  # Starts on http://localhost:3000
```

### Code Style and Standards

- **Python**: Follow PEP 8, use Black formatter
- **TypeScript**: Use ESLint and Prettier
- **Async First**: Use async/await patterns
- **Type Safety**: Full type annotations
- **Error Handling**: Comprehensive try/catch blocks
- **Logging**: Structured JSON logging

### Environment Variables

Key environment variables to configure:

```env
# API Configuration
API_V1_STR=/api/v1
SECRET_KEY=your-secret-key
BACKEND_CORS_ORIGINS=["http://localhost:3000"]

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/nexus_docs

# Redis
REDIS_URL=redis://localhost:6379

# Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Google Cloud Storage
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json
GCS_BUCKET_PREFIX=nexus-docs

# Microservices
MICROSERVICE_API_KEY=your-unified-api-key
CAG_SERVICE_URL=http://cag-service:8000
LANGEXTRACT_SERVICE_URL=http://langextract-service:8000
TEXT_EXTRACTION_SERVICE_URL=http://textextract-service:8000
STORAGE_SERVICE_URL=http://storage-service:8000
WEAVIATE_SERVICE_URL=http://weaviate-service:8000
ELASTICSEARCH_SERVICE_URL=http://elasticsearch-service:8000
TEMPORALIO_SERVICE_URL=http://temporalio-service:8000
TEMPLATE_EDITOR_SERVICE_URL=http://template-editor-service:8000

# External Services
CLERK_SECRET_KEY=your-clerk-secret
STRIPE_SECRET_KEY=your-stripe-secret
STRIPE_WEBHOOK_SECRET=your-webhook-secret

# AI/ML
OPENAI_API_KEY=your-openai-key
OLLAMA_BASE_URL=http://ollama-service:11434
```

## API Documentation

### RESTful Endpoints

The API follows RESTful conventions with versioning:

#### Authentication (`/api/v1/auth`)
- `POST /login` - User login
- `POST /register` - User registration
- `GET /me` - Get current user
- `POST /logout` - User logout

#### Documents (`/api/v1/documents`)
- `GET /` - List documents (paginated)
- `POST /` - Upload document
- `GET /{id}` - Get document details
- `PUT /{id}` - Update document
- `DELETE /{id}` - Delete document
- `GET /{id}/download` - Get download URL
- `POST /{id}/share` - Share document
- `GET /{id}/summary` - Get AI summary

#### Search (`/api/v1/search`)
- `GET /` - Semantic search
- `POST /ask` - Ask questions about documents
- `GET /similar/{id}` - Find similar documents

#### Agents (`/api/v1/agents`)
- `GET /` - List available agents
- `POST /{agent_id}/execute` - Execute agent
- `GET /conversations` - List conversations
- `GET /conversations/{id}` - Get conversation

#### Subscriptions (`/api/v1/subscriptions`)
- `GET /plans` - List available plans
- `POST /subscribe` - Create subscription
- `GET /current` - Get current subscription
- `POST /cancel` - Cancel subscription
- `GET /usage` - Get usage statistics

### API Authentication

All API requests require authentication via JWT tokens:

```bash
# Get token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'

# Use token
curl http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Rate Limiting

API rate limits by subscription tier:
- **Starter**: 100 requests/minute
- **Professional**: 1000 requests/minute
- **Enterprise**: Unlimited

## Microservices

### 1. CAG Service (Port 8008)
- **Contenido + agentes**: Ejecuta cadenas de razonamiento y genera resúmenes/insights avanzados.
- **Embeddings inteligentes**: Coordina llamadas a Ollama/OpenAI y publica resultados en Weaviate.
- **API principal**: `POST /analyze`, `POST /agents/run`, `GET /health`.

### 2. LangExtract Service (Port 8009)
- **Extracción automática** de entidades en cada upload (personas, empresas, importes, fechas).
- **LLM specialization** con prompts médicos/legales según tenant.
- **Endpoints**: `POST /extract`, `POST /bulk`, `GET /health`.

### 3. TextExtract Service (Port 8012)
- **Parsing determinístico/OCR** para PDFs complejos y anexos escaneados.
- **Normalización**: limpia tablas, firmas y campos estructurados antes de LangExtract.
- **Endpoints**: `POST /parse`, `POST /ocr`, `GET /health`.

### 4. Storage Service (Port 8003)
- **Operaciones GCS** asíncronas (upload, delete, versioning) con signed URLs.
- **Metadata hooks**: emite eventos para CAG/LangExtract tras completar el guardado.
- **Endpoints**: `POST /upload`, `GET /download/{id}`, `DELETE /files/{id}`.

### 5. Weaviate Service (Port 8007)
- **Proxy multi-tenant** frente a Weaviate core (auth, cuotas, métricas).
- **Operaciones**: creación de collections, búsqueda híbrida y filtros por tenant.
- **Endpoints**: `POST /vectors/upsert`, `POST /search`, `GET /stats`.

### 6. Elasticsearch Service (Port 8005)
- **Búsqueda híbrida** (keyword + vector), filtros avanzados y analytics.
- **Fallback**: entrega resultados cuando no hay embeddings o se requiere BM25 puro.
- **Endpoints**: `POST /search`, `POST /reindex`, `GET /health`.

### 7. Temporalio Service (Port 8010)
- **Orquestación durable** para workflows (contract renewal, onboarding, etc.).
- **Signals & Queries**: controla ejecuciones en vivo y expone visibilidad agregada.
- **Endpoints**: `POST /workflows/start`, `GET /workflows/status/{id}`, `POST /workflows/cancel`.

### 8. Template Editor Service (Port 8011)
- **Process Library**: administra plantillas, formularios dinámicos e inputs validados.
- **Colaboración**: controla versiones, permisos y publicación por tenant.
- **Endpoints**: `GET /templates`, `POST /templates`, `PATCH /templates/{id}`.

### 9. Gotenberg Service (Port 3000 interno)
- **Conversión de documentos** (HTML/Office → PDF), generación de thumbnails y snapshots para el visor.
- **Pipeline legal + preview**: Storage lo invoca tras cada upload para producir versiones firmables y el preview incrustado en la UI.
- **Endpoints**: `POST /convert/html`, `POST /convert/office`, `POST /merge`.

### 10. Ollama Host (Port 11434)
- **LLM local** para inferencias privadas (Llama 3.x, GPT-OSS, Mistral).
- **Streaming** y soporte para modelos embebidos utilizados por CAG/LangExtract.
- **Endpoints**: `/api/generate`, `/api/embeddings`, `/api/tags`.

### Microservice Communication

All microservices use unified API key authentication:

```python
# Example: Calling storage service from main API
headers = {"X-API-Key": settings.MICROSERVICE_API_KEY}
response = await client.post(
    f"{STORAGE_SERVICE_URL}/upload",
    headers=headers,
    files={"file": file}
)
```

## Testing

### Running Tests

**Full test suite with real services:**
```bash
cd backend/docker
docker compose -f docker-compose.test.yml up
```

**Quick unit tests:**
```bash
cd backend/tests
./run_tests.sh
```

**Test specific module:**
```bash
pytest tests/test_api/test_documents.py -v
```

### Test Coverage

Generate coverage report:
```bash
cd backend/tests
./run_tests.sh --coverage
# Report available at: coverage_report/index.html
```

### Test Categories

1. **Unit Tests**: Service and utility functions
2. **Integration Tests**: API endpoints with database
3. **E2E Tests**: Full workflow testing
4. **Performance Tests**: Load and stress testing

## Deployment

### Production Deployment with Docker

1. **Build production images:**
   ```bash
   cd backend/docker
   ./build-prod.sh
   ```

2. **Deploy with Docker Compose:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

3. **Configure reverse proxy (nginx):**
   ```nginx
   server {
       listen 80;
       server_name api.yourdomain.com;
       
       location / {
           proxy_pass http://api:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Kubernetes Deployment

Helm charts available in `/deploy/kubernetes/`:

```bash
helm install nexus-docs ./deploy/kubernetes/nexus-docs \
  --values ./deploy/kubernetes/values.prod.yaml
```

### Environment-Specific Configuration

- **Development**: Hot reload, debug logging, local services
- **Staging**: Production-like with test data
- **Production**: Optimized builds, monitoring, backups

### Monitoring and Observability

1. **Metrics**: Prometheus + Grafana
2. **Logging**: Structured JSON logs to stdout
3. **Tracing**: OpenTelemetry integration
4. **Error Tracking**: Sentry integration

## Troubleshooting

### Common Issues

#### 1. **Docker Issues**

**Permission denied:**
```bash
sudo usermod -aG docker $USER
# Log out and back in
```

**Port already in use:**
```bash
# Find process using port
lsof -i :8000
# Or change port in docker-compose.yml
```

**Out of disk space:**
```bash
docker system prune -a --volumes
```

#### 2. **Database Issues**

**Migration conflicts:**
```bash
cd backend
python scripts/create_migration.py --fix-heads
python scripts/alembic_safe_migrate.py --check
```

**Connection errors:**
```bash
# Check PostgreSQL is running
docker compose ps db
# Check connection string
echo $DATABASE_URL
```

#### 3. **Storage Issues**

**GCS authentication:**
```bash
# Verify credentials file exists
ls -la backend/credentials/
# Check environment variable
echo $GOOGLE_APPLICATION_CREDENTIALS
```

**Bucket creation fails:**
- Check GCS permissions
- Verify project ID in credentials
- Check bucket naming (lowercase, unique)

#### 4. **Microservice Issues**

**Service not responding:**
```bash
# Check service health
curl http://localhost:8001/health
# View logs
docker compose logs langchain-service
# Restart service
docker compose restart langchain-service
```

### Debug Mode

Enable debug logging:
```python
# In .env
LOG_LEVEL=DEBUG
DEBUG=True
```

View detailed logs:
```bash
docker compose logs -f api | jq '.'
```

### Performance Optimization

1. **Database**: Add indexes for frequent queries
2. **Caching**: Use Redis for repeated operations
3. **Async Operations**: Ensure all I/O is async
4. **Connection Pooling**: Configure pool sizes
5. **CDN**: Use for static document serving

## Contributing

We welcome contributions! Please follow these guidelines:

### Development Process

1. **Fork the repository**
2. **Create feature branch:**
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make changes with tests**
4. **Run test suite:**
   ```bash
   ./tests/run_tests.sh
   ```
5. **Commit changes:**
   ```bash
   git commit -m "Add amazing feature"
   ```
6. **Push branch:**
   ```bash
   git push origin feature/amazing-feature
   ```
7. **Open Pull Request**

### Code Standards

- Write comprehensive tests
- Update documentation
- Follow existing patterns
- Add type hints
- Use meaningful commit messages

### Pull Request Process

1. Update README.md with details of changes
2. Update API documentation if needed
3. Ensure all tests pass
4. Request review from maintainers
5. Merge after approval

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: See `/docs` directory
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Email**: support@nexusdocs.com

## Acknowledgments

- FastAPI for the excellent framework
- The Python async community
- All our contributors and users

---

Built with ❤️ by the Nexus Team
