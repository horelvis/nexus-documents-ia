# Intelligence Docs Service — Design Spec

**Date**: 2026-03-25
**Status**: Draft (v2 — post-review)
**Replaces**: `textextract-service`, `langextract-service`, embedding code in `weaviate-service`

## Problem

The current document processing pipeline is fragmented across 3+ services and multiple embedding codepaths:

- **textextract-service**: Text extraction via Tika/Docling (separate Docker service)
- **langextract-service**: Entity extraction via vLLM NER + regex (separate Docker service, currently broken — `Invalid provider 'vllm'` because `langextract` library only validates `ollama|gemini|openai|anthropic`)
- **weaviate-service**: Hosts embedding model (BGE-M3 sentence-transformers) in-process, plus broken TEI path in `public_knowledge_service`, disabled multimodal embedding, and orphaned CAG embedding code in `cag_service.py`
- **No online provider support**: Everything is local-only. No way to use Google Embedding, Mistral OCR, etc.

This results in:
- 3 HTTP round-trips per document during indexing
- Silent embedding failures (chunks indexed without vectors)
- No provider abstraction (switching models requires code changes)
- GPU memory contention (BGE-M3 loaded inside weaviate-service alongside Weaviate operations)

## Solution

A single unified microservice — `intelligence-docs-service` — that consolidates extraction, embedding, and entity recognition behind a provider registry with ordered fallback. On-premise providers are always prioritized by default; cloud providers are opt-in.

**Scope boundary**: This service is **stateless and document-agnostic**. It handles extract + embed + NER. Chunking, contextual retrieval, hierarchical indexing, and knowledge graph operations remain in `weaviate-service` because they depend on tenant context, sector config, and Weaviate state.

## Design Principles

1. **On-premise first**: Works 100% offline by default. Cloud providers are opt-in via env vars.
2. **Single model active**: One embedding model per deployment. Changing model requires re-indexing (no mixed-dimension vectors).
3. **Provider registry with fallback**: Ordered list of providers per capability. First available wins.
4. **Stateless**: No tenant context, no database access, no Weaviate dependency. Pure document processing.
5. **Task adapters are first-class**: Jina v3 LoRA adapters (`retrieval.query`, `retrieval.passage`, `classification`, `text-matching`, `separation`) are exposed via the `task` parameter on all embedding endpoints. BGE-M3 ignores this parameter gracefully.

## Architecture

```
intelligence-docs-service (FastAPI, container-internal port 8000)
|
+-- /extract      Text extraction from file or URL (Docling -> Tika -> Mistral OCR)
+-- /embed        Vectorize text, single or batch (BGE-M3 -> Jina v3 -> Google -> OpenAI)
+-- /entities     NER (regex always + vLLM optional)
+-- /classify     Document type classification
+-- /process      Combined pipeline: extract + embed + NER in one call
+-- /health       Provider availability + embedding dimensions
```

Note: Port 8000 is container-internal only (all microservices use 8000 internally). Host-mapped port is configured in docker-compose (e.g., `8012:8000`). Inter-service communication uses Docker DNS (`http://intelligence-docs-service:8000`).

### Provider Registry

Each capability (extraction, embedding, entities) has a registry of providers sharing a common interface. The registry tries providers in configured order and falls back automatically.

```python
class ExtractionProvider(ABC):
    async def extract(self, file_bytes: bytes, filename: str, options: dict) -> ExtractionResult
    async def extract_from_url(self, url: str, filename: str, options: dict) -> ExtractionResult
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
| | vLLM NER (direct API) | on-premise, GPU | 2 (optional) |

Note on NER: The `langextract` Python library is **dropped entirely**. It caused the current `Invalid provider 'vllm'` bug because it only validates specific provider names. The vLLM NER provider makes direct OpenAI-compatible API calls to vLLM (`/v1/chat/completions`) with a structured extraction prompt, avoiding the library dependency.

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

# Timeouts (seconds)
EXTRACTION_TIMEOUT=600
EMBEDDING_TIMEOUT=30
NER_TIMEOUT=60

# Cloud providers (opt-in, disabled by default)
# MISTRAL_API_KEY=...
# GOOGLE_EMBEDDING_API_KEY=...
# OPENAI_API_KEY=...
```

## API Contract

### POST /process (Combined Pipeline)

Primary endpoint for document indexing. Combines extraction + embedding + NER in a single HTTP call. **Does NOT include chunking** — chunking remains in weaviate-service because it depends on tenant sector config.

**Request** (multipart/form-data):
```
file: bytes                     # Document (PDF, DOCX, etc.) — mutually exclusive with url
url: str                        # URL to fetch document from — mutually exclusive with file
filename: str                   # "contrato_2024.pdf"
options: JSON {
    "extract": true,            # Step 1: extract text
    "embed": true,              # Step 2: vectorize full text (not chunks — chunking is caller's job)
    "entities": true,           # Step 3: NER on full text
    "embedding_task": "retrieval.passage",
    "language": "es"            # Auto-detect via langdetect if omitted
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
        "quality_score": 0.85,
        "content_type": "application/pdf"
    },
    "vector": [0.023, -0.041, ...],
    "entities": [
        {"type": "PERSON", "value": "Juan Garcia", "provider": "regex"},
        {"type": "DNI", "value": "12345678A", "provider": "regex"},
        {"type": "DATE", "value": "2024-03-15", "provider": "vllm"}
    ],
    "processing_time_ms": 1850
}
```

Note: The response contains a single vector for the full text. For chunk-level vectors, the caller (weaviate-service) chunks the text locally, then calls `/embed` in batch with the chunk texts.

### POST /embed

For query-time embedding and batch chunk embedding. Supports Jina v3 task adapters via the `task` parameter.

**Single request**:
```json
{
    "text": "contrato de arrendamiento",
    "task": "retrieval.query"
}
```

**Single response**:
```json
{
    "embedding": [0.023, -0.041, ...],
    "dimensions": 1024,
    "model": "BAAI/bge-m3",
    "provider": "sentence-transformers"
}
```

**Batch request** (for chunk-level embedding after chunking in weaviate-service):
```json
{
    "texts": ["chunk 1 text", "chunk 2 text", "chunk 3 text"],
    "task": "retrieval.passage"
}
```

**Batch response**:
```json
{
    "embeddings": [[0.023, ...], [0.041, ...], [0.019, ...]],
    "dimensions": 1024,
    "model": "BAAI/bge-m3",
    "provider": "sentence-transformers"
}
```

Available `task` values (Jina v3 LoRA adapters — ignored by BGE-M3):
- `retrieval.query` — query-time search
- `retrieval.passage` — document/chunk indexing
- `classification` — semantic type classification
- `text-matching` — similarity comparisons
- `separation` — cluster separation

### POST /extract

Text extraction only (from file bytes or URL).

**Request** (multipart/form-data):
```
file: bytes                     # Mutually exclusive with url
url: str                        # Mutually exclusive with file
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
        "content_type": "application/pdf",
        "creator": "Microsoft Word",
        "created_date": "2024-01-15"
    }
}
```

### POST /entities

Entity extraction only.

**Request**:
```json
{
    "text": "Juan Garcia con DNI 12345678A firmo el contrato...",
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

### POST /classify

Document type classification. Replaces `langextract_client.categorize_document()`.

**Request**:
```json
{
    "text": "First 2000 chars of document...",
    "filename": "factura_2024.pdf"
}
```

**Response**:
```json
{
    "document_type": "factura",
    "confidence": 0.92,
    "domain": "fiscal",
    "provider": "vllm"
}
```

Falls back to filename-based heuristics if vLLM is unavailable.

### GET /health

Provider availability status. **Includes `embedding_dimensions`** so consumers can validate against their collection schemas at startup.

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
|   |   +-- config.py                    # Settings (providers, models, device, timeouts)
|   +-- providers/
|   |   +-- base.py                      # ABC interfaces (ExtractionProvider, EmbeddingProvider, EntityProvider)
|   |   +-- registry.py                  # ProviderRegistry (ordered fallback, availability check)
|   |   +-- extraction/
|   |   |   +-- docling.py               # Docling HTTP client (from_bytes + from_url)
|   |   |   +-- tika.py                  # Tika HTTP client (from_bytes + from_url)
|   |   |   +-- mistral_ocr.py           # Mistral OCR API (opt-in, cloud)
|   |   +-- embedding/
|   |   |   +-- sentence_transformers.py # BGE-M3 / Jina v3 local GPU, task adapter support
|   |   |   +-- google.py               # Google Embedding API (opt-in)
|   |   |   +-- openai.py               # OpenAI Embedding API (opt-in)
|   |   +-- entities/
|   |       +-- regex_spanish.py         # DNI/NIE/CIF patterns (always active)
|   |       +-- vllm_ner.py             # Direct vLLM API for NER (no langextract library)
|   +-- pipeline/
|   |   +-- processor.py                 # /process orchestration (extract + embed + NER)
|   |   +-- quality.py                   # Document quality scoring (migrated from weaviate-service)
|   |   +-- classifier.py               # Document type classification (/classify)
|   |   +-- language.py                  # Language auto-detection (langdetect)
|   +-- schemas/
|       +-- models.py                    # Pydantic request/response models
+-- Dockerfile
+-- requirements.txt
+-- tests/
```

Note: `SemanticChunker` stays in `weaviate-service` — it depends on tenant sector config (chunk_strategy, chunk_size per sector) and integrates with contextual retrieval, hierarchical indexing, and OCR fallback.

## Integration Changes

### weaviate-service

**Remove**:
- `generate_embedding()`, `get_embedding_model()`, `get_tei_embedding()` from `weaviate_service.py`
- `public_knowledge_service._generate_embedding()`
- `multimodal_embedding_service.py` (entire file)
- `rag/textextract_client.py` (replaced by intelligence client)
- `rag/langextract_client.py` (replaced by intelligence client)
- Embedding model loading from service startup (frees ~2-3 GB GPU memory in this container)

**Add**:
- `clients/intelligence_client.py` — HTTP client for intelligence-docs-service:
  - `extract(file_bytes, filename) -> ExtractionResult`
  - `extract_from_url(url, filename) -> ExtractionResult`
  - `embed(text, task) -> list[float]`
  - `embed_batch(texts, task) -> list[list[float]]`
  - `entities(text, language) -> list[Entity]`
  - `classify(text, filename) -> ClassificationResult`
  - `process(file_bytes, filename, options) -> ProcessResult`
  - `get_embedding_dimensions() -> int` (cached, from /health)

**Modify**:
- `rag/indexing_pipeline.py` — Replace `textextract_client` + `langextract_client` + `generate_embedding()` calls with `intelligence_client` methods
- All `generate_embedding()` call sites (~15 locations) — Replace with `intelligence_client.embed()`
- `public_knowledge_service.py` — Replace `_generate_embedding()` with `intelligence_client.embed()`
- `rag/semantic_type_classifier.py` — Replace `from weaviate_service import generate_embedding` with `intelligence_client.embed(text, task="classification")`
- **Startup validation**: On init, call `intelligence_client.get_embedding_dimensions()` and compare against Weaviate collection schema. Log error and refuse to start if dimensions mismatch.

### Docker Compose (docker-compose.onpremise.yml)

**Remove services**:
- `textextract-service`
- `langextract-service`

**Add service**:
```yaml
intelligence-docs-service:
    build:
        context: ../microservices/intelligence-docs-service
    ports:
        - "127.0.0.1:8012:8000"    # Host debug access only (localhost)
    environment:
        - EXTRACTION_PROVIDERS=docling,tika
        - EMBEDDING_PROVIDERS=sentence-transformers
        - EMBEDDING_MODEL=${EMBEDDING_MODEL:-BAAI/bge-m3}
        - EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-cuda}
        - ENTITY_PROVIDERS=regex,vllm
        - DOCLING_URL=http://docling:5001
        - TIKA_URL=http://tika:9998
        - VLLM_BASE_URL=http://vllm:8000/v1
        - EXTRACTION_TIMEOUT=600
        - EMBEDDING_TIMEOUT=30
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
- Add env: `INTELLIGENCE_DOCS_SERVICE_URL=http://intelligence-docs-service:8000`

**GPU note**: BGE-M3 uses ~2-3 GB VRAM. Moving it from weaviate-service to intelligence-docs-service does not change total GPU pressure — it just isolates it. Both services share the same physical GPU via NVIDIA Container Toolkit. No `CUDA_VISIBLE_DEVICES` partitioning is needed since sentence-transformers and vLLM/SGLang can coexist on the same GPU (SGLang pre-allocates via `gpu_memory_utilization`, leaving the rest available for BGE-M3).

### Migration from existing code

Code to migrate (copy + refactor to provider interface):
- `textextract-service/app/services/backends/` -> `providers/extraction/` (adapt TikaBackend, DoclingBackend)
- `weaviate-service/app/services/rag/document_intelligence.py` -> `pipeline/quality.py` (quality scoring only)
- `weaviate-service/app/services/weaviate_service.py` lines 50-130 -> `providers/embedding/sentence_transformers.py`
- `langextract-service/` regex patterns for DNI/NIE/CIF -> `providers/entities/regex_spanish.py`
- `weaviate-service/app/services/rag/ocr_client.py` -> Absorbed into extraction providers (Docling and Tika already handle OCR; enhanced OCR fallback stays in weaviate-service's indexing pipeline as a re-extraction call with different options)

## Incremental Migration Path

The migration is done in phases to avoid a big-bang cutover:

### Phase 1: Deploy with /embed only
- Build intelligence-docs-service with embedding providers
- Deploy alongside existing services
- Migrate `generate_embedding()` call sites in weaviate-service to `intelligence_client.embed()`
- Validate: embeddings match (same model, same dimensions)
- Remove embedding model loading from weaviate-service

### Phase 2: Migrate /extract
- Add extraction providers to intelligence-docs-service
- Migrate `textextract_client` calls to `intelligence_client.extract()`
- Validate: extraction output matches for test documents
- Remove `textextract-service` from docker-compose

### Phase 3: Migrate /entities + /classify
- Add entity and classification providers
- Migrate `langextract_client` calls to `intelligence_client.entities()` + `intelligence_client.classify()`
- Validate: entity extraction matches (regex patterns identical)
- Remove `langextract-service` from docker-compose

### Phase 4: Add /process endpoint
- Implement combined pipeline endpoint
- Refactor indexing pipeline to use `/process` where beneficial
- This is an optimization, not a requirement — individual endpoints work fine

## Net Result

| Metric | Before | After |
|--------|--------|-------|
| Docker services for processing | 3 (textextract + langextract + embedding-in-weaviate) | 1 (intelligence-docs-service) |
| HTTP calls per document index | 3+ (extract + entities + implicit embed) | 2 (extract + embed_batch after chunking) or 1 (/process + embed_batch) |
| Embedding codepaths | 4 (sentence-transformers, TEI, multimodal, CAG) | 1 (provider registry) |
| Online provider support | None | Opt-in (Google, OpenAI, Mistral OCR) |
| GPU memory in weaviate-service | ~2-3 GB (BGE-M3) | 0 (moved to intelligence-docs-service) |
| Provider switching | Code changes required | Env var change |
| NER library dependency | `langextract` (broken for vLLM) | Direct vLLM API (no library) |

## Out of Scope

- **Multimodal embedding** (images/tables): Deferred. Can be added as an embedding provider later.
- **Streaming extraction**: Not needed for current document sizes.
- **Async job queue**: The `/process` endpoint is synchronous. For very large documents, weaviate-service already handles async via Celery.
- **Re-indexing tool**: When changing embedding model, existing onboarding scripts handle re-indexing.
- **Chunking**: Stays in weaviate-service (depends on tenant sector config, contextual retrieval, hierarchical indexing).
- **OCR fallback orchestration**: The decision to re-extract with OCR after quality check stays in weaviate-service's indexing pipeline. Intelligence-docs-service just extracts what it's asked to extract.
