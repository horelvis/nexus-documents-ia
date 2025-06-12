# Docker Setup for Nexus Document Backend

This directory contains Docker configurations for running the Nexus Document Backend microservices architecture.

## Quick Start

### Development Mode (Recommended)
```bash
./start-dev.sh
```

### Production Mode
```bash
./start-prod.sh
```

## Development vs Production

### 🔧 Development Mode (`docker-compose.dev.yml`)

**Best for:** Active development, debugging, testing changes

**Features:**
- ✅ **Live code reloading** - Python files mounted as volumes
- ✅ **No rebuilds needed** - Only when requirements change
- ✅ **Auto-reload enabled** - uvicorn `--reload` flag
- ✅ **Faster iteration** - Immediate code changes
- ✅ **Development debugging** - Full source access

**Files:**
- `docker-compose.dev.yml` - Development configuration
- `Dockerfile.dev` - Development images for each microservice
- `start-dev.sh` - Development startup script

**Volume Mounts:**
```
microservices/langchain-service/app  → /app/app  (live reload)
microservices/langroid-service/app   → /app/app  (live reload) 
microservices/storage-service/app    → /app/app  (live reload)
microservices/ollama-service/app     → /app/app  (live reload)
```

### 🚀 Production Mode (`docker-compose.yml`)

**Best for:** Production deployment, performance testing

**Features:**
- ✅ **Optimized images** - Multi-stage builds
- ✅ **Smaller size** - Build deps removed
- ✅ **Better security** - Code copied, not mounted
- ✅ **Production performance** - No volume overhead

**Files:**
- `docker-compose.yml` - Production configuration  
- `Dockerfile` - Production images for each microservice
- `start-prod.sh` - Production startup script

## Services Overview

| Service | Dev Port | Prod Port | Description |
|---------|----------|-----------|-------------|
| Main API | 8000 | 8000 | FastAPI main application |
| LangChain | 8001 | 8001 | Document processing & embeddings |
| Langroid | 8002 | 8002 | Advanced AI agents |
| Storage | 8003 | 8003 | Google Cloud Storage service |
| Ollama API | 8004 | 8004 | LLM API wrapper |
| Ollama Server | 11434 | 11434 | Ollama LLM server |
| PostgreSQL | 5432 | 5432 | Main database |
| Redis | 6379 | 6379 | Cache & sessions |
| Qdrant | 6333 | 6333 | Vector database |

## Environment Setup

1. **Create `.env` file** (required - in backend root):
```bash
# From backend/docker directory:
cp ../.env.example ../.env
# Edit ../.env with your settings

# Or from backend root directory:
cp .env.example .env
# Edit .env with your settings
```

2. **Credentials setup**:
```bash
# Place GCS credentials in:
../credentials/nexus-document-ia-04252dae0146.json
```

## Usage Commands

### Development Workflow
```bash
# Start development environment
./start-dev.sh

# View logs
docker compose -f docker-compose.dev.yml logs -f

# View specific service logs
docker compose -f docker-compose.dev.yml logs -f langchain-service

# Stop services
docker compose -f docker-compose.dev.yml down

# Restart a single service
docker compose -f docker-compose.dev.yml restart langchain-service
```

### Production Workflow  
```bash
# Start production environment
./start-prod.sh

# View logs
docker compose logs -f

# Stop services
docker compose down

# Rebuild all images
docker compose build --no-cache
```

### Debugging Commands
```bash
# Execute shell in container
docker compose exec langchain-service bash

# View container status
docker compose ps

# View resource usage
docker stats

# Clean up
docker compose down --volumes --remove-orphans
docker system prune -f
```

## Development Benefits

### Before (Traditional Docker)
- ❌ Full rebuild on every code change
- ❌ 2-5 minutes rebuild time
- ❌ Slow development iteration
- ❌ Container restart required

### After (Volume Mounting)
- ✅ Instant code changes
- ✅ No rebuilds needed
- ✅ Fast development iteration  
- ✅ Auto-reload on save

## Troubleshooting

### Common Issues

**Port conflicts:**
```bash
# Check what's using ports
lsof -i :8000
lsof -i :8001

# Kill processes if needed
sudo kill -9 <PID>
```

**Permission issues:**
```bash
# Fix volume permissions
sudo chown -R $USER:$USER ../microservices/
```

**Dependency issues:**
```bash
# Rebuild images when requirements.txt changes
docker compose -f docker-compose.dev.yml build --no-cache
```

**Database issues:**
```bash
# Reset database
docker compose down --volumes
docker compose up -d db
# Run migrations again from backend root:
cd .. && python -m scripts.init_db
```

**Environment file issues:**
```bash
# Check if .env exists in backend root
ls -la ../.env

# Create from example if missing
cp ../.env.example ../.env
```

### Log Monitoring
```bash
# Monitor all services
docker compose -f docker-compose.dev.yml logs -f

# Monitor specific service
docker compose -f docker-compose.dev.yml logs -f langchain-service

# Monitor with timestamps
docker compose -f docker-compose.dev.yml logs -f -t
```

## Performance Notes

- **Development mode**: Slight performance overhead due to volume mounting
- **Production mode**: Optimized performance, smaller images
- **Memory usage**: ~4-6GB RAM for full stack
- **GPU support**: Ollama service includes NVIDIA GPU support