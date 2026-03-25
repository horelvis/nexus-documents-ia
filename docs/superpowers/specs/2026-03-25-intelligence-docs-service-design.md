# Intelligence Docs Service — Design Spec

**Date**: 2026-03-25
**Status**: Draft
**Replaces**: `textextract-service`, `langextract-service`, embedding code in `weaviate-service`

## Problem

The current document processing pipeline is fragmented across 3+ services and multiple embedding codepaths:

- **textextract-service**: Text extraction via Tika/Docling (separate Docker service)
- **langextract-service**: Entity extraction via vLLM NER + regex (separate Docker service, currently broken — `Invalid provider 'vllm'`)
- **weaviate-service**: Hosts embedding model (BGE-M3 sentence-transformers) in-process, plus broken TEI path in `public_knowledge_service`, disabled multimodal embedding, and orphaned CAG embedding code
- **No online provider support**: Everything is local-only. No way to use Google Embedding, Mistral OCR, etc.

This results in:
- 3 HTTP round-trips per document during indexing
- Silent embedding failures (chunks indexed without vectors)
- No provider abstraction (switching models requires code changes)
- GPU memory contention (BGE-M3 loaded inside weaviate-service alongside Weaviate operations)

## Solution

A single unified microservice — `intelligence-docs-service` — that consolidates extraction, embedding, and entity recognition behind a provider registry with ordered fallback. On-premise providers are always prioritized by default; cloud providers are opt-in.

## Design Principles

1. **On-premise first**: Works 100% offline by default. Cloud providers are opt-in via env vars.
2. **Single model active**: One embedding model per deployment. Changing model requires re-indexing (no mixed-dimension vectors).
3. **Provider registry with fallback**: Ordered list of providers per capability. First available wins.
4. **One HTTP call for indexing**: The `/process` endpoint handles extract + chunk + embed + NER in a single round-trip.

## Architecture

```
intelligence-docs-service (FastAPI, port 8000)
|
+-- /extract      Text extraction (Docling -> Tika -> Mistral OCR)
+-- /embed        Vectorize text (BGE-M3 -> Jina v3 -> Google -> OpenAI)
+-- /entities     NER (regex always + vLLM optional)
+-- /process      Full pipeline: extract + chunk + embed + NER
+-- /health       Provider availability status
```

### Provider Registry

Each capability (extraction, embedding, entities) has a registry of providers sharing a common interface. The registry tries providers in configured order and falls back automatically.

```python
class ExtractionProvider(ABC):
    async def extract(self, file_bytes: bytes, filename: str, options: dict) -> ExtractionResult
    def is_available(self) -> bool

class EmbeddingProvider(ABC):
    async def embed(self, texts: list[str], task: str) -> list[list[float]]
    async def embed_single(self, text: str, task: str) -> list[float]
    def dimensions(self) -> int
    def is_available(self) -> bool

class EntityProvider(ABC):
    async def extract_entities(self, text: str, language: str) -> list[Entity]
    def is_available(self) -> bool
```

### Providers (by priority)

| Capability | Provider | Type | Priority |
|-----------|----------|------|----------|
| **Extraction** | Docling | on-premise | 1 (default) |
| | Tika | on-premise | 2 (fallback) |
| | Mistral OCR | cloud, opt-in | 3 |
| **Embedding** | Sentence Transformers (BGE-M3) | on-premise, GPU | 1 (default) |
| | Sentence Transformers (Jina v3) | on-premise, GPU | alternative |
| | Google Embedding | cloud, opt-in | 2 |
| | OpenAI Embedding | cloud, opt-in | 3 |
| **Entities** | Regex (DNI/NIE/CIF) | on-premise | 1 (always active) |
| | vLLM NER | on-premise, GPU | 2 (optional) |

### Configuration

```ini
# Provider order (automatic fallback)
EXTRACTION_PROVIDERS=docling,tika
EMBEDDING_PROVIDERS=sentence-transformers
ENTITY_PROVIDERS=regex,vllm

# Active embedding model
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSIONS=1024
EMBEDDING_DEVICE=cuda

# Extraction backends
DOCLING_URL=http://docling:5001
TIKA_URL=http://tika:9998

# LLM for NER
VLLM_BASE_URL=http://vllm:8000/v1

# Cloud providers (opt-in, disabled by default)
# MISTRAL_API_KEY=...
# GOOGLE_EMBEDDING_API_KEY=...
# OPENAI_API_KEY=...
```

## API Contract

### POST /process (Full Pipeline)

The primary endpoint for document indexing. Replaces 3 separate HTTP calls.

**Request** (multipart/form-data):
```
file: bytes                     # Document (PDF, DOCX, etc.)
filename: str                   # "contrato_2024.pdf"
options: JSON {
    "extract": true,            # Step 1: extract text
    "chunk": true,              # Step 2: semantic chunking
    "embed": true,              # Step 3: vectorize chunks
    "entities": true,           # Step 4: NER
    "chunk_strategy": "legal_sections",
    "chunk_size": 1500,
    "chunk_overlap": 200,
    "embedding_task": "retrieval.passage",
    "language": "es"            # Auto-detect if omitted
}
```

**Response**:
```json
{
    "text": "Full extracted text...",
    "language": "es",
    "metadata": {
        "extraction_provider": "docling",
        "embedding_provider": "sentence-transformers",
        "embedding_model": "BAAI/bge-m3",
        "embedding_dimensions": 1024,
        "pages": 12,
        "quality_score": 0.85
    },
    "chunks": [
        {
            "content": "Articulo 1. Objeto del contrato...",
            "index": 0,
            "section_title": "Articulo 1",
            "vector": [0.023, -0.041, ...],
            "entities": [
                {"type": "PERSON", "value": "Juan Garcia", "provider": "regex"},
                {"type": "DATE", "value": "2024-03-15", "provider": "vllm"}
            ]
        }
    ],
    "entities_global": [
        {"type": "DNI", "value": "12345678A", "provider": "regex"}
    ],
    "processing_time_ms": 1850
}
```

### POST /embed

For query-time embedding (used by weaviate-service during searches).

**Request**:
```json
{
    "text": "contrato de arrendamiento",
    "task": "retrieval.query"
}
```

**Response**:
```json
{
    "embedding": [0.023, -0.041, ...],
    "dimensions": 1024,
    "model": "BAAI/bge-m3",
    "provider": "sentence-transformers"
}
```

Also supports batch:
```json
{
    "texts": ["text1", "text2"],
    "task": "retrieval.passage"
}
```

### POST /extract

Text extraction only (no embedding/NER).

**Request** (multipart/form-data):
```
file: bytes
filename: str
```

**Response**:
```json
{
    "text": "Extracted text...",
    "language": "es",
    "metadata": {
        "provider": "docling",
        "pages": 12,
        "quality_score": 0.85,
        "content_type": "application/pdf"
    }
}
```

### POST /entities

Entity extraction only.

**Request**:
```json
{
    "text": "Juan Garcia con DNI 12345678A firmó el contrato...",
    "language": "es"
}
```

**Response**:
```json
{
    "entities": [
        {"type": "PERSON", "value": "Juan Garcia", "provider": "regex"},
        {"type": "DNI", "value": "12345678A", "provider": "regex"}
    ]
}
```

### GET /health

Provider availability status.

**Response**:
```json
{
    "status": "healthy",
    "providers": {
        "extraction": [
            {"name": "docling", "available": true, "url": "http://docling:5001"},
            {"name": "tika", "available": true, "url": "http://tika:9998"}
        ],
        "embedding": [
            {"name": "sentence-transformers", "available": true, "model": "BAAI/bge-m3", "device": "cuda", "dimensions": 1024}
        ],
        "entities": [
            {"name": "regex", "available": true},
            {"name": "vllm", "available": true, "url": "http://vllm:8000/v1"}
        ]
    }
}
```

## File Structure

```
backend/microservices/intelligence-docs-service/
+-- app/
|   +-- main.py                          # FastAPI app + route registration
|   +-- core/
|   |   +-- config.py                    # Settings (providers, models, device)
|   +-- providers/
|   |   +-- base.py                      # ABC interfaces
|   |   +-- registry.py                  # ProviderRegistry (ordered fallback)
|   |   +-- extraction/
|   |   |   +-- docling.py               # Docling HTTP client
|   |   |   +-- tika.py                  # Tika HTTP client
|   |   |   +-- mistral_ocr.py           # Mistral OCR API (opt-in)
|   |   +-- embedding/
|   |   |   +-- sentence_transformers.py # BGE-M3 / Jina v3 local GPU
|   |   |   +-- google.py               # Google Embedding API (opt-in)
|   |   |   +-- openai.py               # OpenAI Embedding API (opt-in)
|   |   +-- entities/
|   |       +-- regex_spanish.py         # DNI/NIE/CIF (always active)
|   |       +-- vllm_ner.py             # LLM NER via vLLM
|   +-- pipeline/
|   |   +-- processor.py                 # /process orchestration
|   |   +-- chunker.py                   # SemanticChunker (migrated from weaviate-service)
|   |   +-- quality.py                   # DocumentIntelligence (quality scoring)
|   +-- schemas/
|       +-- models.py                    # Pydantic request/response models
+-- Dockerfile
+-- requirements.txt
+-- tests/
```

## Integration Changes

### weaviate-service

**Remove**:
- `generate_embedding()`, `get_embedding_model()`, `get_tei_embedding()` from `weaviate_service.py`
- `public_knowledge_service._generate_embedding()` (just fixed to use weaviate_service, will now call intelligence-docs-service)
- `multimodal_embedding_service.py` (entire file)
- `rag/textextract_client.py` (replaced by intelligence client)
- `rag/langextract_client.py` (replaced by intelligence client)
- Embedding model loading from service startup (frees GPU memory in this container)

**Add**:
- `clients/intelligence_client.py` — HTTP client for intelligence-docs-service
  - `process(file_bytes, filename, options) -> IntelligenceResult`
  - `embed(text, task) -> list[float]`
  - `embed_batch(texts, task) -> list[list[float]]`

**Modify**:
- `rag/indexing_pipeline.py` — Replace 3 service calls with single `intelligence_client.process()`
- All `generate_embedding()` call sites — Replace with `intelligence_client.embed()`
- `public_knowledge_service.py` — Replace `_generate_embedding()` with intelligence client call

### Docker Compose (docker-compose.onpremise.yml)

**Remove services**:
- `textextract-service`
- `langextract-service`

**Add service**:
```yaml
intelligence-docs-service:
    build:
        context: ../microservices/intelligence-docs-service
    environment:
        - EXTRACTION_PROVIDERS=docling,tika
        - EMBEDDING_PROVIDERS=sentence-transformers
        - EMBEDDING_MODEL=${EMBEDDING_MODEL:-BAAI/bge-m3}
        - EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-cuda}
        - ENTITY_PROVIDERS=regex,vllm
        - DOCLING_URL=http://docling:5001
        - TIKA_URL=http://tika:9998
        - VLLM_BASE_URL=http://vllm:8000/v1
    depends_on:
        tika: { condition: service_started }
    deploy:
        resources:
            reservations:
                devices:
                    - capabilities: [gpu]
    healthcheck:
        test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
        interval: 30s
        timeout: 10s
        retries: 3
```

**Update weaviate-service**:
- Remove `depends_on: textextract-service, langextract-service`
- Add `depends_on: intelligence-docs-service`
- Remove GPU reservation (embedding model no longer loaded here)

### Migration from existing code

Code to migrate (copy + refactor):
- `textextract-service/app/services/backends/` -> `providers/extraction/` (adapt to provider interface)
- `weaviate-service/app/services/rag/semantic_chunker.py` -> `pipeline/chunker.py`
- `weaviate-service/app/services/rag/document_intelligence.py` -> `pipeline/quality.py`
- `weaviate-service/app/services/weaviate_service.py` `generate_embedding()` logic -> `providers/embedding/sentence_transformers.py`
- `langextract-service/` regex patterns -> `providers/entities/regex_spanish.py`

## Net Result

| Metric | Before | After |
|--------|--------|-------|
| Docker services for processing | 3 (textextract + langextract + embedding-in-weaviate) | 1 (intelligence-docs-service) |
| HTTP calls per document index | 3 (extract + entities + implicit embed) | 1 (/process) |
| Embedding codepaths | 4 (sentence-transformers, TEI, multimodal, CAG) | 1 (provider registry) |
| Online provider support | None | Opt-in (Google, OpenAI, Mistral OCR) |
| GPU memory in weaviate-service | ~2-3 GB (BGE-M3) | 0 (moved to intelligence-docs-service) |
| Provider switching | Code changes required | Env var change |

## Out of Scope

- **Multimodal embedding** (images/tables): Deferred. Can be added as a provider later.
- **Streaming extraction**: Not needed for current document sizes.
- **Async job queue**: The `/process` endpoint is synchronous. For very large documents, weaviate-service already handles async via Celery.
- **Re-indexing tool**: When changing embedding model, existing onboarding scripts handle re-indexing.
