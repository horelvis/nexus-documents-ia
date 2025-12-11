# Docker Setup for Nexus Document Backend

This directory contains Docker configurations for running the Nexus Document Backend microservices architecture.

## Quick Start

### Fast Development Mode (Recommended for active development)
```bash
./start-dev-fast.sh
```
**Best for:** Maximum development speed with instant code changes

### Standard Development Mode
```bash
./start-dev.sh
```
**Best for:** When you need to modify dependencies or Dockerfiles

### Production Mode
```bash
./start-prod.sh
```

## Development vs Production

### ⚡ Fast Development Mode (`docker-compose.dev.yml` + `start-dev-fast.sh`)

**Best for:** Maximum development speed with instant code changes

**Features:**
- ✅ **Instant code changes** - No rebuilds, just save and refresh
- ✅ **Volume mounting** - All source code mounted as volumes
- ✅ **Live reloading** - uvicorn `--reload` flag on all services
- ✅ **Smart building** - Only rebuilds when dependencies change
- ✅ **Full debugging** - Source maps and error traces
- ✅ **Hot module replacement** - Changes reflect immediately

**Volume Mounts:**
```
../app                          → /app/app          (main API)
../microservices/*/app          → /app/app          (all microservices)
../credentials                  → /app/credentials  (GCS keys)
../scripts                      → /app/scripts      (utility scripts)
```

### 🔧 Standard Development Mode (`docker-compose.yml` + `start-dev.sh`)

**Best for:** When you need to modify Dockerfiles or dependencies

**Features:**
- ✅ **Traditional Docker** - Rebuilds on every startup
- ✅ **Clean builds** - Ensures consistency
- ✅ **Dependency updates** - Picks up requirements.txt changes
- ✅ **Dockerfile changes** - Applies configuration updates

**When to use:**
- After modifying `requirements.txt`
- After changing `Dockerfile`
- When you want guaranteed clean state
- For CI/CD pipeline testing

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

### Microservices

| Service | Port | Description |
|---------|------|-------------|
| Main API | 8000 | FastAPI main application |
| Storage Service | 8003 | Google Cloud Storage operations |
| Weaviate Service | 8007 | Emma AI (Agent Framework + vLLM + RAG Pipeline + Weaviate) |
| Elasticsearch Service | 8008 | Full-text search & document indexing |
| LangExtract Service | 8010 | Document language extraction |
| TextExtract Service | 8011 | OCR & text extraction |
| Template Editor Service | 8012 | Document template management |
| Background Worker | 8100 | Celery async task worker |

### Infrastructure

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5432 | Main relational database |
| Redis | 6379 | Cache, sessions & Celery broker |
| Weaviate | 8080 | Vector database for semantic search |
| Elasticsearch | 9200 | Full-text search engine |
| vLLM Server | 8001 | High-throughput GPU inference (Qwen2.5-7B-Instruct) |
| Ollama Server | 11434 | Legacy local LLM server (fallback) |
| Gotenberg | 3000 | Document conversion to PDF |

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

### Fast Development Workflow (Recommended)
```bash
# Start fast development environment
./start-dev-fast.sh

# View logs
docker compose -f docker-compose.dev.yml logs -f

# View specific service logs
docker compose -f docker-compose.dev.yml logs -f api

# Stop services
docker compose -f docker-compose.dev.yml down

# Restart a single service
docker compose -f docker-compose.dev.yml restart api
```

### Standard Development Workflow
```bash
# Start standard development environment
./start-dev.sh

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f api

# Stop services
docker compose down

# Restart a single service
docker compose restart api
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

## Gotenberg Document Conversion

### Overview
Gotenberg is an open-source document conversion service that provides universal PDF generation from various document formats.

### Supported Formats
- **Office Documents**: `.docx`, `.doc`, `.xlsx`, `.xls`, `.pptx`, `.ppt`, `.odt`, `.ods`, `.odp`
- **Text Formats**: `.txt`, `.md`, `.html`, `.htm`
- **Already PDF**: `.pdf` (thumbnail generation)
- **Images**: `.jpg`, `.png`, `.gif`, `.bmp`, `.tiff`

### API Endpoints
```bash
# Generate document preview
GET /api/v1/documents/{doc_id}/preview

# Check existing preview
GET /api/v1/documents/{doc_id}/preview/info

# Force regenerate preview
GET /api/v1/documents/{doc_id}/preview?force_regenerate=true
```

### Preview Response Format
```json
{
  "type": "office_preview",
  "conversion_method": "gotenberg",
  "pdf_available": true,
  "pdf_storage_path": "previews/tenant-id/doc-id/preview.pdf",
  "thumbnails": ["path/to/thumb1.jpg", "path/to/thumb2.jpg"],
  "original_format": ".docx",
  "cached": true,
  "generated_at": 1703123456,
  "file_size": 2048576
}
```

### Features
- ✅ **High-quality PDF conversion** using LibreOffice and Chromium
- ✅ **Thumbnail generation** from PDF pages
- ✅ **Caching system** for faster subsequent requests
- ✅ **Storage integration** for preview persistence
- ✅ **Fallback support** when Gotenberg is unavailable
- ✅ **Custom CSS** for HTML/Markdown conversion

### Health Check
```bash
curl http://localhost:3001/health
```

## Performance Notes

- **Development mode**: Slight performance overhead due to volume mounting
- **Production mode**: Optimized performance, smaller images
- **Memory usage**: ~4-6GB RAM for full stack (including Gotenberg)
- **GPU support**: Ollama service includes NVIDIA GPU support
- **Gotenberg resources**: ~512MB-1GB RAM, varies by document complexity