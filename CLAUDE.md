# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend Development
- **Start development environment**: `cd backend/docker && docker compose up -d`
- **API server (local)**: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Initialize database**: `cd backend && python -m scripts.init_db`
- **Database migrations**: `cd backend && alembic upgrade head`
- **Run tests**: `cd backend/tests && ./run_tests.sh`
- **Run tests (with real GCS)**: `cd backend/docker && docker compose -f docker-compose.test.yml up`
- **Clean rebuild**: `./clean_and_rebuild.sh` (from project root)

### Frontend Development
- **Start development**: `cd frontend && npm run dev` (uses Turbopack)
- **Build**: `cd frontend && npm run build`
- **Lint**: `cd frontend && npm run lint`
- **Install dependencies**: `cd frontend && npm install`

### Full Stack Development
- **Backend services**: `cd backend/docker && docker compose up -d` (PostgreSQL, Redis, Qdrant, microservices)
- **Frontend**: `cd frontend && npm run dev` (runs on port 3000)
- **API Documentation**: Available at `http://localhost:8000/docs` when backend is running

## Architecture Overview

### System Design
This is a **multi-tenant intelligent document management system** with a microservices architecture:

**Backend**: FastAPI with Python 3.9+, using async/await patterns throughout
**Frontend**: Next.js 15 with App Router, TypeScript, and Clerk authentication
**Database**: PostgreSQL for relational data, Qdrant for vector embeddings
**Storage**: Google Cloud Storage for files
**AI/ML**: Multiple LLM integrations (Ollama, LangChain, Langroid)

### Key Architectural Patterns

#### Multi-Tenant Architecture
- Complete tenant isolation at database and storage levels
- Tenant-specific settings and quotas in models
- Tenant context passed through dependency injection in FastAPI endpoints
- Authentication via Clerk with tenant association

#### Microservices Design
- **Main API** (port 8000): Core business logic, authentication, document management
- **LangChain Service** (port 8001): Document processing, embeddings, basic LLM operations
- **Langroid Service** (port 8002): Advanced AI agents and multi-agent conversations
- **Storage Service** (port 8003): Google Cloud Storage operations with signed URLs
- **Ollama Service** (port 8004): Local LLM hosting and inference

#### Database Schema Highlights
- **Multi-tenant models**: All core entities have tenant_id foreign keys
- **Audit trails**: Comprehensive tracking for compliance (document views, role assignments)
- **RBAC system**: Role-based access control with fine-grained permissions
- **Agent system**: AI agents with conversation history and execution tracking
- **Digital signatures**: Complete workflow with provider integrations

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
- **Clerk**: Authentication and user management
- **Stripe**: Payment processing integration
- **Qdrant**: Vector database for semantic search
- **Redis**: Caching and session storage

#### Frontend Technologies
- **Next.js 15**: React framework with App Router
- **Clerk**: Authentication provider
- **shadcn/ui**: UI component library based on Radix UI
- **Tailwind CSS**: Utility-first styling
- **Zod**: Schema validation
- **React Hook Form**: Form management

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
- **Development mode**: Uses fake-gcs-server (mock) when `DEBUG=true` and no credentials
- **Test mode**: Uses real GCS with credentials mounted from `./credentials` directory
- **Production mode**: Uses real GCS with service account credentials
- Place GCS service account JSON file in `/credentials/nexus-document-ia-04252dae0146.json`
- Test bucket: `test-docs-eu` for isolated testing
- Development bucket: configurable via environment variables

### Code Quality Standards
- Use async/await patterns consistently in backend
- Follow TypeScript strict mode in frontend
- Implement comprehensive error handling
- Use structured logging with request correlation IDs

## Common Development Workflows

### Adding New API Endpoint
1. Create Pydantic schemas in `schemas/`
2. Add route in appropriate `api/v1/` file
3. Implement business logic in `services/`
4. Add database models if needed with migration
5. Write tests in `tests/test_api/`

### Adding New Microservice Feature
1. Identify appropriate microservice (LangChain, Langroid, Storage, Ollama)
2. Implement endpoint in microservice's `api/` directory
3. Update main API to call microservice
4. Add necessary environment variables
5. Update docker-compose configuration

### Database Schema Changes
1. Modify models in `db/models.py`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review and edit migration file if needed
4. Apply migration: `alembic upgrade head`
5. Update corresponding Pydantic schemas

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