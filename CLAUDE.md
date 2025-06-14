# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- **Backend services**: `cd backend/docker && ./start-dev.sh` (PostgreSQL, Redis, Qdrant, microservices with live reload)
- **Backend with Langflow**: `cd backend/docker && ./start-dev-with-langflow.sh` (includes visual agent builder)
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
- `microservices/langchain-service/app` → Container's `/app/app`
- `microservices/langroid-service/app` → Container's `/app/app`
- `microservices/storage-service/app` → Container's `/app/app`
- `microservices/ollama-service/app` → Container's `/app/app`

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
- **Gotenberg Service** (port 8005): Document conversion, PDF generation, thumbnail creation

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

## Langflow Integration for Admin Agent Management

### Overview
Langflow can be integrated as an admin-only tool for visual agent creation and deployment, complementing the existing Langroid-based agent system.

### Current Agent Architecture
- **Agent Service**: REST API at `/backend/app/api/v1/agents.py`
- **Langroid Microservice**: Dedicated service for agent execution (port 8002)
- **Agent Types**: Digital Signature, Document Analyzer, RAG Assistant, Contract/Financial/Legal Analysis
- **Database Models**: agents, agent_tools, agent_conversations, agent_messages, agent_executions

### Proposed Langflow Integration

#### 1. New Microservice
- **Langflow Service** (port 8006): Visual workflow builder and manager
- Docker configuration in `backend/microservices/langflow-service/`
- Communicates with Langroid service for agent deployment

#### 2. Admin-Only API Endpoints
```python
# backend/app/api/v1/langflow_admin.py
- POST /langflow/flows - Create workflow (admin only)
- GET /langflow/flows - List workflows (admin only)
- POST /langflow/deploy/{flow_id} - Deploy as agent (admin only)
- PUT /langflow/flows/{flow_id} - Update workflow (admin only)
- POST /langflow/test/{flow_id} - Test workflow (admin only)
```

#### 3. Database Extensions
```sql
-- Langflow-specific tables
langflow_workflows:
  - id, name, description, flow_definition (JSONB)
  - created_by, is_active, deployment_status
  
langflow_deployments:
  - workflow_id, agent_id, deployed_by
  - deployment_config, status, deployed_at
```

#### 4. Security Considerations
- All Langflow endpoints require `get_current_active_superuser` dependency
- Flow definitions validated before deployment
- Sandboxed testing environment
- Audit logging for all admin actions

#### 5. Integration Benefits
- Visual workflow builder for non-technical admins
- Rapid prototyping of new agent capabilities
- Version control for agent workflows
- Hot-reload capability for updates
- A/B testing of agent behaviors

#### 6. Deployment Flow
1. Admin creates visual workflow in Langflow UI
2. Workflow saved to `langflow_workflows` table
3. Admin deploys workflow to specific tenant
4. Langflow definition converted to Langroid agent
5. Agent registered in existing agent system
6. Monitoring and rollback capabilities available

### Langflow Development Environment

#### Overview
Langflow is included as a Docker container in the development environment for visual agent design.

#### Starting Langflow
```bash
cd backend/docker
./start-dev-with-langflow.sh
```

#### Access Points
- **Langflow UI**: http://localhost:7860
- **Flows Directory**: `backend/docker/langflow/flows/`
- **Custom Components**: `backend/docker/langflow/components/`

#### Creating Agents with Langflow
1. **Open Langflow**: Navigate to http://localhost:7860
2. **Create Flow**: 
   - Use drag-and-drop interface
   - Connect nodes: LLMs, Prompts, Tools, Memory
   - Test flow in Langflow playground
3. **Configure for Nexus**:
   - Use Ollama nodes with model: `llama3.2`
   - Use QdrantVectorStore for RAG
   - Set collection names to match tenant pattern
4. **Export Flow**: 
   - Click Export → JSON
   - Save to `langflow/flows/` or copy JSON
5. **Import to System**:
   - Save JSON to `langflow/flows/` directory
   - Or use API endpoint: `/api/v1/agents/import/langflow` (Admin only)
   - Restart Langroid service to load new agents

#### Example Flows
- **RAG Document Assistant**: `langflow/flows/example-rag-agent.json`
- Custom components in `langflow/components/`

#### Best Practices
- Test flows in Langflow before importing
- Use meaningful node names and descriptions
- Include error handling nodes
- Document expected inputs/outputs
- Version control flow JSON files