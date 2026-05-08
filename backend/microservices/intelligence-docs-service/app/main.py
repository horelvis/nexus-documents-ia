import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form

from app.core.config import settings
from app.providers.registry import ProviderRegistry
from app.providers.base import EmbeddingProvider, ExtractionProvider, EntityProvider
from app.providers.embedding.sentence_transformers import SentenceTransformersProvider
from app.providers.extraction.tika import TikaProvider
from app.providers.extraction.docling import DoclingProvider
from app.providers.extraction.glm_ocr import GlmOcrProvider
from app.providers.extraction.plaintext import PlaintextProvider, is_plaintext
from app.providers.entities.langextract_provider import LangExtractProvider
from app.providers.entities.regex_provider import RegexEntityProvider
from app.providers.entities.openai_ner_provider import OpenAINerProvider
from app.providers.guardrails.spanish_id_validator import SpanishIdValidator

_id_validator = SpanishIdValidator()
from app.pipeline.processor import process_document
from app.pipeline.classifier import classify_document
from app.api.identity import router as identity_router
from app.schemas.models import (
    EmbedRequest, EmbedSingleResponse, EmbedBatchResponse,
    ExtractResponse, EntitiesRequest, EntitiesResponse, EntityResponse,
    ClassifyRequest, ClassifyResponse,
    ProcessOptions, ProcessResponse,
    HealthResponse, ProviderStatus,
)

logger = logging.getLogger(__name__)

# Global registries
embedding_registry = ProviderRegistry[EmbeddingProvider]()
extraction_registry = ProviderRegistry[ExtractionProvider]()
entity_registry = ProviderRegistry[EntityProvider]()


async def _init_embedding_providers():
    for provider_name in settings.embedding_provider_list:
        if provider_name == "sentence-transformers":
            provider = SentenceTransformersProvider(
                model_name=settings.embedding_model,
                device=settings.embedding_device,
                expected_dimensions=settings.embedding_dimensions,
            )
            await provider.load_model()
            embedding_registry.register(provider)
            logger.info(f"Registered embedding provider: {provider.name}")


async def _init_extraction_providers():
    for provider_name in settings.extraction_provider_list:
        if provider_name == "docling":
            extraction_registry.register(
                DoclingProvider(url=settings.docling_url, timeout=settings.extraction_timeout)
            )
            logger.info("Registered extraction provider: docling")
        elif provider_name == "tika":
            extraction_registry.register(
                TikaProvider(url=settings.tika_url, timeout=settings.extraction_timeout)
            )
            logger.info("Registered extraction provider: tika")
        elif provider_name == "glm-ocr":
            extraction_registry.register(
                GlmOcrProvider(
                    base_url=settings.glm_ocr_url,
                    model=settings.glm_ocr_model,
                    timeout=settings.extraction_timeout,
                )
            )
            logger.info(f"Registered extraction provider: glm-ocr (model={settings.glm_ocr_model})")


async def _init_entity_providers():
    # Regex provider always runs first (fast, reliable, no LLM dependency)
    entity_registry.register(RegexEntityProvider())
    logger.info("Registered entity provider: regex (Spanish NER patterns)")

    for provider_name in settings.entity_provider_list:
        if provider_name == "langextract":
            if not settings.langextract_enabled:
                logger.info("LangExtract provider disabled via config")
                continue
            # Use the OpenAI-compatible SGLang API for LangExtract.
            # This gives us control over chat_template_kwargs (disable thinking).
            base_url = settings.sglang_base_url.rstrip("/").removesuffix("/v1")
            provider = OpenAINerProvider(
                base_url=base_url,
                model=settings.sglang_model,
            )
            entity_registry.register(provider)
            logger.info(
                f"Registered entity provider: openai_ner "
                f"(model={settings.sglang_model}, via /v1/chat/completions)"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting intelligence-docs-service...")
    await _init_embedding_providers()
    await _init_extraction_providers()
    await _init_entity_providers()
    logger.info("intelligence-docs-service ready")
    yield
    logger.info("Shutting down intelligence-docs-service")


app = FastAPI(
    title="Intelligence Docs Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(identity_router)


# --- Health ---

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

    extraction_status = [
        ProviderStatus(**s) for s in await extraction_registry.status()
    ]
    entity_status = [
        ProviderStatus(**s) for s in await entity_registry.status()
    ]

    any_embedding = any(s.available for s in embedding_status)
    status = "healthy" if any_embedding else "degraded"

    return HealthResponse(
        status=status,
        providers={
            "embedding": embedding_status,
            "extraction": extraction_status,
            "entities": entity_status,
        },
    )


# --- Embed ---

@app.post("/embed")
async def embed(request: EmbedRequest):
    if not request.text and not request.texts:
        raise HTTPException(status_code=400, detail="Provide 'text' or 'texts'")

    try:
        provider = await embedding_registry.get_available()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if request.text and not request.texts:
        vector = await provider.embed_single(request.text, task=request.task)
        return EmbedSingleResponse(
            embedding=vector,
            dimensions=provider.dimensions(),
            model=getattr(provider, "_model_name", "unknown"),
            provider=provider.name,
        )
    else:
        texts = request.texts or [request.text]
        vectors = await provider.embed(texts, task=request.task)
        return EmbedBatchResponse(
            embeddings=vectors,
            dimensions=provider.dimensions(),
            model=getattr(provider, "_model_name", "unknown"),
            provider=provider.name,
        )


# --- Extract ---

@app.post("/extract", response_model=ExtractResponse)
async def extract(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
):
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide 'file' or 'url'")

    file_bytes = None
    if file:
        file_bytes = await file.read()
        fname = filename or file.filename or "unknown"
    else:
        fname = filename or url.split("/")[-1]

    # Plaintext files: read directly, skip Docling/Tika
    if is_plaintext(fname):
        pt = PlaintextProvider()
        if file_bytes:
            result = await pt.extract(file_bytes, fname)
        else:
            result = await pt.extract_from_url(url, fname)
        return ExtractResponse(text=result.text, language=result.language, metadata=result.metadata)

    # Try each available provider with automatic fallback
    last_error = None
    result = None
    for provider in extraction_registry.all():
        try:
            if not await provider.is_available():
                continue
            if file_bytes:
                result = await provider.extract(file_bytes, fname)
            else:
                result = await provider.extract_from_url(url, fname)
            break  # Success
        except Exception as e:
            logger.warning(f"Extraction provider {provider.name} failed for {fname}: {e}")
            last_error = e

    if result is None:
        detail = f"All extraction providers failed. Last error: {last_error}" if last_error else "No extraction provider available"
        raise HTTPException(status_code=503, detail=detail)

    return ExtractResponse(
        text=result.text,
        language=result.language,
        metadata=result.metadata,
        chunks=[
            {
                "text": c.text,
                "chunk_index": c.chunk_index,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "headings": c.headings,
            }
            for c in (result.chunks or [])
        ] or None,
    )


# --- Entities ---

@app.post("/entities", response_model=EntitiesResponse)
async def entities(request: EntitiesRequest):
    all_entities = []
    for provider in entity_registry.all():
        try:
            if not await provider.is_available():
                continue
            # LangExtractProvider accepts document_type for few-shot selection
            if hasattr(provider, "name") and provider.name == "langextract":
                result = await provider.extract_entities(
                    request.text, request.language, document_type=request.document_type,
                )
            else:
                result = await provider.extract_entities(request.text, request.language)
            all_entities.extend(result)
        except Exception as e:
            logger.warning(f"Entity provider {provider.name} failed: {e}")

    # Guardrail: validate Spanish IDs and scan for missed ones
    all_entities = _id_validator.validate_and_enrich(all_entities, request.text)

    return EntitiesResponse(
        entities=[EntityResponse(
            type=e.type, value=e.value, provider=e.provider, confidence=e.confidence,
            start_pos=e.start_pos, end_pos=e.end_pos, attributes=e.attributes,
        ) for e in all_entities]
    )


# --- Classify ---

@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    result = await classify_document(
        text=request.text,
        filename=request.filename,
    )
    return ClassifyResponse(
        document_type=result.document_type,
        confidence=result.confidence,
        provider=result.provider,
    )


# --- Process (combined pipeline) ---

@app.post("/process", response_model=ProcessResponse)
async def process(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
    options: str = Form("{}"),
):
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
