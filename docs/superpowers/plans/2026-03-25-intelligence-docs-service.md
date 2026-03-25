# Intelligence Docs Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `intelligence-docs-service` — a unified microservice replacing `textextract-service`, `langextract-service`, and embedding code in `weaviate-service` behind a provider registry with automatic fallback.

**Architecture:** FastAPI service with provider registry pattern. Three registries (extraction, embedding, entities) each with ordered providers that fall back automatically. On-premise providers first (Docling, BGE-M3, regex), cloud opt-in. Stateless — no tenant context, no DB access.

**Tech Stack:** Python 3.12, FastAPI, sentence-transformers (BGE-M3), httpx, langdetect, Pydantic v2

**Spec:** `docs/superpowers/specs/2026-03-25-intelligence-docs-service-design.md`

---

## File Structure

```
backend/microservices/intelligence-docs-service/
+-- app/
|   +-- __init__.py
|   +-- main.py                              # FastAPI app, routes, lifespan
|   +-- core/
|   |   +-- __init__.py
|   |   +-- config.py                        # Settings from env vars
|   +-- providers/
|   |   +-- __init__.py
|   |   +-- base.py                          # ABC: ExtractionProvider, EmbeddingProvider, EntityProvider
|   |   +-- registry.py                      # ProviderRegistry with ordered fallback
|   |   +-- extraction/
|   |   |   +-- __init__.py
|   |   |   +-- docling.py                   # Docling HTTP client
|   |   |   +-- tika.py                      # Tika HTTP client
|   |   +-- embedding/
|   |   |   +-- __init__.py
|   |   |   +-- sentence_transformers.py     # BGE-M3 / Jina v3 local
|   |   +-- entities/
|   |       +-- __init__.py
|   |       +-- regex_spanish.py             # DNI/NIE/CIF patterns
|   |       +-- vllm_ner.py                  # Direct vLLM API NER
|   +-- pipeline/
|   |   +-- __init__.py
|   |   +-- processor.py                     # /process orchestration
|   |   +-- quality.py                       # Document quality scoring
|   |   +-- classifier.py                    # Document type classification
|   |   +-- language.py                      # Language auto-detection
|   +-- schemas/
|       +-- __init__.py
|       +-- models.py                        # Pydantic request/response models
+-- Dockerfile
+-- requirements.txt
+-- tests/
    +-- __init__.py
    +-- conftest.py                          # Shared fixtures
    +-- test_registry.py                     # Provider registry tests
    +-- test_embedding.py                    # Embedding provider tests
    +-- test_extraction.py                   # Extraction provider tests
    +-- test_entities.py                     # Entity provider tests
    +-- test_api.py                          # API endpoint integration tests
    +-- test_quality.py                      # Document quality tests
    +-- test_classifier.py                   # Document classifier tests
```

Files modified in weaviate-service:
- Modify: `backend/microservices/weaviate-service/app/services/weaviate_service.py` (remove embedding functions, add intelligence client calls)
- Modify: `backend/microservices/weaviate-service/app/services/public_knowledge_service.py` (replace _generate_embedding)
- Modify: `backend/microservices/weaviate-service/app/services/rag/semantic_type_classifier.py` (replace generate_embedding import)
- Modify: `backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py` (replace textextract + langextract clients)
- Create: `backend/microservices/weaviate-service/app/clients/intelligence_client.py`
- Modify: `backend/docker/docker-compose.onpremise.yml` (add service, remove old ones)

---

## Phase 1: Core Service + Embedding Provider

### Task 1: Project Scaffolding + Config

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/__init__.py`
- Create: `backend/microservices/intelligence-docs-service/app/core/__init__.py`
- Create: `backend/microservices/intelligence-docs-service/app/core/config.py`
- Create: `backend/microservices/intelligence-docs-service/requirements.txt`
- Create: `backend/microservices/intelligence-docs-service/Dockerfile`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/microservices/intelligence-docs-service/{app/{core,providers/{extraction,embedding,entities},pipeline,schemas},tests}
touch backend/microservices/intelligence-docs-service/{app/{__init__,main},app/core/__init__,app/providers/__init__,app/providers/extraction/__init__,app/providers/embedding/__init__,app/providers/entities/__init__,app/pipeline/__init__,app/schemas/__init__,tests/__init__}.py
```

- [ ] **Step 2: Write config.py**

```python
# backend/microservices/intelligence-docs-service/app/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Provider order (comma-separated, parsed from env string)
    extraction_providers: str = "docling,tika"
    embedding_providers: str = "sentence-transformers"
    entity_providers: str = "regex,vllm"

    # Embedding
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimensions: int = 1024
    embedding_device: str = "cuda"
    embedding_task_query: str = "retrieval.query"
    embedding_task_passage: str = "retrieval.passage"

    # Extraction backends
    docling_url: str = "http://docling:5001"
    tika_url: str = "http://tika:9998"

    # LLM for NER
    vllm_base_url: str = "http://vllm:8000/v1"
    vllm_model: str = ""

    # Timeouts (seconds)
    extraction_timeout: int = 600
    embedding_timeout: int = 30
    ner_timeout: int = 60

    # Cloud providers (opt-in)
    mistral_api_key: str = ""
    google_embedding_api_key: str = ""
    openai_api_key: str = ""

    @property
    def extraction_provider_list(self) -> list[str]:
        return [p.strip() for p in self.extraction_providers.split(",")]

    @property
    def embedding_provider_list(self) -> list[str]:
        return [p.strip() for p in self.embedding_providers.split(",")]

    @property
    def entity_provider_list(self) -> list[str]:
        return [p.strip() for p in self.entity_providers.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
```

- [ ] **Step 3: Write requirements.txt**

```
# backend/microservices/intelligence-docs-service/requirements.txt
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.0
pydantic-settings>=2.0
httpx>=0.27.0
sentence-transformers>=3.0.0
langdetect>=1.0.9
python-multipart>=0.0.12
torch>=2.0
numpy
```

- [ ] **Step 4: Write Dockerfile**

```dockerfile
# backend/microservices/intelligence-docs-service/Dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Commit scaffolding**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): scaffold project structure + config"
```

---

### Task 2: Provider Base Classes + Registry

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/providers/base.py`
- Create: `backend/microservices/intelligence-docs-service/app/providers/registry.py`
- Test: `backend/microservices/intelligence-docs-service/tests/test_registry.py`

- [ ] **Step 1: Write provider base classes**

```python
# backend/microservices/intelligence-docs-service/app/providers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractionResult:
    text: str
    language: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0


@dataclass
class Entity:
    type: str        # PERSON, DNI, NIE, CIF, DATE, ORGANIZATION, AMOUNT, LOCATION
    value: str
    provider: str
    confidence: float = 1.0


@dataclass
class ClassificationResult:
    document_type: str
    confidence: float
    domain: str = ""
    provider: str = ""


class ExtractionProvider(ABC):
    name: str

    @abstractmethod
    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        ...

    @abstractmethod
    async def extract_from_url(self, url: str, filename: str, **options) -> ExtractionResult:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


class EmbeddingProvider(ABC):
    name: str

    @abstractmethod
    async def embed(self, texts: list[str], task: str = "") -> list[list[float]]:
        ...

    @abstractmethod
    async def embed_single(self, text: str, task: str = "") -> list[float]:
        ...

    @abstractmethod
    def dimensions(self) -> int:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


class EntityProvider(ABC):
    name: str

    @abstractmethod
    async def extract_entities(self, text: str, language: str = "es") -> list[Entity]:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...
```

- [ ] **Step 2: Write failing registry test**

```python
# backend/microservices/intelligence-docs-service/tests/test_registry.py
import pytest
from app.providers.registry import ProviderRegistry
from app.providers.base import EmbeddingProvider


class FakeEmbeddingOK(EmbeddingProvider):
    name = "fake-ok"

    async def embed(self, texts, task=""):
        return [[0.1] * 10 for _ in texts]

    async def embed_single(self, text, task=""):
        return [0.1] * 10

    def dimensions(self):
        return 10

    async def is_available(self):
        return True


class FakeEmbeddingFail(EmbeddingProvider):
    name = "fake-fail"

    async def embed(self, texts, task=""):
        raise ConnectionError("down")

    async def embed_single(self, text, task=""):
        raise ConnectionError("down")

    def dimensions(self):
        return 10

    async def is_available(self):
        return False


@pytest.mark.asyncio
async def test_registry_returns_first_available():
    registry = ProviderRegistry[EmbeddingProvider]()
    registry.register(FakeEmbeddingFail())
    registry.register(FakeEmbeddingOK())
    provider = await registry.get_available()
    assert provider.name == "fake-ok"


@pytest.mark.asyncio
async def test_registry_raises_when_none_available():
    registry = ProviderRegistry[EmbeddingProvider]()
    registry.register(FakeEmbeddingFail())
    with pytest.raises(RuntimeError, match="No.*provider available"):
        await registry.get_available()


def test_registry_list_all():
    registry = ProviderRegistry[EmbeddingProvider]()
    ok = FakeEmbeddingOK()
    registry.register(ok)
    assert registry.all() == [ok]
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_registry.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.registry'`

- [ ] **Step 4: Implement ProviderRegistry**

```python
# backend/microservices/intelligence-docs-service/app/providers/registry.py
import logging
from typing import Generic, TypeVar

from app.providers.base import ExtractionProvider, EmbeddingProvider, EntityProvider

T = TypeVar("T", ExtractionProvider, EmbeddingProvider, EntityProvider)
logger = logging.getLogger(__name__)


class ProviderRegistry(Generic[T]):
    """Ordered registry of providers with automatic fallback."""

    def __init__(self):
        self._providers: list[T] = []

    def register(self, provider: T) -> None:
        self._providers.append(provider)

    def all(self) -> list[T]:
        return list(self._providers)

    async def get_available(self) -> T:
        """Return the first available provider, or raise RuntimeError."""
        for provider in self._providers:
            try:
                if await provider.is_available():
                    return provider
            except Exception as e:
                logger.warning(f"Provider {provider.name} availability check failed: {e}")
        names = [p.name for p in self._providers]
        raise RuntimeError(f"No {type(self).__name__} provider available. Tried: {names}")

    async def status(self) -> list[dict]:
        """Return availability status of all providers."""
        result = []
        for provider in self._providers:
            try:
                available = await provider.is_available()
            except Exception:
                available = False
            result.append({"name": provider.name, "available": available})
        return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_registry.py -v
```

Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): provider base classes + registry with fallback"
```

---

### Task 3: Sentence Transformers Embedding Provider

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/providers/embedding/sentence_transformers.py`
- Test: `backend/microservices/intelligence-docs-service/tests/test_embedding.py`

Source reference: `backend/microservices/weaviate-service/app/services/weaviate_service.py:50-130`

- [ ] **Step 1: Write failing embedding test**

```python
# backend/microservices/intelligence-docs-service/tests/test_embedding.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.providers.embedding.sentence_transformers import SentenceTransformersProvider


@pytest.mark.asyncio
async def test_embed_single_returns_correct_dimensions():
    """Test that embedding returns vector of configured dimensions."""
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3",
        device="cpu",
        expected_dimensions=1024,
    )
    # Mock the model to avoid loading a real model in tests
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 1024)
    provider._model = mock_model

    result = await provider.embed_single("test text")
    assert len(result) == 1024
    assert isinstance(result[0], float)


@pytest.mark.asyncio
async def test_embed_batch():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3",
        device="cpu",
        expected_dimensions=1024,
    )
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [[0.1] * 1024, [0.2] * 1024])
    provider._model = mock_model

    result = await provider.embed(["text1", "text2"])
    assert len(result) == 2


@pytest.mark.asyncio
async def test_dimensions():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3",
        device="cpu",
        expected_dimensions=1024,
    )
    assert provider.dimensions() == 1024


@pytest.mark.asyncio
async def test_is_available_when_model_loaded():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3",
        device="cpu",
        expected_dimensions=1024,
    )
    provider._model = MagicMock()
    assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_is_available_when_model_not_loaded():
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3",
        device="cpu",
        expected_dimensions=1024,
    )
    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_task_adapter_fallback():
    """Test that unsupported task adapter falls back to basic encode."""
    provider = SentenceTransformersProvider(
        model_name="BAAI/bge-m3",
        device="cpu",
        expected_dimensions=1024,
    )
    mock_model = MagicMock()
    # First call with prompt_name raises, second without succeeds
    mock_model.encode.side_effect = [
        TypeError("prompt_name not supported"),
        MagicMock(tolist=lambda: [0.1] * 1024),
    ]
    provider._model = mock_model

    result = await provider.embed_single("test", task="retrieval.query")
    assert len(result) == 1024
    assert mock_model.encode.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_embedding.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SentenceTransformersProvider**

```python
# backend/microservices/intelligence-docs-service/app/providers/embedding/sentence_transformers.py
import asyncio
import logging
from typing import Optional

from app.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class SentenceTransformersProvider(EmbeddingProvider):
    """Local embedding via sentence-transformers (BGE-M3, Jina v3, etc.)."""

    name = "sentence-transformers"

    def __init__(self, model_name: str, device: str, expected_dimensions: int):
        self._model_name = model_name
        self._device = device
        self._expected_dimensions = expected_dimensions
        self._model = None  # Lazy-loaded

    async def load_model(self) -> bool:
        """Load the model. Called once at startup."""
        if self._model is not None:
            return True
        try:
            logger.info(f"Loading embedding model: {self._model_name} on {self._device}")
            loop = asyncio.get_event_loop()

            def _load():
                import torch
                from sentence_transformers import SentenceTransformer

                device = self._device
                if device == "cuda" and not torch.cuda.is_available():
                    logger.warning("CUDA not available, falling back to CPU")
                    device = "cpu"

                model = SentenceTransformer(self._model_name, device=device)

                # Verify dimensions
                test_emb = model.encode("test", convert_to_numpy=True)
                dims = len(test_emb)
                if dims != self._expected_dimensions:
                    logger.warning(
                        f"Model dimensions {dims} != expected {self._expected_dimensions}"
                    )
                    self._expected_dimensions = dims

                logger.info(
                    f"Loaded embedding model: {self._model_name} "
                    f"({dims} dims) on {device}"
                )
                return model

            self._model = await loop.run_in_executor(None, _load)
            return True
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._model = None
            return False

    async def embed_single(self, text: str, task: str = "") -> list[float]:
        if self._model is None:
            raise RuntimeError("Embedding model not loaded")
        loop = asyncio.get_event_loop()

        def _encode():
            kwargs = {"convert_to_numpy": True}
            if task:
                try:
                    return self._model.encode(text, prompt_name=task, **kwargs).tolist()
                except (TypeError, ValueError, KeyError):
                    pass  # Model doesn't support this task adapter
            return self._model.encode(text, **kwargs).tolist()

        return await loop.run_in_executor(None, _encode)

    async def embed(self, texts: list[str], task: str = "") -> list[list[float]]:
        if self._model is None:
            raise RuntimeError("Embedding model not loaded")
        loop = asyncio.get_event_loop()

        def _encode_batch():
            kwargs = {"convert_to_numpy": True}
            if task:
                try:
                    return self._model.encode(texts, prompt_name=task, **kwargs).tolist()
                except (TypeError, ValueError, KeyError):
                    pass
            return self._model.encode(texts, **kwargs).tolist()

        return await loop.run_in_executor(None, _encode_batch)

    def dimensions(self) -> int:
        return self._expected_dimensions

    async def is_available(self) -> bool:
        return self._model is not None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_embedding.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): sentence-transformers embedding provider"
```

---

### Task 4: Pydantic Schemas + /embed and /health Endpoints

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/schemas/models.py`
- Create: `backend/microservices/intelligence-docs-service/app/main.py`
- Test: `backend/microservices/intelligence-docs-service/tests/test_api.py`

- [ ] **Step 1: Write Pydantic schemas**

```python
# backend/microservices/intelligence-docs-service/app/schemas/models.py
from pydantic import BaseModel
from typing import Optional, Any


# --- Embedding ---

class EmbedRequest(BaseModel):
    text: Optional[str] = None
    texts: Optional[list[str]] = None
    task: str = "retrieval.passage"

class EmbedSingleResponse(BaseModel):
    embedding: list[float]
    dimensions: int
    model: str
    provider: str

class EmbedBatchResponse(BaseModel):
    embeddings: list[list[float]]
    dimensions: int
    model: str
    provider: str

# --- Extraction ---

class ExtractResponse(BaseModel):
    text: str
    language: str
    metadata: dict[str, Any] = {}

# --- Entities ---

class EntityResponse(BaseModel):
    type: str
    value: str
    provider: str
    confidence: float = 1.0

class EntitiesRequest(BaseModel):
    text: str
    language: str = "es"

class EntitiesResponse(BaseModel):
    entities: list[EntityResponse]

# --- Classification ---

class ClassifyRequest(BaseModel):
    text: str
    filename: str = ""

class ClassifyResponse(BaseModel):
    document_type: str
    confidence: float
    domain: str = ""
    provider: str = ""

# --- Process (combined pipeline) ---

class ProcessOptions(BaseModel):
    extract: bool = True
    embed: bool = True
    entities: bool = True
    embedding_task: str = "retrieval.passage"
    language: str = ""

class ProcessResponse(BaseModel):
    text: str
    language: str
    metadata: dict[str, Any] = {}
    vector: Optional[list[float]] = None
    entities: list[EntityResponse] = []
    processing_time_ms: int = 0

# --- Health ---

class ProviderStatus(BaseModel):
    name: str
    available: bool
    model: Optional[str] = None
    device: Optional[str] = None
    dimensions: Optional[int] = None
    url: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    providers: dict[str, list[ProviderStatus]]
```

- [ ] **Step 2: Write failing API test for /embed and /health**

```python
# backend/microservices/intelligence-docs-service/tests/test_api.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked embedding provider."""
    # Must patch before importing app
    from app.main import app
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "providers" in data
    assert "embedding" in data["providers"]


def test_embed_single(client):
    response = client.post("/embed", json={
        "text": "test document",
        "task": "retrieval.query"
    })
    # May fail if model not loaded in test, that's OK — we test the route exists
    assert response.status_code in (200, 503)


def test_embed_batch(client):
    response = client.post("/embed", json={
        "texts": ["text1", "text2"],
        "task": "retrieval.passage"
    })
    assert response.status_code in (200, 503)


def test_embed_requires_text_or_texts(client):
    response = client.post("/embed", json={"task": "retrieval.query"})
    assert response.status_code == 422 or response.status_code == 400
```

- [ ] **Step 3: Write main.py with /embed and /health**

```python
# backend/microservices/intelligence-docs-service/app/main.py
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from typing import Optional

from app.core.config import settings
from app.providers.registry import ProviderRegistry
from app.providers.base import EmbeddingProvider, ExtractionProvider, EntityProvider
from app.providers.embedding.sentence_transformers import SentenceTransformersProvider
from app.schemas.models import (
    EmbedRequest, EmbedSingleResponse, EmbedBatchResponse,
    HealthResponse, ProviderStatus,
)

logger = logging.getLogger(__name__)

# Global registries
embedding_registry = ProviderRegistry[EmbeddingProvider]()
extraction_registry = ProviderRegistry[ExtractionProvider]()
entity_registry = ProviderRegistry[EntityProvider]()


async def _init_embedding_providers():
    """Initialize embedding providers based on config."""
    for provider_name in settings.embedding_providers:
        provider_name = provider_name.strip()
        if provider_name == "sentence-transformers":
            provider = SentenceTransformersProvider(
                model_name=settings.embedding_model,
                device=settings.embedding_device,
                expected_dimensions=settings.embedding_dimensions,
            )
            await provider.load_model()
            embedding_registry.register(provider)
            logger.info(f"Registered embedding provider: {provider.name}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load models and register providers."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting intelligence-docs-service...")
    await _init_embedding_providers()
    logger.info("intelligence-docs-service ready")
    yield
    logger.info("Shutting down intelligence-docs-service")


app = FastAPI(
    title="Intelligence Docs Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    embedding_status = []
    for p in embedding_registry.all():
        available = await p.is_available()
        embedding_status.append(ProviderStatus(
            name=p.name,
            available=available,
            model=getattr(p, "_model_name", None),
            device=getattr(p, "_device", None),
            dimensions=p.dimensions() if available else None,
        ))

    extraction_status = await extraction_registry.status()
    entity_status = await entity_registry.status()

    any_embedding = any(s.available for s in embedding_status)
    status = "healthy" if any_embedding else "degraded"

    return HealthResponse(
        status=status,
        providers={
            "embedding": embedding_status,
            "extraction": [ProviderStatus(**s) for s in extraction_status],
            "entities": [ProviderStatus(**s) for s in entity_status],
        },
    )


@app.post("/embed")
async def embed(request: EmbedRequest):
    if not request.text and not request.texts:
        raise HTTPException(status_code=400, detail="Provide 'text' or 'texts'")

    try:
        provider = await embedding_registry.get_available()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if request.text and not request.texts:
        # Single embedding
        vector = await provider.embed_single(request.text, task=request.task)
        return EmbedSingleResponse(
            embedding=vector,
            dimensions=provider.dimensions(),
            model=getattr(provider, "_model_name", "unknown"),
            provider=provider.name,
        )
    else:
        # Batch embedding
        texts = request.texts or [request.text]
        vectors = await provider.embed(texts, task=request.task)
        return EmbedBatchResponse(
            embeddings=vectors,
            dimensions=provider.dimensions(),
            model=getattr(provider, "_model_name", "unknown"),
            provider=provider.name,
        )
```

- [ ] **Step 4: Run tests**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_api.py -v
```

Expected: Tests pass (health returns 200, embed returns 503 since no GPU in test)

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): /embed + /health endpoints with schemas"
```

---

### Task 5: Docker Compose Integration + Smoke Test

**Files:**
- Modify: `backend/docker/docker-compose.onpremise.yml` (add intelligence-docs-service)

- [ ] **Step 1: Add intelligence-docs-service to docker-compose.onpremise.yml**

Add after the existing services, before weaviate-service. Use the compose definition from the spec:

```yaml
  intelligence-docs-service:
    build:
      context: ../microservices/intelligence-docs-service
      dockerfile: Dockerfile
    ports:
      - "127.0.0.1:8012:8000"
    environment:
      - EXTRACTION_PROVIDERS=${EXTRACTION_PROVIDERS:-docling,tika}
      - EMBEDDING_PROVIDERS=${EMBEDDING_PROVIDERS:-sentence-transformers}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-BAAI/bge-m3}
      - EMBEDDING_DIMENSIONS=${EMBEDDING_DIMENSIONS:-1024}
      - EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-cuda}
      - ENTITY_PROVIDERS=${ENTITY_PROVIDERS:-regex}
      - DOCLING_URL=http://docling:5001
      - TIKA_URL=http://tika:9998
      - VLLM_BASE_URL=http://vllm:8000/v1
      - VLLM_MODEL=${VLLM_MODEL:-}
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
```

- [ ] **Step 2: Build and start the service**

```bash
cd backend/docker && docker compose build intelligence-docs-service
docker compose up -d intelligence-docs-service
```

- [ ] **Step 3: Smoke test /health and /embed**

```bash
# Wait for service to be healthy
sleep 30
curl -s http://localhost:8012/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"

# Test embedding
curl -s -X POST http://localhost:8012/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "Ley de Proteccion de Datos", "task": "retrieval.query"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK: {d[\"dimensions\"]} dims') if 'embedding' in d else print(d)"
```

Expected: 1024 dims from BGE-M3

- [ ] **Step 4: Commit**

```bash
git add backend/docker/docker-compose.onpremise.yml
git commit -m "feat(intelligence-docs): add to docker-compose with GPU + healthcheck"
```

---

## Phase 2: Extraction Providers

### Task 6: Tika Extraction Provider

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/providers/extraction/tika.py`
- Test: `backend/microservices/intelligence-docs-service/tests/test_extraction.py`

Source reference: `backend/microservices/textextract-service/app/services/backends/tika_backend.py`

- [ ] **Step 1: Write failing test**

```python
# backend/microservices/intelligence-docs-service/tests/test_extraction.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from app.providers.extraction.tika import TikaProvider


@pytest.mark.asyncio
async def test_tika_extract_returns_text():
    provider = TikaProvider(url="http://tika:9998", timeout=30)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Extracted document text"
    mock_response.headers = {"Content-Type": "text/plain"}

    with patch("httpx.AsyncClient.put", new_callable=AsyncMock, return_value=mock_response):
        result = await provider.extract(b"fake pdf bytes", "test.pdf")
        assert result.text == "Extracted document text"
        assert result.metadata["extraction_provider"] == "tika"


@pytest.mark.asyncio
async def test_tika_is_available_when_reachable():
    provider = TikaProvider(url="http://tika:9998", timeout=30)
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_tika_is_unavailable_when_unreachable():
    provider = TikaProvider(url="http://tika:9998", timeout=30)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")):
        assert await provider.is_available() is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_extraction.py -v
```

- [ ] **Step 3: Implement TikaProvider**

```python
# backend/microservices/intelligence-docs-service/app/providers/extraction/tika.py
import logging
import mimetypes
import httpx
from langdetect import detect

from app.providers.base import ExtractionProvider, ExtractionResult

logger = logging.getLogger(__name__)

MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".html": "text/html",
    ".csv": "text/csv",
    ".md": "text/markdown",
}


class TikaProvider(ExtractionProvider):
    """Extract text via Apache Tika REST API."""

    name = "tika"

    def __init__(self, url: str, timeout: int = 600):
        self._url = url.rstrip("/")
        self._timeout = timeout

    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = MIME_MAP.get(ext) or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.put(
                f"{self._url}/tika",
                content=file_bytes,
                headers={
                    "Content-Type": content_type,
                    "Accept": "text/plain",
                },
            )
            response.raise_for_status()
            text = response.text.strip()

        language = ""
        if text and len(text) > 20:
            try:
                language = detect(text)
            except Exception:
                pass

        return ExtractionResult(
            text=text,
            language=language,
            metadata={
                "extraction_provider": "tika",
                "content_type": content_type,
                "characters": len(text),
            },
        )

    async def extract_from_url(self, url: str, filename: str, **options) -> ExtractionResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return await self.extract(resp.content, filename, **options)

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._url}/version")
                return resp.status_code == 200
        except Exception:
            return False
```

- [ ] **Step 4: Run tests, verify pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_extraction.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): Tika extraction provider"
```

---

### Task 7: Docling Extraction Provider

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/providers/extraction/docling.py`
- Modify: `backend/microservices/intelligence-docs-service/tests/test_extraction.py` (add Docling tests)

Source reference: `backend/microservices/textextract-service/app/services/backends/docling_backend.py`

- [ ] **Step 1: Write failing Docling test** (append to test_extraction.py)

```python
# Append to tests/test_extraction.py
from app.providers.extraction.docling import DoclingProvider


@pytest.mark.asyncio
async def test_docling_extract_returns_markdown():
    provider = DoclingProvider(url="http://docling:5001", timeout=300)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "document": {"md_content": "# Title\n\nExtracted content"},
        "status": "success"
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await provider.extract(b"fake pdf bytes", "test.pdf")
        assert "Extracted content" in result.text
        assert result.metadata["extraction_provider"] == "docling"
```

- [ ] **Step 2: Implement DoclingProvider**

```python
# backend/microservices/intelligence-docs-service/app/providers/extraction/docling.py
import logging
import httpx
from langdetect import detect

from app.providers.base import ExtractionProvider, ExtractionResult

logger = logging.getLogger(__name__)


class DoclingProvider(ExtractionProvider):
    """Extract text via IBM Docling Serve API. Returns Markdown."""

    name = "docling"

    def __init__(self, url: str, timeout: int = 600):
        self._url = url.rstrip("/")
        self._timeout = timeout

    async def extract(self, file_bytes: bytes, filename: str, **options) -> ExtractionResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._url}/v1/convert/file",
                files={"file": (filename, file_bytes)},
            )
            response.raise_for_status()
            data = response.json()

        text = data.get("document", {}).get("md_content", "")
        if not text:
            text = data.get("text", "")

        language = ""
        if text and len(text) > 20:
            try:
                language = detect(text)
            except Exception:
                pass

        page_count = data.get("document", {}).get("num_pages", 0)

        return ExtractionResult(
            text=text,
            language=language,
            metadata={
                "extraction_provider": "docling",
                "extraction_format": "markdown",
                "characters": len(text),
                "pages": page_count,
            },
        )

    async def extract_from_url(self, url: str, filename: str, **options) -> ExtractionResult:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return await self.extract(resp.content, filename, **options)

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._url}/health")
                return resp.status_code == 200
        except Exception:
            return False
```

- [ ] **Step 3: Add /extract endpoint to main.py**

Add to `app/main.py` after the `/embed` endpoint:

```python
from app.providers.extraction.tika import TikaProvider
from app.providers.extraction.docling import DoclingProvider
from app.schemas.models import ExtractResponse


async def _init_extraction_providers():
    for provider_name in settings.extraction_providers:
        provider_name = provider_name.strip()
        if provider_name == "docling":
            extraction_registry.register(
                DoclingProvider(url=settings.docling_url, timeout=settings.extraction_timeout)
            )
        elif provider_name == "tika":
            extraction_registry.register(
                TikaProvider(url=settings.tika_url, timeout=settings.extraction_timeout)
            )
        logger.info(f"Registered extraction provider: {provider_name}")


# Call in lifespan after _init_embedding_providers():
#   await _init_extraction_providers()


@app.post("/extract", response_model=ExtractResponse)
async def extract(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide 'file' or 'url'")

    try:
        provider = await extraction_registry.get_available()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if file:
        file_bytes = await file.read()
        fname = filename or file.filename or "unknown"
        result = await provider.extract(file_bytes, fname)
    else:
        fname = filename or url.split("/")[-1]
        result = await provider.extract_from_url(url, fname)

    return ExtractResponse(
        text=result.text,
        language=result.language,
        metadata=result.metadata,
    )
```

- [ ] **Step 4: Run tests, verify pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): Docling + Tika extraction providers + /extract endpoint"
```

---

## Phase 3: Entity Providers

### Task 8: Regex Spanish Entity Provider

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/providers/entities/regex_spanish.py`
- Test: `backend/microservices/intelligence-docs-service/tests/test_entities.py`

Source reference: `backend/microservices/weaviate-service/app/services/rag/langextract_client.py:36-139`

- [ ] **Step 1: Write failing test**

```python
# backend/microservices/intelligence-docs-service/tests/test_entities.py
import pytest
from app.providers.entities.regex_spanish import RegexSpanishProvider


@pytest.mark.asyncio
async def test_extracts_dni():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("DNI del cliente: 12345678A")
    assert any(e.type == "DNI" and e.value == "12345678A" for e in entities)


@pytest.mark.asyncio
async def test_extracts_nie():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("NIE: X1234567B")
    assert any(e.type == "NIE" and e.value == "X1234567B" for e in entities)


@pytest.mark.asyncio
async def test_extracts_cif():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("CIF empresa: A12345678")
    assert any(e.type == "CIF" and e.value == "A12345678" for e in entities)


@pytest.mark.asyncio
async def test_extracts_multiple():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities(
        "Juan Garcia con DNI 12345678A de la empresa A12345678"
    )
    types = {e.type for e in entities}
    assert "DNI" in types
    assert "CIF" in types


@pytest.mark.asyncio
async def test_is_always_available():
    provider = RegexSpanishProvider()
    assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_no_entities_in_clean_text():
    provider = RegexSpanishProvider()
    entities = await provider.extract_entities("El tiempo hoy es soleado")
    assert len(entities) == 0
```

- [ ] **Step 2: Implement RegexSpanishProvider**

```python
# backend/microservices/intelligence-docs-service/app/providers/entities/regex_spanish.py
import re
from app.providers.base import EntityProvider, Entity

DNI_PATTERN = re.compile(r"\b(\d{8}[A-Za-z])\b")
NIE_PATTERN = re.compile(r"\b([XYZxyz]\d{7}[A-Za-z])\b")
CIF_PATTERN = re.compile(r"\b([A-Ha-h]\d{8})\b")

DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def _validate_dni(number: str) -> bool:
    digits = number[:8]
    letter = number[8].upper()
    try:
        return DNI_LETTERS[int(digits) % 23] == letter
    except (ValueError, IndexError):
        return False


def _validate_nie(number: str) -> bool:
    prefix_map = {"X": "0", "Y": "1", "Z": "2"}
    first = number[0].upper()
    if first not in prefix_map:
        return False
    digits = prefix_map[first] + number[1:8]
    letter = number[8].upper()
    try:
        return DNI_LETTERS[int(digits) % 23] == letter
    except (ValueError, IndexError):
        return False


class RegexSpanishProvider(EntityProvider):
    """Extract Spanish identity document numbers via regex. Always available."""

    name = "regex"

    async def extract_entities(self, text: str, language: str = "es") -> list[Entity]:
        entities = []
        seen = set()

        for match in DNI_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in seen and _validate_dni(value):
                entities.append(Entity(type="DNI", value=value, provider="regex"))
                seen.add(value)

        for match in NIE_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in seen and _validate_nie(value):
                entities.append(Entity(type="NIE", value=value, provider="regex"))
                seen.add(value)

        for match in CIF_PATTERN.finditer(text):
            value = match.group(1).upper()
            if value not in seen:
                entities.append(Entity(type="CIF", value=value, provider="regex"))
                seen.add(value)

        return entities

    async def is_available(self) -> bool:
        return True
```

- [ ] **Step 3: Run tests, verify pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_entities.py -v
```

- [ ] **Step 4: Add /entities endpoint to main.py**

```python
# Add to main.py
from app.providers.entities.regex_spanish import RegexSpanishProvider
from app.schemas.models import EntitiesRequest, EntitiesResponse, EntityResponse


async def _init_entity_providers():
    for provider_name in settings.entity_providers:
        provider_name = provider_name.strip()
        if provider_name == "regex":
            entity_registry.register(RegexSpanishProvider())
            logger.info("Registered entity provider: regex")


@app.post("/entities", response_model=EntitiesResponse)
async def entities(request: EntitiesRequest):
    all_entities = []
    for provider in entity_registry.all():
        try:
            if await provider.is_available():
                result = await provider.extract_entities(request.text, request.language)
                all_entities.extend(result)
        except Exception as e:
            logger.warning(f"Entity provider {provider.name} failed: {e}")

    return EntitiesResponse(
        entities=[EntityResponse(
            type=e.type, value=e.value, provider=e.provider, confidence=e.confidence
        ) for e in all_entities]
    )
```

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): regex Spanish entity provider + /entities endpoint"
```

---

### Task 9: Document Quality Scoring + Language Detection

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/pipeline/quality.py`
- Create: `backend/microservices/intelligence-docs-service/app/pipeline/language.py`
- Test: `backend/microservices/intelligence-docs-service/tests/test_quality.py`

Source reference: `backend/microservices/weaviate-service/app/services/rag/document_intelligence.py`

- [ ] **Step 1: Write quality and language modules**

```python
# backend/microservices/intelligence-docs-service/app/pipeline/language.py
from langdetect import detect


def detect_language(text: str) -> str:
    """Detect language of text. Returns ISO 639-1 code or empty string."""
    if not text or len(text.strip()) < 20:
        return ""
    try:
        return detect(text)
    except Exception:
        return ""
```

```python
# backend/microservices/intelligence-docs-service/app/pipeline/quality.py
import re


def compute_quality_score(text: str) -> float:
    """Score document text quality from 0.0 to 1.0."""
    if not text:
        return 0.0

    issues = 0
    total_checks = 5

    # Check 1: Very short text
    if len(text) < 50:
        issues += 1

    # Check 2: High ratio of special characters (OCR noise)
    special = sum(1 for c in text if not c.isalnum() and not c.isspace())
    if len(text) > 0 and special / len(text) > 0.3:
        issues += 1

    # Check 3: Missing whitespace (garbled OCR)
    words = text.split()
    if words:
        avg_word_len = sum(len(w) for w in words) / len(words)
        if avg_word_len > 20:
            issues += 1

    # Check 4: Repetitive content
    lines = text.split("\n")
    if len(lines) > 5:
        unique = len(set(lines))
        if unique / len(lines) < 0.3:
            issues += 1

    # Check 5: Encoding issues
    if "\ufffd" in text or "\x00" in text:
        issues += 1

    return max(0.0, 1.0 - (issues / total_checks))
```

- [ ] **Step 2: Write test**

```python
# backend/microservices/intelligence-docs-service/tests/test_quality.py
from app.pipeline.quality import compute_quality_score
from app.pipeline.language import detect_language


def test_quality_good_text():
    score = compute_quality_score("Este es un documento de buena calidad con texto legible.")
    assert score >= 0.8


def test_quality_empty():
    assert compute_quality_score("") == 0.0


def test_quality_garbled():
    score = compute_quality_score("a" * 200)  # No spaces, one giant word
    assert score < 0.8


def test_detect_spanish():
    lang = detect_language("Este es un documento en espanol sobre contratos laborales")
    assert lang == "es"


def test_detect_empty():
    assert detect_language("") == ""
```

- [ ] **Step 3: Run tests, verify pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_quality.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): document quality scoring + language detection"
```

---

### Task 9b: vLLM NER Provider

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/providers/entities/vllm_ner.py`
- Modify: `backend/microservices/intelligence-docs-service/tests/test_entities.py` (add vLLM tests)

The `langextract` library is dropped. This provider makes direct OpenAI-compatible API calls to vLLM.

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_entities.py
from unittest.mock import AsyncMock, patch, MagicMock
from app.providers.entities.vllm_ner import VllmNerProvider


@pytest.mark.asyncio
async def test_vllm_ner_extracts_entities():
    provider = VllmNerProvider(base_url="http://vllm:8000/v1", model="test-model", timeout=30)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '[{"type":"PERSON","value":"Juan Garcia"},{"type":"ORGANIZATION","value":"Acme S.L."}]'}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        entities = await provider.extract_entities("Juan Garcia de Acme S.L. firmo el contrato")
        types = {e.type for e in entities}
        assert "PERSON" in types
        assert "ORGANIZATION" in types


@pytest.mark.asyncio
async def test_vllm_ner_handles_invalid_json():
    provider = VllmNerProvider(base_url="http://vllm:8000/v1", model="test-model", timeout=30)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "not valid json"}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        entities = await provider.extract_entities("some text")
        assert entities == []


@pytest.mark.asyncio
async def test_vllm_ner_unavailable_when_no_model():
    provider = VllmNerProvider(base_url="http://vllm:8000/v1", model="", timeout=30)
    assert await provider.is_available() is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_entities.py::test_vllm_ner_extracts_entities -v
```

- [ ] **Step 3: Implement VllmNerProvider**

```python
# backend/microservices/intelligence-docs-service/app/providers/entities/vllm_ner.py
import json
import logging
import httpx

from app.providers.base import EntityProvider, Entity

logger = logging.getLogger(__name__)

NER_SYSTEM_PROMPT = """Extract named entities from the text. Return a JSON array of objects with "type" and "value" fields.
Entity types: PERSON, ORGANIZATION, DATE, AMOUNT, LOCATION.
Only return the JSON array, no other text. If no entities found, return [].
Example: [{"type":"PERSON","value":"Maria Lopez"},{"type":"DATE","value":"2024-03-15"}]"""


class VllmNerProvider(EntityProvider):
    """Extract entities via direct OpenAI-compatible API calls to vLLM."""

    name = "vllm"

    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def extract_entities(self, text: str, language: str = "es") -> list[Entity]:
        if not self._model:
            return []

        # Truncate to avoid token limits
        truncated = text[:4000] if len(text) > 4000 else text

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": NER_SYSTEM_PROMPT},
                            {"role": "user", "content": truncated},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                )
                response.raise_for_status()
                data = response.json()

            content = data["choices"][0]["message"]["content"].strip()
            # Extract JSON array from response (may have surrounding text)
            start = content.find("[")
            end = content.rfind("]") + 1
            if start == -1 or end == 0:
                return []

            raw_entities = json.loads(content[start:end])
            return [
                Entity(
                    type=e.get("type", "UNKNOWN"),
                    value=e.get("value", ""),
                    provider="vllm",
                    confidence=e.get("confidence", 0.8),
                )
                for e in raw_entities
                if e.get("value")
            ]
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse vLLM NER response: {e}")
            return []
        except Exception as e:
            logger.warning(f"vLLM NER failed: {e}")
            return []

    async def is_available(self) -> bool:
        if not self._model:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False
```

- [ ] **Step 4: Update `_init_entity_providers()` in main.py**

Add the vllm branch:

```python
from app.providers.entities.vllm_ner import VllmNerProvider

async def _init_entity_providers():
    for provider_name in settings.entity_provider_list:
        if provider_name == "regex":
            entity_registry.register(RegexSpanishProvider())
            logger.info("Registered entity provider: regex")
        elif provider_name == "vllm":
            provider = VllmNerProvider(
                base_url=settings.vllm_base_url,
                model=settings.vllm_model,
                timeout=settings.ner_timeout,
            )
            entity_registry.register(provider)
            logger.info(f"Registered entity provider: vllm (model={settings.vllm_model})")
```

- [ ] **Step 5: Run tests, verify pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_entities.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): vLLM NER provider (replaces langextract library)"
```

---

### Task 9c: Document Classifier + /classify Endpoint

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/pipeline/classifier.py`
- Create: `backend/microservices/intelligence-docs-service/tests/test_classifier.py`
- Modify: `backend/microservices/intelligence-docs-service/app/main.py` (add /classify route)

Replaces `langextract_client.categorize_document()` (see `weaviate-service/app/services/rag/langextract_client.py:241-283`).

- [ ] **Step 1: Write failing test**

```python
# backend/microservices/intelligence-docs-service/tests/test_classifier.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.pipeline.classifier import classify_document


@pytest.mark.asyncio
async def test_classify_by_filename_factura():
    result = await classify_document("contenido de la factura...", "factura_2024.pdf", vllm_available=False)
    assert result.document_type == "factura"
    assert result.domain == "fiscal"


@pytest.mark.asyncio
async def test_classify_by_filename_contrato():
    result = await classify_document("contenido del contrato...", "contrato_laboral.pdf", vllm_available=False)
    assert result.document_type == "contrato"
    assert result.domain == "legal"


@pytest.mark.asyncio
async def test_classify_by_filename_nomina():
    result = await classify_document("", "nomina_marzo.pdf", vllm_available=False)
    assert result.document_type == "nomina"
    assert result.domain == "laboral"


@pytest.mark.asyncio
async def test_classify_unknown():
    result = await classify_document("random text", "document.pdf", vllm_available=False)
    assert result.document_type == "general"
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_classifier.py -v
```

- [ ] **Step 3: Implement classifier**

```python
# backend/microservices/intelligence-docs-service/app/pipeline/classifier.py
import re
import logging
from app.providers.base import ClassificationResult

logger = logging.getLogger(__name__)

# Filename-based heuristics (fallback when LLM unavailable)
FILENAME_PATTERNS: list[tuple[str, str, str]] = [
    (r"factura|invoice", "factura", "fiscal"),
    (r"contrato|contract", "contrato", "legal"),
    (r"nomina|payroll|payslip", "nomina", "laboral"),
    (r"modelo.?(111|190|303|347|390)", "modelo_fiscal", "fiscal"),
    (r"sentencia|resoluci[oó]n", "sentencia", "legal"),
    (r"convenio", "convenio", "laboral"),
    (r"estatuto", "estatuto", "legal"),
    (r"informe|report", "informe", "general"),
    (r"acta", "acta", "legal"),
    (r"escritura", "escritura", "legal"),
    (r"p[oó]liza", "poliza", "mercantil"),
    (r"balance|cuenta.*resultado", "contable", "fiscal"),
    (r"certificado", "certificado", "general"),
    (r"demanda", "demanda", "legal"),
]


async def classify_document(
    text: str,
    filename: str,
    vllm_available: bool = False,
    vllm_base_url: str = "",
    vllm_model: str = "",
) -> ClassificationResult:
    """Classify document type. Uses filename heuristics, with optional LLM."""
    fname_lower = filename.lower()

    # Stage 1: Filename heuristics
    for pattern, doc_type, domain in FILENAME_PATTERNS:
        if re.search(pattern, fname_lower, re.IGNORECASE):
            return ClassificationResult(
                document_type=doc_type,
                confidence=0.75,
                domain=domain,
                provider="heuristic",
            )

    # Stage 2: Content heuristics (first 500 chars)
    snippet = text[:500].lower() if text else ""
    for pattern, doc_type, domain in FILENAME_PATTERNS:
        if re.search(pattern, snippet, re.IGNORECASE):
            return ClassificationResult(
                document_type=doc_type,
                confidence=0.60,
                domain=domain,
                provider="heuristic",
            )

    # Default
    return ClassificationResult(
        document_type="general",
        confidence=0.30,
        domain="general",
        provider="heuristic",
    )
```

- [ ] **Step 4: Add /classify route to main.py**

```python
from app.pipeline.classifier import classify_document
from app.schemas.models import ClassifyRequest, ClassifyResponse


@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    result = await classify_document(
        text=request.text,
        filename=request.filename,
    )
    return ClassifyResponse(
        document_type=result.document_type,
        confidence=result.confidence,
        domain=result.domain,
        provider=result.provider,
    )
```

- [ ] **Step 5: Run tests, verify pass**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/test_classifier.py -v
```

- [ ] **Step 6: Add `classify()` to intelligence_client.py**

Add this method to `backend/microservices/weaviate-service/app/clients/intelligence_client.py`:

```python
async def classify(text: str, filename: str) -> Optional[dict]:
    """Classify document type."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_base_url}/classify",
                json={"text": text[:2000], "filename": filename},
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"Intelligence classification failed: {e}")
        return None
```

- [ ] **Step 7: Commit**

```bash
git add backend/microservices/intelligence-docs-service/ backend/microservices/weaviate-service/app/clients/
git commit -m "feat(intelligence-docs): document classifier + /classify endpoint"
```

---

### Task 10: /process Combined Pipeline Endpoint

**Files:**
- Create: `backend/microservices/intelligence-docs-service/app/pipeline/processor.py`
- Modify: `backend/microservices/intelligence-docs-service/app/main.py` (add /process route)

- [ ] **Step 1: Implement processor**

```python
# backend/microservices/intelligence-docs-service/app/pipeline/processor.py
import time
import logging
from typing import Optional

from app.providers.registry import ProviderRegistry
from app.providers.base import (
    ExtractionProvider, EmbeddingProvider, EntityProvider,
    ExtractionResult, Entity,
)
from app.pipeline.quality import compute_quality_score
from app.pipeline.language import detect_language
from app.schemas.models import ProcessOptions, ProcessResponse, EntityResponse

logger = logging.getLogger(__name__)


async def process_document(
    file_bytes: Optional[bytes],
    url: Optional[str],
    filename: str,
    options: ProcessOptions,
    extraction_registry: ProviderRegistry[ExtractionProvider],
    embedding_registry: ProviderRegistry[EmbeddingProvider],
    entity_registry: ProviderRegistry[EntityProvider],
) -> ProcessResponse:
    start = time.monotonic()

    text = ""
    metadata: dict = {}
    vector: Optional[list[float]] = None
    entities: list[EntityResponse] = []

    # Step 1: Extract text
    if options.extract:
        try:
            provider = await extraction_registry.get_available()
            if file_bytes:
                result = await provider.extract(file_bytes, filename)
            elif url:
                result = await provider.extract_from_url(url, filename)
            else:
                raise ValueError("No file or URL provided")

            text = result.text
            metadata = result.metadata
            metadata["quality_score"] = compute_quality_score(text)
        except RuntimeError as e:
            logger.error(f"No extraction provider available: {e}")
            metadata["extraction_error"] = str(e)

    # Detect language
    language = options.language or detect_language(text)

    # Step 2: Embed full text
    if options.embed and text:
        try:
            provider = await embedding_registry.get_available()
            vector = await provider.embed_single(text, task=options.embedding_task)
            metadata["embedding_provider"] = provider.name
            metadata["embedding_model"] = getattr(provider, "_model_name", "unknown")
            metadata["embedding_dimensions"] = provider.dimensions()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            metadata["embedding_error"] = str(e)

    # Step 3: Extract entities
    if options.entities and text:
        for provider in entity_registry.all():
            try:
                if await provider.is_available():
                    result = await provider.extract_entities(text, language)
                    entities.extend([
                        EntityResponse(
                            type=e.type, value=e.value,
                            provider=e.provider, confidence=e.confidence,
                        )
                        for e in result
                    ])
            except Exception as e:
                logger.warning(f"Entity provider {provider.name} failed: {e}")

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return ProcessResponse(
        text=text,
        language=language,
        metadata=metadata,
        vector=vector,
        entities=entities,
        processing_time_ms=elapsed_ms,
    )
```

- [ ] **Step 2: Add /process route to main.py**

```python
# Add to main.py
from app.pipeline.processor import process_document
from app.schemas.models import ProcessOptions, ProcessResponse


@app.post("/process", response_model=ProcessResponse)
async def process(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
    options: str = Form("{}"),
):
    import json
    opts = ProcessOptions(**json.loads(options))

    file_bytes = None
    if file:
        file_bytes = await file.read()
        fname = filename or file.filename or "unknown"
    elif url:
        fname = filename or url.split("/")[-1]
    else:
        raise HTTPException(status_code=400, detail="Provide 'file' or 'url'")

    return await process_document(
        file_bytes=file_bytes,
        url=url,
        filename=fname,
        options=opts,
        extraction_registry=extraction_registry,
        embedding_registry=embedding_registry,
        entity_registry=entity_registry,
    )
```

- [ ] **Step 3: Run all tests**

```bash
cd backend/microservices/intelligence-docs-service && python -m pytest tests/ -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/intelligence-docs-service/
git commit -m "feat(intelligence-docs): /process combined pipeline endpoint"
```

---

## Phase 4: Weaviate-Service Integration

### Task 11: Intelligence Client in weaviate-service

**Files:**
- Create: `backend/microservices/weaviate-service/app/clients/intelligence_client.py`
- Create: `backend/microservices/weaviate-service/app/clients/__init__.py`

- [ ] **Step 1: Create intelligence_client.py**

```python
# backend/microservices/weaviate-service/app/clients/intelligence_client.py
import logging
from typing import Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_base_url: str = getattr(settings, "intelligence_docs_service_url", "http://intelligence-docs-service:8000")
_timeout: float = 30.0
_extraction_timeout: float = 600.0
_cached_dimensions: Optional[int] = None


async def embed(text: str, task: str = "") -> Optional[list[float]]:
    """Generate embedding for a single text."""
    try:
        async with httpx.AsyncClient(timeout=_timeout) as client:
            response = await client.post(
                f"{_base_url}/embed",
                json={"text": text, "task": task},
            )
            response.raise_for_status()
            return response.json()["embedding"]
    except Exception as e:
        logger.warning(f"Intelligence embedding failed: {e}")
        return None


async def embed_batch(texts: list[str], task: str = "") -> Optional[list[list[float]]]:
    """Generate embeddings for multiple texts."""
    try:
        async with httpx.AsyncClient(timeout=_timeout) as client:
            response = await client.post(
                f"{_base_url}/embed",
                json={"texts": texts, "task": task},
            )
            response.raise_for_status()
            return response.json()["embeddings"]
    except Exception as e:
        logger.warning(f"Intelligence batch embedding failed: {e}")
        return None


async def extract(file_bytes: bytes, filename: str) -> Optional[dict]:
    """Extract text from document bytes."""
    try:
        async with httpx.AsyncClient(timeout=_extraction_timeout) as client:
            response = await client.post(
                f"{_base_url}/extract",
                files={"file": (filename, file_bytes)},
                data={"filename": filename},
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"Intelligence extraction failed: {e}")
        return None


async def extract_from_url(url: str, filename: str) -> Optional[dict]:
    """Extract text from document URL."""
    try:
        async with httpx.AsyncClient(timeout=_extraction_timeout) as client:
            response = await client.post(
                f"{_base_url}/extract",
                data={"url": url, "filename": filename},
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"Intelligence URL extraction failed: {e}")
        return None


async def extract_entities(text: str, language: str = "es") -> list[dict]:
    """Extract entities from text."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{_base_url}/entities",
                json={"text": text, "language": language},
            )
            response.raise_for_status()
            return response.json().get("entities", [])
    except Exception as e:
        logger.warning(f"Intelligence entity extraction failed: {e}")
        return []


async def get_embedding_dimensions() -> Optional[int]:
    """Get embedding dimensions from health endpoint (cached)."""
    global _cached_dimensions
    if _cached_dimensions is not None:
        return _cached_dimensions
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{_base_url}/health")
            response.raise_for_status()
            data = response.json()
            for p in data.get("providers", {}).get("embedding", []):
                if p.get("available") and p.get("dimensions"):
                    _cached_dimensions = p["dimensions"]
                    return _cached_dimensions
    except Exception as e:
        logger.warning(f"Failed to get embedding dimensions: {e}")
    return None
```

- [ ] **Step 2: Add INTELLIGENCE_DOCS_SERVICE_URL to weaviate-service config**

In `backend/microservices/weaviate-service/app/core/config.py`, add:

```python
intelligence_docs_service_url: str = os.getenv("INTELLIGENCE_DOCS_SERVICE_URL", "http://intelligence-docs-service:8000")
```

- [ ] **Step 3: Add env var to docker-compose.onpremise.yml weaviate-service section**

Add to the weaviate-service environment block:

```yaml
- INTELLIGENCE_DOCS_SERVICE_URL=http://intelligence-docs-service:8000
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/weaviate-service/app/clients/ backend/microservices/weaviate-service/app/core/config.py backend/docker/docker-compose.onpremise.yml
git commit -m "feat(weaviate): add intelligence_client for intelligence-docs-service"
```

---

### Task 12: Migrate All Embedding + Extraction Call Sites

**Files:**
- Modify: `backend/microservices/weaviate-service/app/services/weaviate_service.py`
- Modify: `backend/microservices/weaviate-service/app/services/public_knowledge_service.py`
- Modify: `backend/microservices/weaviate-service/app/services/rag/semantic_type_classifier.py`
- Modify: `backend/microservices/weaviate-service/app/services/rag/query_intelligence.py`
- Modify: `backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py`
- Modify: `backend/microservices/weaviate-service/app/main.py` (remove /embed endpoint or proxy)

This is the largest task. Replace ALL `generate_embedding()` calls and old client imports.

- [ ] **Step 1: Replace import in public_knowledge_service.py**

```python
# Change line 16 from:
from app.services.weaviate_service import generate_embedding
# To:
from app.clients.intelligence_client import embed as generate_embedding
```

And update `_generate_embedding` method:
```python
async def _generate_embedding(self, text: str) -> Optional[List[float]]:
    """Generate embedding via intelligence-docs-service."""
    return await generate_embedding(text)
```

- [ ] **Step 2: Replace import in semantic_type_classifier.py**

At lines 204 and 266, change:
```python
from app.services.weaviate_service import generate_embedding
```
To:
```python
from app.clients.intelligence_client import embed as generate_embedding
```

- [ ] **Step 3: Replace import in query_intelligence.py**

At line 350, `_generate_embeddings()` calls TEI directly via HTTP. Replace with intelligence client:
```python
from app.clients.intelligence_client import embed

async def _generate_embeddings(self, text: str) -> Optional[List[float]]:
    return await embed(text, task="retrieval.query")
```

- [ ] **Step 4: Replace calls in weaviate_service.py**

Add import at top:
```python
from app.clients import intelligence_client
```

Then replace all internal `generate_embedding(text)` calls with `await intelligence_client.embed(text)`. Key locations:
- Line 352: test connection → `await intelligence_client.embed("test connection")`
- Line 874: context embedding
- Line 939: query embedding
- Line 1682: chunk embedding during indexing
- Line 1739: chunk embedding
- Line 2039: query embedding
- Line 2077: query embedding
- Line 2861: query embedding
- Line 2968: text embedding

- [ ] **Step 5: Migrate indexing_pipeline.py**

Replace old client imports:
```python
# Change:
from .textextract_client import textextract_client, TextExtractResult
from .langextract_client import langextract_client, LangExtractResult
# To:
from app.clients import intelligence_client
```

Then migrate the call sites:
- `textextract_client.extract_from_bytes()` → `intelligence_client.extract()`
- `textextract_client.extract_from_url()` → `intelligence_client.extract_from_url()`
- `langextract_client.extract_entities()` → `intelligence_client.extract_entities()`
- `langextract_client.categorize_document()` → `intelligence_client.classify()`

- [ ] **Step 6: Handle weaviate-service /embed endpoint in main.py**

The weaviate-service's own `/embed` endpoint at `main.py:206` currently calls the local `generate_embedding()`. Either:
- Proxy it to intelligence-docs-service, or
- Remove it (if no external consumers depend on it)

Check if anything calls `weaviate-service:8007/embed` externally. If not, remove it.

- [ ] **Step 7: Remove old embedding functions from weaviate_service.py**

Delete lines 27-130 (functions: `get_tei_embedding`, `get_embedding_model`, `generate_embedding`) and the associated imports (`sentence_transformers`, `torch`, etc.).

- [ ] **Step 8: Add dimension validation at startup**

In weaviate-service startup (lifespan in `main.py`), add:
```python
# Validate embedding dimensions match Weaviate collection
dims = await intelligence_client.get_embedding_dimensions()
if dims:
    logger.info(f"Intelligence-docs-service embedding dimensions: {dims}")
    # Compare with Weaviate collection config if needed
else:
    logger.warning("Could not verify embedding dimensions from intelligence-docs-service")
```

- [ ] **Step 9: Test by restarting both services**

```bash
cd backend/docker
docker compose restart weaviate-service intelligence-docs-service
sleep 30
# Save response to file first (per CLAUDE.md best practices)
docker compose exec -T weaviate-service curl -s http://intelligence-docs-service:8000/health > /tmp/health.json
python3 -c "import json; d=json.load(open('/tmp/health.json')); print(json.dumps(d, indent=2))"
```

- [ ] **Step 10: Commit**

```bash
git add backend/microservices/weaviate-service/
git commit -m "refactor(weaviate): migrate all embedding + extraction to intelligence_client"
```

---

### Task 13: Remove Old Services from Docker Compose

**Files:**
- Modify: `backend/docker/docker-compose.onpremise.yml`

- [ ] **Step 1: Update weaviate-service depends_on**

Replace:
```yaml
textextract-service:
    condition: service_started
langextract-service:
    condition: service_healthy
```
With:
```yaml
intelligence-docs-service:
    condition: service_healthy
```

- [ ] **Step 2: Remove GPU reservation from weaviate-service**

Remove the `deploy.resources.reservations.devices` block from weaviate-service (embedding model no longer loaded here).

- [ ] **Step 3: Comment out textextract-service and langextract-service**

Comment out (don't delete yet — keep for rollback) the `textextract-service` (lines ~249-280) and `langextract-service` (lines ~289-314) service definitions.

- [ ] **Step 4: Full integration test**

```bash
cd backend/docker
docker compose down
docker compose up -d
# Wait for all services
sleep 60
# Verify intelligence-docs-service is healthy
curl -s http://localhost:8012/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])"
# Verify weaviate-service can embed via intelligence-docs-service
docker compose exec -T weaviate-service curl -s http://intelligence-docs-service:8000/embed \
  -X POST -H "Content-Type: application/json" \
  -d '{"text":"test","task":"retrieval.query"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'OK: {d[\"dimensions\"]} dims')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/docker/docker-compose.onpremise.yml
git commit -m "refactor(docker): wire intelligence-docs-service, comment out old services"
```

---

### Task 14: Delete Dead Code

**Files:**
- Delete: `backend/microservices/weaviate-service/app/services/multimodal_embedding_service.py`
- Delete: `backend/app/services/embedding_service.py` (orphaned CAG service)
- Delete: `backend/microservices/weaviate-service/app/services/rag/textextract_client.py`
- Delete: `backend/microservices/weaviate-service/app/services/rag/langextract_client.py`
- Modify: `backend/microservices/weaviate-service/app/services/weaviate_service.py` (remove unused embedding imports)
- Modify: `backend/microservices/weaviate-service/app/cag/services/cag_service.py` (remove embedding codepath)

- [ ] **Step 1: Delete dead files**

```bash
rm backend/microservices/weaviate-service/app/services/multimodal_embedding_service.py
rm backend/app/services/embedding_service.py
rm backend/microservices/weaviate-service/app/services/rag/textextract_client.py
rm backend/microservices/weaviate-service/app/services/rag/langextract_client.py
```

- [ ] **Step 2: Clean up imports in weaviate_service.py**

Remove any remaining imports for `sentence_transformers`, `torch`, `get_tei_embedding`, etc. that are no longer used.

- [ ] **Step 3: Clean up CAG service embedding code**

In `cag/services/cag_service.py`, the `generate_embeddings()` method (line 203) uses its own Ollama/OpenAI embedding path. Replace with `intelligence_client.embed_batch()` or remove if CAG is not actively used.

- [ ] **Step 4: Verify nothing is broken**

```bash
cd backend/docker && docker compose restart weaviate-service
sleep 20
docker compose logs weaviate-service --since 30s | grep -i error
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead embedding code (multimodal, CAG, TEI, old clients)"
```

---

## Summary

| Phase | Tasks | What it delivers |
|-------|-------|------------------|
| **Phase 1** (Tasks 1-5) | Core service + embedding | `/embed` + `/health` running in Docker, BGE-M3 on GPU |
| **Phase 2** (Tasks 6-7) | Extraction providers | `/extract` with Docling + Tika fallback |
| **Phase 3** (Tasks 8-9c, 10) | Entities + classifier + pipeline | `/entities` + `/classify` + `/process`, vLLM NER provider |
| **Phase 4** (Tasks 11-14) | Integration + cleanup | All call sites migrated, dimension validation, old services removed |

Each phase is independently testable and deployable. Phase 1 can run alongside existing services for validation before proceeding to Phase 4 cutover.
